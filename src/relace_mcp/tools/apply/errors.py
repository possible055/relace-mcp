from typing import Any

import openai


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


def openai_error_to_recoverable(
    exc: openai.APIError,
    path: str,
    instruction: str | None,
    trace_id: str = "",
    timing_ms: int = 0,
) -> dict[str, Any]:
    """Convert OpenAI SDK errors to recoverable message (structured format).

    Args:
        exc: OpenAI API exception (APIStatusError, APIConnectionError, APITimeoutError).
        path: File path.
        instruction: Optional instruction.
        trace_id: Trace ID.
        timing_ms: Elapsed time (milliseconds).

    Returns:
        Structured recoverable error response.
    """
    if isinstance(exc, openai.APITimeoutError):
        return {
            "status": "error",
            "code": "TIMEOUT_ERROR",
            "path": path,
            "trace_id": trace_id,
            "timing_ms": timing_ms,
            "message": "Request timed out. Please retry later.",
            "detail": str(exc),
        }

    if isinstance(exc, openai.APIConnectionError):
        return {
            "status": "error",
            "code": "NETWORK_ERROR",
            "path": path,
            "trace_id": trace_id,
            "timing_ms": timing_ms,
            "message": "Network error. Please check network connection and retry.",
            "detail": str(exc),
        }

    if isinstance(exc, openai.APIStatusError):
        status_code = exc.status_code
        if status_code in (401, 403):
            error_code = "AUTH_ERROR"
            message = "API authentication or permission error. Please check API key settings."
        elif status_code == 429:
            error_code = "RATE_LIMIT"
            message = "Rate limit exceeded. Please retry later."
        elif status_code >= 500:
            error_code = "SERVER_ERROR"
            message = "API server error. Please retry later."
        else:
            error_code = "API_ERROR"
            message = "API error. Please simplify edit_snippet or add more explicit anchor lines."

        return {
            "status": "error",
            "code": error_code,
            "path": path,
            "trace_id": trace_id,
            "timing_ms": timing_ms,
            "message": message,
            "detail": {
                "status_code": status_code,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        }

    return recoverable_error(
        "API_ERROR",
        f"Unexpected API error: {type(exc).__name__}",
        path,
        instruction,
        trace_id,
        timing_ms,
    )
