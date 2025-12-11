import json

import httpx


class RelaceAPIError(Exception):
    """Relace API 錯誤。"""

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
    """網路層錯誤，可重試。"""


class RelaceTimeoutError(RelaceNetworkError):
    """請求逾時，可重試。"""


def raise_for_status(resp: httpx.Response) -> None:
    """根據 HTTP status 拋出對應的 RelaceAPIError。

    Args:
        resp: httpx Response 物件。

    Raises:
        RelaceAPIError: 當 HTTP status 非 2xx 時拋出。
    """
    if resp.is_success:
        return

    # 解析錯誤回應
    code = "unknown"
    message = resp.text

    try:
        data = json.loads(resp.text)
        if isinstance(data, dict):
            code = data.get("code", data.get("error", "unknown"))
            message = data.get("message", data.get("detail", resp.text))
    except (json.JSONDecodeError, TypeError):
        pass

    # 判斷是否可重試
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
