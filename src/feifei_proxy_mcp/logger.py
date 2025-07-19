import logging
import os
from logging.handlers import RotatingFileHandler


class McpLogger:
    """ mcp代理日志服务配置 """

    logger: logging.Logger | None = None
    logger_name = "feifei_proxy_mcp"

    @classmethod
    def setup_logger(cls):
        McpLogger.logger = logging.getLogger(McpLogger.logger_name)
        McpLogger.logger.setLevel(logging.INFO)

        # 防止重复添加处理器
        if McpLogger.logger.handlers:
            return

        log_file = "./logs/application.log"
        log_dir = os.path.dirname(log_file)
        os.makedirs(log_dir, exist_ok=True)

        formatter = logging.Formatter(
            "%(asctime)s | %(name)-15s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # 配置日志滚动更新
        file_handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,  # 保留5个备份文件
            encoding="utf-8"
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)

        McpLogger.logger.addHandler(file_handler)
        McpLogger.logger.propagate = False

        # 添加控制台输出
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        McpLogger.logger.addHandler(console_handler)

    @classmethod
    def get_logger(cls) -> logging.Logger:
        if McpLogger.logger is None:
            McpLogger.setup_logger()
        if McpLogger.logger is None:
            return logging.getLogger(McpLogger.logger_name)
        else:
            return McpLogger.logger
