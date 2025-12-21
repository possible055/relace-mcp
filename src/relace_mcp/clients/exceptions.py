import json

import httpx


class RelaceAPIError(Exception):
    """Relace API error."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        retryable: bool = False,
        retry_after: float | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable
        self.retry_after = retry_after
        super().__init__(f"[{code}] {message} (status={status_code})")


class RelaceNetworkError(Exception):
    """Network layer error, retryable."""


class RelaceTimeoutError(RelaceNetworkError):
    """Request timeout, retryable."""


def raise_for_status(resp: httpx.Response) -> None:
    """Raise corresponding RelaceAPIError based on HTTP status.

    Args:
        resp: httpx Response object.

    Raises:
        RelaceAPIError: Raised when HTTP status is not 2xx.
    """
    if resp.is_success:
        return

    # Parse error response
    code = "unknown"
    message = resp.text

    try:
        data = json.loads(resp.text)
        if isinstance(data, dict):
            # Relace format: {"code": "...", "message": "..."}
            # OpenAI-compatible format: {"error": {"message": "...", "type": "...", "code": "..."}}
            error = data.get("error")
            if isinstance(error, dict):
                code = error.get("code") or error.get("type") or data.get("code", "unknown")
                message = (
                    error.get("message") or data.get("message") or data.get("detail") or resp.text
                )
            else:
                code = str(data.get("code") or data.get("error") or "unknown")
                message = str(data.get("message") or data.get("detail") or resp.text)
    except (json.JSONDecodeError, TypeError):
        pass

    if not isinstance(code, str):
        code = str(code)
    if not isinstance(message, str):
        message = str(message)

    # Determine if retryable
    retryable = False
    retry_after: float | None = None

    if resp.status_code == 429:
        retryable = True
        if "retry-after" in resp.headers:
            try:
                retry_after = float(resp.headers["retry-after"])
            except ValueError:
                pass
    elif resp.status_code >= 500:
        retryable = True

    raise RelaceAPIError(
        status_code=resp.status_code,
        code=code,
        message=message,
        retryable=retryable,
        retry_after=retry_after,
    )
