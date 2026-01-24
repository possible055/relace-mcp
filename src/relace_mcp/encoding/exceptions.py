class EncodingDetectionError(Exception):
    """Cannot detect file encoding."""

    error_code = "ENCODING_ERROR"

    def __init__(self, path: str) -> None:
        self.path = path
        self.message = f"Cannot detect encoding for file: {path}"
        super().__init__(self.message)
