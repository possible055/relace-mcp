class ApplyError(Exception):
    """fast_apply 工具的基礎例外類別。"""

    error_code: str = "APPLY_ERROR"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class FileTooLargeError(ApplyError):
    """檔案超過大小限制。"""

    error_code = "FILE_TOO_LARGE"

    def __init__(self, file_size: int, max_size: int) -> None:
        self.file_size = file_size
        self.max_size = max_size
        super().__init__(f"File too large ({file_size} bytes). Maximum allowed: {max_size} bytes")


class EncodingDetectionError(ApplyError):
    """無法偵測檔案編碼。"""

    error_code = "ENCODING_ERROR"

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Cannot detect encoding for file: {path}")


class ApiInvalidResponseError(ApplyError):
    """API 回傳無效回應。"""

    error_code = "API_INVALID_RESPONSE"

    def __init__(self, detail: str = "Relace API did not return 'mergedCode'") -> None:
        super().__init__(detail)


class FileNotWritableError(ApplyError):
    """檔案不可寫入。"""

    error_code = "FILE_NOT_WRITABLE"

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"File is not writable: {path}")


class PostCheckFailedError(ApplyError):
    """Post-check 驗證 merged_code 失敗。"""

    error_code = "POST_CHECK_FAILED"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Post-check failed: {reason}")
