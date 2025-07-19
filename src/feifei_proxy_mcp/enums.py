from enum import Enum


class McpTransportType(str, Enum):
    """
    mcp 传输类型枚举
    """
    STDIO = 'stdio'  # 本地标准输入输出服务
    SSE = 'sse'  # 远程 http sse服务 废弃
    STREAMABLE_HTTP = 'streamable_http'  # 远程 http 流式服务
    OPENAPI = 'openapi'  # 开放平台http服务 后续支持，自动转为mcp服务