import json
import os
import traceback

import anyio
from mcp import types
from mcp.server import Server

from .enums import McpTransportType
from .logger import McpLogger
from .mcp_client_manager import McpClientManager
from .mcp_exception import McpException

logger = McpLogger.get_logger()

# 代理的mcp传输类型 默认为 streamable_http
transport_type: str = McpTransportType.STREAMABLE_HTTP.value

# 需要进行代理的 mcp server 配置
proxy_mcp_server_config: dict = {}

# 代理的mcp名称
proxy_mcp_name: str = ""

# 代理的mcp server 实例
proxy_mcp_server: Server

# 定义代理版本
mcp_proxy_version: str = "0.0.1"

# mcp 客户端管理服务 McpClientManager 对应着连接/会话/工具调用等服务
mcp_client_manager: McpClientManager = None


def startup():
    """ web应用启动入口 """
    global transport_type, proxy_mcp_name, proxy_mcp_server_config, proxy_mcp_server

    logger.info("====== Start mcp proxy server application begin =======")

    # 1. 获取环境变量相关信息
    proxy_mcp_name = os.getenv("PROXY_MCP_NAME", "")
    transport_type = os.getenv("TRANSPORT_TYPE", McpTransportType.STREAMABLE_HTTP.value)
    proxy_mcp_server_config_str = os.getenv("PROXY_MCP_SERVER_CONFIG", "")
    if proxy_mcp_server_config_str:
        proxy_mcp_server_config = json.loads(proxy_mcp_server_config_str)
        # TODO mcp配置 参数 合法性校验，确保mcp配置参数正确 后续完善
    else:
        raise ValueError("PROXY_MCP_SERVER_CONFIG is empty, please check!")

    # 初始化代理mcp server实例
    proxy_mcp_server = Server("feifei-proxy-mcp")

    logger.info(f"init proxy server,"
                f"transport_type: {transport_type}, "
                f"proxy_mcp_name: {proxy_mcp_name}, "
                f"proxy_mcp_server_config: {proxy_mcp_server_config}, "
                f"version: {mcp_proxy_version}")

    # 构建代理mcp server
    create_proxy_mcp_server()

    # 启动代理mcp server
    start_proxy_mcp_server()

    logger.info("======  Start mcp proxy server application end =======")


def create_proxy_mcp_server():
    """ 创建 代理mcp server 服务， 目前仅提供 tool能力，prompt, resource暂不进行支持 """

    @proxy_mcp_server.call_tool()
    async def call_tool(name: str, arguments: dict
                        ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """ 工具调用 """
        logger.info(f"calling tool: {name}, arguments: {arguments}")

        if mcp_client_manager:
            if not await init_proxy_mcp():
                raise NameError(f"failed to init proxy mcp: {proxy_mcp_name}")
        result = await mcp_client_manager.execute_tool(tool_name=name, arguments=arguments)
        return result.content

    @proxy_mcp_server.list_tools()
    async def list_tools() -> list[types.Tool]:
        """ 返回所有可用工具 """
        return await proxy_mcp_tools()

    return proxy_mcp_server


def start_proxy_mcp_server():
    """ 启动代理mcp服务器 """
    match transport_type:
        case McpTransportType.STDIO.value:
            # 本地进程mcp server
            from mcp.server.stdio import stdio_server

            async def arun():
                async with stdio_server() as streams:
                    await proxy_mcp_server.run(
                        streams[0], streams[1], proxy_mcp_server.create_initialization_options()
                    )
                # 异步调度
                anyio.run(arun)

            logger.info("======= STDIO Proxy mcp Application Started ======")

        case McpTransportType.SSE.value:
            # sse mcp server
            from mcp.server.sse import SseServerTransport
            from contextlib import asynccontextmanager
            from collections.abc import AsyncIterator
            from starlette.routing import Route, Mount
            from fastapi import FastAPI

            sse_transport = SseServerTransport("/messages/")

            async def handle_sse(request):
                async with sse_transport.connect_sse(request.scope,
                                                     request.receive, request._send) as streams:
                    await proxy_mcp_server.run(streams[0], streams[1],
                                                 proxy_mcp_server.create_initialization_options())

            @asynccontextmanager
            async def sse_lifespan(app: FastAPI) -> AsyncIterator[None]:
                """ 上下文会话管理 """
                try:
                    if not await init_proxy_mcp():
                        raise McpException("failed to init mcp server")
                    yield
                    await mcp_client_manager.cleanup()
                finally:
                    logger.info("Application shutting down...")

            # 构建fastapi web程序
            sse_app = FastAPI(
                debug=True,
                routes=[
                    Route("/sse", endpoint=handle_sse, methods=["GET"]),
                    Mount("/messages/", app=sse_transport.handle_post_message),
                ],
                lifespan=sse_lifespan,
            )

            import uvicorn

            uvicorn.run(sse_app, host="0.0.0.0", port=int(os.getenv("PROXY_MCP_PORT", "8000")))
            logger.info("======= SSE Proxy mcp Application Started ======")
            return

        case McpTransportType.STREAMABLE_HTTP.value:
            from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
            from starlette.types import Scope
            from starlette.types import Receive
            from starlette.types import Send

            from mcp.server.sse import SseServerTransport
            from fastapi import FastAPI
            from starlette.routing import Mount
            from contextlib import asynccontextmanager
            from collections.abc import AsyncIterator

            session_manager = StreamableHTTPSessionManager(
                app=proxy_mcp_server,
                event_store=None,
                json_response=False,
                stateless=True,  # 设置为无状态
            )

            sse_transport = SseServerTransport("/messages/")

            async def handle_streamable_http(
                    scope: Scope, receive: Receive, send: Send
            ) -> None:
                await session_manager.handle_request(scope, receive, send)

            @asynccontextmanager
            async def streamable_lifespan(app: FastAPI) -> AsyncIterator[None]:
                """ 上下文会话管理 """
                logger.info("Starting session manager...")
                async with session_manager.run():
                    logger.info("Session manager started successfully")

                    try:
                        if not await init_proxy_mcp():
                            raise McpException("failed to init_proxy_mcp")
                        yield
                    except Exception as e:
                        logger.error(f"Error during MCP initialization: {e}")
                        logger.error(f"Traceback: {traceback.format_exc()}")
                        raise McpException(f"failed to init_proxy_mcp: {e}")
                    finally:
                        logger.info("Application shutting down...")
                        await mcp_client_manager.cleanup()

            # 启动web应用
            streamable_app = FastAPI(
                debug=True,
                routes=[
                    Mount("/mcp", app=handle_streamable_http),
                    Mount("/messages/", app=sse_transport.handle_post_message),  # 兼容sse模式
                ],
                lifespan=streamable_lifespan,
            )

            import uvicorn
            uvicorn.run(streamable_app, host="0.0.0.0", port=int(os.getenv("PROXY_MCP_PORT", "8000")))

        case _:
            raise ValueError("Invalid MCP_TRANSPORT_TYPE")


async def init_proxy_mcp() -> bool:
    global proxy_mcp_server_config, mcp_client_manager

    # 如果代理mcp已经在运行中，则不需要再次构建连接
    if mcp_client_manager:
        return True

    # 创建mcp客户端连接
    tmp_mcp_client_manager = McpClientManager(mcp_server_config=proxy_mcp_server_config)

    # 等待 mcp客户端连接 + 初始化完成
    await tmp_mcp_client_manager.wait_for_initialization()

    # 健康检查
    if await tmp_mcp_client_manager.healthy():
        mcp_client_manager = tmp_mcp_client_manager
        # 获取mcp server相关服务版本信息
        init_result = mcp_client_manager.get_initialized_response()
        version = getattr(getattr(init_result, 'serverInfo', None), 'version', "1.0.0")
        proxy_mcp_server.version = version
        return True

    else:
        return False


async def proxy_mcp_tools() -> list[types.Tool]:
    if await init_proxy_mcp():
        try:
            return await mcp_client_manager.list_tools()
        except (KeyError, Exception) as e:
            logger.warning("failed to list tools for proxy mcp server: " + proxy_mcp_name, exc_info=e)
            return []
    else:
        raise McpException(msg=f"failed to initialize proxy MCP server {proxy_mcp_name}")
