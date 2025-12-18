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
            code = data.get("code", data.get("error", "unknown"))
            message = data.get("message", data.get("detail", resp.text))
    except (json.JSONDecodeError, TypeError):
        pass

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
    elif resp.status_code == 423:
        retryable = True
    elif resp.status_code >= 500:
        retryable = True

    raise RelaceAPIError(
        status_code=resp.status_code,
        code=code,
        message=message,
        retryable=retryable,
        retry_after=retry_after,
    )
