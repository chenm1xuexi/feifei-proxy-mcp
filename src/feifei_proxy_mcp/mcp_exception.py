class McpException(Exception):
    """ mcp 异常类 """
    msg: str | None = None

    def __init__(self, msg: str):
        self.msg = msg

    def __str__(self) -> str:
        return f'{self.msg}'

    def get_error_message(self) -> str | None:
        return self.msg
