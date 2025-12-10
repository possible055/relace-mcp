import json
import logging
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx

from ..config import (
    MAX_RETRIES,
    RELACE_ENDPOINT,
    RELACE_MODEL,
    RETRY_BASE_DELAY,
    TIMEOUT_SECONDS,
    RelaceConfig,
)

logger = logging.getLogger(__name__)


class RelaceErrorCode(str, Enum):
    """Relace API 官方錯誤碼。"""

    # 400
    INVALID_PARAMETER = "invalid_parameter"
    VALIDATION_ERROR = "validation_error"
    # 401
    MISSING_API_KEY = "missing_api_key"
    INVALID_API_KEY = "invalid_api_key"
    # 403
    INSUFFICIENT_PERMISSIONS = "insufficient_permissions"
    # 404
    NOT_FOUND = "not_found"
    # 405
    METHOD_NOT_ALLOWED = "method_not_allowed"
    # 409
    CONFLICT = "conflict"
    # 413
    PAYLOAD_TOO_LARGE = "payload_too_large"
    # 422
    INVALID_TEMPLATE = "invalid_template"
    INVALID_FILE_FORMAT = "invalid_file_format"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    # 423
    RESOURCE_LOCKED = "resource_locked"
    # 429
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    # 5xx
    APPLICATION_ERROR = "application_error"
    INTERNAL_SERVER_ERROR = "internal_server_error"
    # Fallback
    UNKNOWN = "unknown"


@dataclass
class RelaceErrorDetail:
    """解析後的 Relace API 錯誤詳情。"""

    code: RelaceErrorCode
    message: str
    status_code: int
    raw_response: str


class RelaceAPIError(Exception):
    """Relace API 錯誤基底類別。"""

    def __init__(self, detail: RelaceErrorDetail) -> None:
        self.detail = detail
        super().__init__(f"[{detail.code.value}] {detail.message} (status={detail.status_code})")


class RelaceAuthError(RelaceAPIError):
    """認證相關錯誤 (401, 403)，不可重試。"""


class RelaceValidationError(RelaceAPIError):
    """請求驗證錯誤 (400, 422)，不可重試。"""


class RelaceNotFoundError(RelaceAPIError):
    """資源不存在 (404)，不可重試。"""


class RelaceRateLimitError(RelaceAPIError):
    """Rate limit 錯誤 (429)，應等待後重試。"""

    def __init__(self, detail: RelaceErrorDetail, retry_after: float | None = None) -> None:
        super().__init__(detail)
        self.retry_after = retry_after


class RelaceResourceLockedError(RelaceAPIError):
    """資源鎖定 (423)，可稍後重試。"""


class RelaceServerError(RelaceAPIError):
    """伺服器端錯誤 (5xx)，可重試。"""


class RelaceNetworkError(Exception):
    """網路層錯誤，可重試。"""


class RelaceTimeoutError(RelaceNetworkError):
    """請求逾時，可重試。"""


def _parse_error_response(status_code: int, response_text: str) -> RelaceErrorDetail:
    """解析 Relace API 錯誤回應。"""
    code = RelaceErrorCode.UNKNOWN
    message = response_text

    try:
        data = json.loads(response_text)
        if isinstance(data, dict):
            raw_code = data.get("code", data.get("error", ""))
            message = data.get("message", data.get("detail", response_text))
            try:
                code = RelaceErrorCode(raw_code)
            except ValueError:
                code = RelaceErrorCode.UNKNOWN
    except (json.JSONDecodeError, TypeError):
        pass

    return RelaceErrorDetail(
        code=code, message=message, status_code=status_code, raw_response=response_text
    )


def _raise_for_status(resp: httpx.Response) -> None:
    """根據 HTTP status 和 error code 拋出對應的例外。"""
    if resp.is_success:
        return

    detail = _parse_error_response(resp.status_code, resp.text)

    if resp.status_code == 401:
        raise RelaceAuthError(detail)

    if resp.status_code == 403:
        raise RelaceAuthError(detail)

    if resp.status_code == 404:
        raise RelaceNotFoundError(detail)

    if resp.status_code == 423:
        raise RelaceResourceLockedError(detail)

    if resp.status_code == 429:
        retry_after: float | None = None
        if "retry-after" in resp.headers:
            try:
                retry_after = float(resp.headers["retry-after"])
            except ValueError:
                pass
        raise RelaceRateLimitError(detail, retry_after=retry_after)

    if 400 <= resp.status_code < 500:
        raise RelaceValidationError(detail)

    if resp.status_code >= 500:
        raise RelaceServerError(detail)

    # Fallback: 處理所有其他非成功狀態（如 3xx、1xx 或代理層錯誤）
    raise RelaceServerError(detail)


class RelaceClient:
    def __init__(self, config: RelaceConfig) -> None:
        self._config = config

    def apply(
        self,
        initial_code: str,
        edit_snippet: str,
        instruction: str | None = None,
        relace_metadata: dict[str, Any] | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        """呼叫 Relace API 執行 Instant apply。

        Args:
            initial_code: 原始檔案內容。
            edit_snippet: 要套用的程式碼變更片段。
            instruction: 補充說明，用來協助 disambiguation。
            relace_metadata: 額外 metadata，會送到 Relace API 用於追蹤。
            stream: 是否要求串流回應；目前僅支援 False，True 會回退為 False。

        Returns:
            Relace API 回傳的 JSON dict。

        Raises:
            RelaceAuthError: API key 無效或缺失。
            RelaceValidationError: 請求參數有誤。
            RelaceNotFoundError: 資源不存在。
            RelaceRateLimitError: 超過速率限制（已重試 MAX_RETRIES 次）。
            RelaceResourceLockedError: 資源被鎖定（已重試 MAX_RETRIES 次）。
            RelaceServerError: 伺服器端錯誤（已重試 MAX_RETRIES 次）。
            RelaceNetworkError: 網路錯誤（已重試 MAX_RETRIES 次）。
        """
        if stream:
            logger.warning("Relace API stream mode is not supported; falling back to stream=False")
            stream = False

        payload: dict[str, Any] = {
            "initial_code": initial_code,
            "edit_snippet": edit_snippet,
            "model": RELACE_MODEL,
            "stream": stream,
        }
        if instruction:
            payload["instruction"] = instruction
        if relace_metadata:
            payload["relace_metadata"] = relace_metadata

        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }

        trace_id = relace_metadata.get("trace_id", "unknown") if relace_metadata else "unknown"
        last_exc: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                started_at = time.monotonic()
                with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
                    resp = client.post(RELACE_ENDPOINT, json=payload, headers=headers)
                latency_ms = int((time.monotonic() - started_at) * 1000)

                try:
                    _raise_for_status(resp)
                except (RelaceAuthError, RelaceValidationError, RelaceNotFoundError) as exc:
                    # 不可重試的錯誤，直接拋出
                    logger.error(
                        "[%s] Relace API %s (status=%d, latency=%dms): %s",
                        trace_id,
                        exc.detail.code.value,
                        resp.status_code,
                        latency_ms,
                        exc.detail.message,
                    )
                    raise

                except RelaceRateLimitError as exc:
                    last_exc = exc
                    logger.warning(
                        "[%s] Relace API rate_limit_exceeded (status=%d, latency=%dms, attempt=%d/%d)",
                        trace_id,
                        resp.status_code,
                        latency_ms,
                        attempt + 1,
                        MAX_RETRIES + 1,
                    )
                    if attempt < MAX_RETRIES:
                        delay = (
                            exc.retry_after if exc.retry_after else RETRY_BASE_DELAY * (2**attempt)
                        )
                        delay += random.uniform(0, 0.5)  # nosec B311
                        time.sleep(delay)
                        continue
                    raise

                except RelaceResourceLockedError as exc:
                    last_exc = exc
                    logger.warning(
                        "[%s] Relace API resource_locked (status=%d, latency=%dms, attempt=%d/%d)",
                        trace_id,
                        resp.status_code,
                        latency_ms,
                        attempt + 1,
                        MAX_RETRIES + 1,
                    )
                    if attempt < MAX_RETRIES:
                        delay = RETRY_BASE_DELAY * (2**attempt) + random.uniform(0, 0.5)  # nosec B311
                        time.sleep(delay)
                        continue
                    raise

                except RelaceServerError as exc:
                    last_exc = exc
                    logger.warning(
                        "[%s] Relace API server_error (status=%d, latency=%dms, attempt=%d/%d): %s",
                        trace_id,
                        resp.status_code,
                        latency_ms,
                        attempt + 1,
                        MAX_RETRIES + 1,
                        exc.detail.code.value,
                    )
                    if attempt < MAX_RETRIES:
                        delay = RETRY_BASE_DELAY * (2**attempt) + random.uniform(0, 0.5)  # nosec B311
                        time.sleep(delay)
                        continue
                    raise

                # 成功
                logger.info(
                    "[%s] Relace API success (status=%d, latency=%dms)",
                    trace_id,
                    resp.status_code,
                    latency_ms,
                )

                try:
                    return resp.json()
                except ValueError as exc:
                    # 2xx 但非 JSON 是服務端異常行為，非用戶端驗證錯誤
                    logger.error(
                        "[%s] Relace API returned non-JSON response (status=%d)",
                        trace_id,
                        resp.status_code,
                    )
                    raise RelaceServerError(
                        RelaceErrorDetail(
                            code=RelaceErrorCode.APPLICATION_ERROR,
                            message="Relace API returned non-JSON response",
                            status_code=resp.status_code,
                            raw_response=resp.text,
                        )
                    ) from exc

            except httpx.TimeoutException as exc:
                last_exc = RelaceTimeoutError(f"Request timed out after {TIMEOUT_SECONDS}s")
                last_exc.__cause__ = exc
                logger.warning(
                    "[%s] Relace API timeout after %.1fs (attempt=%d/%d)",
                    trace_id,
                    TIMEOUT_SECONDS,
                    attempt + 1,
                    MAX_RETRIES + 1,
                )
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2**attempt) + random.uniform(0, 0.5)  # nosec B311
                    time.sleep(delay)
                    continue
                raise last_exc from exc

            except httpx.RequestError as exc:
                last_exc = RelaceNetworkError(f"Network error: {exc}")
                last_exc.__cause__ = exc
                logger.warning(
                    "[%s] Relace API network error: %s (attempt=%d/%d)",
                    trace_id,
                    exc,
                    attempt + 1,
                    MAX_RETRIES + 1,
                )
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2**attempt) + random.uniform(0, 0.5)  # nosec B311
                    time.sleep(delay)
                    continue
                raise last_exc from exc

        # Should not reach here, but as a fallback
        raise last_exc or RelaceServerError(
            RelaceErrorDetail(
                code=RelaceErrorCode.UNKNOWN,
                message=f"Failed after {MAX_RETRIES + 1} attempts",
                status_code=0,
                raw_response="",
            )
        )
