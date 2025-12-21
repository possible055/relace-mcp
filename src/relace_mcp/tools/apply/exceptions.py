class ApplyError(Exception):
    """Base exception class for fast_apply tool."""

    error_code: str = "APPLY_ERROR"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class FileTooLargeError(ApplyError):
    """File exceeds size limit."""

    error_code = "FILE_TOO_LARGE"

    def __init__(self, file_size: int, max_size: int) -> None:
        self.file_size = file_size
        self.max_size = max_size
        super().__init__(f"File too large ({file_size} bytes). Maximum allowed: {max_size} bytes")


class EncodingDetectionError(ApplyError):
    """Cannot detect file encoding."""

    error_code = "ENCODING_ERROR"

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Cannot detect encoding for file: {path}")


class ApiInvalidResponseError(ApplyError):
    """API returned invalid response."""

    error_code = "API_INVALID_RESPONSE"

    def __init__(self, detail: str = "Apply API did not return updated code") -> None:
        super().__init__(detail)


class FileNotWritableError(ApplyError):
    """File is not writable."""

    error_code = "FILE_NOT_WRITABLE"

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"File is not writable: {path}")
