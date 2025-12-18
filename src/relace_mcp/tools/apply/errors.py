from typing import Any


def recoverable_error(
    error_code: str,
    message: str,
    path: str,
    instruction: str | None,
    trace_id: str = "",
    timing_ms: int = 0,
) -> dict[str, Any]:
    """產生可恢復錯誤的回傳訊息（結構化格式）。

    Args:
        error_code: 錯誤代碼（例如 INVALID_PATH, NEEDS_MORE_CONTEXT）。
        message: 錯誤訊息。
        path: 檔案路徑。
        instruction: 可選的 instruction。
        trace_id: 追蹤 ID。
        timing_ms: 耗時（毫秒）。

    Returns:
        結構化的錯誤回應。
    """
    return {
        "status": "error",
        "code": error_code,
        "path": path,
        "trace_id": trace_id,
        "timing_ms": timing_ms,
        "message": message,
    }


def api_error_to_recoverable(
    exc: Exception,
    path: str,
    instruction: str | None,
    trace_id: str = "",
    timing_ms: int = 0,
) -> dict[str, Any]:
    """將 API 相關錯誤轉為可恢復訊息（結構化格式）。

    Args:
        exc: API 相關例外（RelaceAPIError / RelaceNetworkError / RelaceTimeoutError）。
        path: 檔案路徑。
        instruction: 可選的 instruction。
        trace_id: 追蹤 ID。
        timing_ms: 耗時（毫秒）。

    Returns:
        結構化的可恢復錯誤回應。
    """
    from ...clients.exceptions import RelaceAPIError, RelaceNetworkError, RelaceTimeoutError

    if isinstance(exc, RelaceAPIError):
        if exc.status_code in (401, 403):
            error_code = "AUTH_ERROR"
            message = "API 認證或權限錯誤。請檢查 API key 設定。"
        else:
            error_code = "API_ERROR"
            message = "Relace API 錯誤。請簡化 edit_snippet 或增加更明確的 anchor lines。"

        return {
            "status": "error",
            "code": error_code,
            "path": path,
            "trace_id": trace_id,
            "timing_ms": timing_ms,
            "message": message,
            "detail": {
                "status_code": exc.status_code,
                "api_code": exc.code,
                "api_message": exc.message,
            },
        }

    if isinstance(exc, RelaceTimeoutError):
        return {
            "status": "error",
            "code": "TIMEOUT_ERROR",
            "path": path,
            "trace_id": trace_id,
            "timing_ms": timing_ms,
            "message": "請求逾時。請稍後重試。",
            "detail": str(exc),
        }

    if isinstance(exc, RelaceNetworkError):
        return {
            "status": "error",
            "code": "NETWORK_ERROR",
            "path": path,
            "trace_id": trace_id,
            "timing_ms": timing_ms,
            "message": "網路錯誤。請檢查網路連線後重試。",
            "detail": str(exc),
        }

    return recoverable_error(
        "UNKNOWN_ERROR",
        f"未預期的錯誤：{type(exc).__name__}",
        path,
        instruction,
        trace_id,
        timing_ms,
    )
