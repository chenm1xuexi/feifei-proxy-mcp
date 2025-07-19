import asyncio
from typing import Any
from contextlib import AsyncExitStack

import mcp
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

from .enums import McpTransportType
from .logger import McpLogger

logger = McpLogger.get_logger()


def _stdio_transport_context(config: dict[str, Any]):
    server_params = StdioServerParameters(command=config['command'], args=config['args'] if 'args' in config else [],
                                          env=config['env'] if 'env' in config else {})
    return stdio_client(server_params)


def _sse_transport_context(config: dict[str, Any]):
    return sse_client(url=config['url'], headers=config['headers'] if 'headers' in config else {}, timeout=10)


def _streamable_http_transport_context(config: dict[str, Any]):
    return streamablehttp_client(url=config["url"], headers=config['headers'] if 'headers' in config else {})


class McpClientManager:
    """
    mcp 客户端 实现 用于连接mcp-server / 会话管理 / 工具调度 / 连接检查 / 资源清理等能力

    "mcpServers": {
      "fetch": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-fetch"],
      },
      "fetch1": {
        "transport": "sse",
        "url": "http://xxx.xxx.xx/sse"
      },
      "fetch2": {
        "transport": "streamable_http",
        "url": "http://xxx.xxx.xx/mcp"
      },
    }

    """

    def __init__(self, mcp_server_config: dict[str, Any]):
        self.session: ClientSession | None = None
        self._cleanup_lock: asyncio.Lock = asyncio.Lock()
        self.exit_stack: AsyncExitStack = AsyncExitStack()
        self.stdio_context: Any | None = None
        self._initialized_event = asyncio.Event()
        self._shutdown_event = asyncio.Event()
        self._initialized: bool = False  # 初始化状态标记

        mcp_servers = mcp_server_config.get('mcpServers', {})
        if not mcp_servers:
            raise ValueError("mcpServers must be contain one mcp server configuration")

        # 这里请注意，mcpServers只能包含一个 mcp server 配置，
        # 如果配置多个，只会取第一个，其他的将被忽略
        for key, value in mcp_servers.items():
            logger.info(f"====== mcp_name: {key}, mcp_config: {value} ======")
            self.mcp_name = key
            self.server_config = value
            break

        transport = self.server_config.get('transport', McpTransportType.STDIO.value)
        if transport == McpTransportType.SSE.value:
            self._transport_context_factory = _sse_transport_context
        elif transport == McpTransportType.STREAMABLE_HTTP.value:
            self._transport_context_factory = _streamable_http_transport_context
        else:
            self._transport_context_factory = _stdio_transport_context

        self._transport = transport
        # 创建一个异步任务，等待事件循环去执行。
        self._server_task = asyncio.create_task(self._server_lifespan_cycle())

    async def _server_lifespan_cycle(self):
        logger.info("======= Start to connect MCP server ======")
        try:
            if self._transport == McpTransportType.STREAMABLE_HTTP.value:
                async with self._transport_context_factory(self.server_config) as (read, write, _):
                    # 构建一个mcp客户端连接
                    async with ClientSession(read, write) as session:
                        self.session_initialized_response = await session.initialize()
                        self.session = session
                        self._initialized = True
                        self._initialized_event.set()
                        await self.wait_for_shutdown_request()
            else:
                async with self._transport_context_factory(self.server_config) as (read, write):
                    # 构建一个mcp客户端连接
                    async with ClientSession(read, write) as session:
                        self.session_initialized_response = await session.initialize()
                        self.session = session
                        self._initialized = True
                        self._initialized_event.set()
                        await self.wait_for_shutdown_request()
        except Exception as ex:
            logger.warning("failed to init mcp server " + self.mcp_name + ", config: "
                           + str(self.server_config), exc_info=ex)
            self._initialized = False
            self._initialized_event.set()
            self._shutdown_event.set()

    def get_initialized_response(self) -> mcp.types.InitializeResult:
        return self.session_initialized_response

    async def healthy(self) -> bool:
        """ 连接mcp server 健康检查 """
        return (self.session is not None and
                self._initialized and
                not self._shutdown_event.is_set()
                and not await self.is_session_disconnected())

    async def wait_for_initialization(self):
        await self._initialized_event.wait()

    async def request_for_shutdown(self):
        self._shutdown_event.set()

    async def wait_for_shutdown_request(self):
        await self._shutdown_event.wait()

    async def list_tools(self) -> list[mcp.types.Tool]:
        """ 从mcp server 快速获取 工具列表 """
        if not self.session:
            raise RuntimeError(f"Server {self.mcp_name} is not initialized")

        tools_response = await self.session.list_tools()

        return tools_response.tools

    async def execute_tool(
            self,
            tool_name: str,
            arguments: dict[str, Any],
            retries: int = 2,
            delay: float = 1.0,
    ) -> Any:
        """ 调用mcp工具 """
        if not self.session:
            raise RuntimeError(f"Server {self.mcp_name} not initialized")

        attempt = 0
        while attempt < retries:
            try:
                result = await self.session.call_tool(tool_name, arguments)

                return result

            except Exception as e:
                attempt += 1
                if attempt < retries:
                    await asyncio.sleep(delay)
                    await self.session.initialize()
                    try:
                        result = await self.session.call_tool(tool_name, arguments)
                        return result
                    except Exception as e:
                        raise e
                else:
                    raise

    async def cleanup(self) -> None:
        """Clean up server resources."""
        async with self._cleanup_lock:
            try:
                await self.exit_stack.aclose()
                self.session = None
                self.stdio_context = None
            except Exception as e:
                logger.error(f"Error during cleanup of server {self.mcp_name}: {e}")

    async def is_session_disconnected(self, timeout: float = 5.0) -> bool:
        """
        检查session是否断开连接
  
        Args:
            timeout: 检测超时时间（秒）
  
        Returns:
            bool: True表示连接断开，False表示连接正常
        """
        # 基础检查：session对象是否存在
        if not self.session:
            logger.info(f"Server {self.mcp_name}: session object is None")
            return True

        # 检查是否已初始化
        if not self._initialized:
            logger.info(f"Server {self.mcp_name}: not initialized")
            return True

        # 检查是否请求关闭
        if self._shutdown_event.is_set():
            logger.info(f"Server {self.mcp_name}: shutdown requested")
            return True

        try:
            # 尝试执行一个轻量级操作来测试连接
            logger.info(f"Server {self.mcp_name}: testing connection health")
            return await self._test_connection_health(timeout)
        except Exception as e:
            logger.warning(f"Server {self.mcp_name}: connection test failed: {e}")
            return True

    async def _test_connection_health(self, timeout: float) -> bool:
        import anyio
        """
        测试连接健康状态
  
        Args:
            timeout: 超时时间
  
        Returns:
            bool: True表示连接断开，False表示连接正常
        """
        try:
            # 使用asyncio.wait_for设置超时
            async with asyncio.timeout(timeout):
                if self.session is None:
                    return True
                # 尝试调用一个简单的MCP操作
                await self.session.list_tools()
                # 更新最后活动时间
                import time
                self._last_activity_time = time.time()
                return False  # 连接正常

        except (asyncio.TimeoutError, mcp.McpError, anyio.ClosedResourceError):
            logger.warning(f"Server {self.mcp_name}: connection test timeout after {timeout}s")
            return True
        except (ConnectionError, BrokenPipeError, OSError) as e:
            logger.warning(f"Server {self.mcp_name}: connection error: {e}")
            return True
        except Exception as e:
            # 对于其他异常，可能是协议错误或服务器内部错误
            # 这里可以根据具体的异常类型来判断是否是连接问题
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ['connection', 'broken', 'closed', 'reset', 'timeout']):
                logger.warning(f"Server {self.mcp_name}: connection-related error: {e}")
                return True
            else:
                # 其他错误可能不是连接问题，连接可能仍然正常
                logger.error(f"Server {self.mcp_name}: non-connection error during health check",
                             exc_info=e)
                return False
