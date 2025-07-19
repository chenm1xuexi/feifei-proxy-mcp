from feifei_proxy_mcp import main

if __name__ == "__main__":
    import os

    os.environ["PROXY_MCP_NAME"] = "xiaofeifei_test"
    os.environ["TRANSPORT_TYPE"] = "streamable_http"
    os.environ["PROXY_MCP_SERVER_CONFIG"] = '{"mcpServers":{"fetch":{"command":"uvx","args": ["mcp-server-fetch"]}}}'
    os.environ["PROXY_MCP_PORT"] = "8888"
    main()