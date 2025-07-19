# MCP 传输类型转换服务

> 可以将现有的MCP类型为 stdio / sse 转换为 streamable_http传输类型的MCP
> 本实现完全按照标准的MCP官方进行实现
> 版本更新：
> 当前版本： 0.0.1

## 环境变量设置

| 参数                        | 描述            | 默认值                | 是否必填 | 备注                                           |
|---------------------------|---------------|--------------------|------|----------------------------------------------|
| `TRANSPORT_TYPE`          | 传输协议类型        | `streamable_http`  | 否    | 填写传输协议类型，可选值：`stdio`、`sse`、`streamable_http` |
| `PROXY_MCP_NAME`          | 代理的 MCP 服务器名称 | `feifei-proxy-mcp` | 否    | 代理的mcp服务名称                                   |
| `PROXY_MCP_SERVER_CONFIG` | mcp 服务器配置           | -                  | 是    | 要代理的mcp服务配置                                  |
| `PROXY_MCP_PORT`          | 服务端口          | `8000`             | 否    | 代理mcp协议类型为 `sse` 或 `streamable_http` 时使用     |


## 必要安装
> 使用前 请保障当前机器已安装了 docker 环境
> 因为此模式采用docker 容器作为streamable_http 的 代理MCP服务

## 容器化部署
### docker 命令行部署

> 以下以部署 fetch mcp 为例，将stdio转为 streamable_http mcp

```shell
docker run 
  -e PROXY_MCP_SERVER_CONFIG='{"mcpServers":{"fetch":{"command":"uvx","args": ["mcp-server-fetch"]}}}'  
  nacos/nacos-mcp-router:latest
```


### docker-compose 部署