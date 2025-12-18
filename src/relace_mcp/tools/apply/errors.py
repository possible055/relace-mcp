from typing import Any


def recoverable_error(
    error_code: str,
    message: str,
    path: str,
    instruction: str | None,
    trace_id: str = "",
    timing_ms: int = 0,
) -> dict[str, Any]:
    """Generate recoverable error response message (structured format).

    Args:
        error_code: Error code (e.g., INVALID_PATH, NEEDS_MORE_CONTEXT).
        message: Error message.
        path: File path.
        instruction: Optional instruction.
        trace_id: Trace ID.
        timing_ms: Elapsed time (milliseconds).

    Returns:
        Structured error response.
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
    """Convert API-related errors to recoverable message (structured format).

    Args:
        exc: API-related exception (RelaceAPIError / RelaceNetworkError / RelaceTimeoutError).
        path: File path.
        instruction: Optional instruction.
        trace_id: Trace ID.
        timing_ms: Elapsed time (milliseconds).

    Returns:
        Structured recoverable error response.
    """
    from ...clients.exceptions import RelaceAPIError, RelaceNetworkError, RelaceTimeoutError

    if isinstance(exc, RelaceAPIError):
        if exc.status_code in (401, 403):
            error_code = "AUTH_ERROR"
            message = "API authentication or permission error. Please check API key settings."
        else:
            error_code = "API_ERROR"
            message = (
                "Relace API error. Please simplify edit_snippet or add more explicit anchor lines."
            )

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
            "message": "Request timed out. Please retry later.",
            "detail": str(exc),
        }

    if isinstance(exc, RelaceNetworkError):
        return {
            "status": "error",
            "code": "NETWORK_ERROR",
            "path": path,
            "trace_id": trace_id,
            "timing_ms": timing_ms,
            "message": "Network error. Please check network connection and retry.",
            "detail": str(exc),
        }

    return recoverable_error(
        "UNKNOWN_ERROR",
        f"Unexpected error: {type(exc).__name__}",
        path,
        instruction,
        trace_id,
        timing_ms,
    )
