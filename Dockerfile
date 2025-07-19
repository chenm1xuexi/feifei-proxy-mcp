# 用于提供通用的mcp-server docker镜像 使用内置安装好了uv的python3.12作为基础镜像
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

# 安装必要工具
RUN apt-get update && apt-get install -y curl xz-utils
# 安装node 目前固定版本为v20.11.1 较新版本 方便用于后续 stdio 采用npx构建 mcp server
RUN curl -fsSL https://repo.huaweicloud.com/nodejs/v20.11.1/node-v20.11.1-linux-x64.tar.xz | tar -xJ -C /usr/local --strip-components=1
# 设置 npm 使用国内镜像
RUN npm config set registry https://registry.npmmirror.com
# 清理
RUN apt-get remove -y curl xz-utils && apt-get autoremove -y && apt-get clean && rm -rf /var/lib/apt/lists/*

# 配置pip使用阿里云源
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    pip config set install.trusted-host mirrors.aliyun.com

# 配置uv使用阿里云源 安装uv的目的是方便容器 uvx启动 mcp服务
ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV UV_TRUSTED_HOST=mirrors.aliyun.com

# 创建工作目录
WORKDIR /app

# 拷贝项目相关文件
COPY . /app

# 安装python依赖包
#RUN uv sync --no-cache
RUN pip install --no-cache-dir .

CMD ["python", "-m", "feifei_proxy_mcp"]
