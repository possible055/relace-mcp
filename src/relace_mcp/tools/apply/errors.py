def recoverable_error(error_code: str, message: str, path: str, instruction: str | None) -> str:
    """產生可恢復錯誤的回傳訊息。

    Args:
        error_code: 錯誤代碼（例如 INVALID_PATH, NEEDS_MORE_CONTEXT）。
        message: 錯誤訊息。
        path: 檔案路徑。
        instruction: 可選的 instruction。

    Returns:
        格式化的錯誤訊息。
    """
    return f"{error_code}\n{message}\npath: {path}\ninstruction: {instruction or ''}\n"


def api_error_to_recoverable(exc: Exception, path: str, instruction: str | None) -> str:
    """將 API 相關錯誤轉為可恢復訊息。

    Args:
        exc: API 相關例外（RelaceAPIError / RelaceNetworkError / RelaceTimeoutError）。
        path: 檔案路徑。
        instruction: 可選的 instruction。

    Returns:
        格式化的可恢復錯誤訊息。
    """
    from ...clients.exceptions import RelaceAPIError, RelaceNetworkError, RelaceTimeoutError

    if isinstance(exc, RelaceAPIError):
        # 區分 auth 錯誤和其他 API 錯誤
        if exc.status_code in (401, 403):
            error_code = "AUTH_ERROR"
            message = "API 認證或權限錯誤。請檢查 API key 設定。"
        else:
            error_code = "API_ERROR"
            message = "Relace API 錯誤。請簡化 edit_snippet 或增加更明確的 anchor lines。"

        return (
            f"{error_code}\n"
            f"{message}\n"
            f"path: {path}\n"
            f"instruction: {instruction or ''}\n"
            f"status: {exc.status_code}\n"
            f"code: {exc.code}\n"
            f"detail: {exc.message}\n"
        )

    if isinstance(exc, RelaceTimeoutError):
        return (
            f"TIMEOUT_ERROR\n"
            f"請求逾時。請稍後重試。\n"
            f"path: {path}\n"
            f"instruction: {instruction or ''}\n"
            f"detail: {str(exc)}\n"
        )

    if isinstance(exc, RelaceNetworkError):
        return (
            f"NETWORK_ERROR\n"
            f"網路錯誤。請檢查網路連線後重試。\n"
            f"path: {path}\n"
            f"instruction: {instruction or ''}\n"
            f"detail: {str(exc)}\n"
        )

    # 不應該到這裡，但作為 fallback
    return recoverable_error(
        "UNKNOWN_ERROR",
        f"未預期的錯誤：{type(exc).__name__}",
        path,
        instruction,
    )
