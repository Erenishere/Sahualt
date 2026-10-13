class BridgeError(Exception):
    """Only stable internal codes are exposed; upstream messages remain private."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
