import logging
import random
import time
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
from .exceptions import RelaceAPIError, RelaceNetworkError, RelaceTimeoutError, raise_for_status

logger = logging.getLogger(__name__)


class RelaceClient:
    def __init__(self, config: RelaceConfig) -> None:
        self._config = config

    def apply(
        self,
        initial_code: str,
        edit_snippet: str,
        instruction: str | None = None,
        relace_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """呼叫 Relace API 執行 Instant apply。

        Args:
            initial_code: 原始檔案內容。
            edit_snippet: 要套用的程式碼變更片段。
            instruction: 補充說明，用來協助 disambiguation。
            relace_metadata: 額外 metadata，會送到 Relace API 用於追蹤。

        Returns:
            Relace API 回傳的 JSON dict。

        Raises:
            RelaceAPIError: API 錯誤（不可重試的錯誤或重試 MAX_RETRIES 次後失敗）。
            RelaceNetworkError: 網路錯誤（已重試 MAX_RETRIES 次）。
            RelaceTimeoutError: 請求逾時（已重試 MAX_RETRIES 次）。
        """
        payload: dict[str, Any] = {
            "initial_code": initial_code,
            "edit_snippet": edit_snippet,
            "model": RELACE_MODEL,
            "stream": False,
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
                    raise_for_status(resp)
                except RelaceAPIError as exc:
                    if not exc.retryable:
                        # 不可重試的錯誤，直接拋出
                        logger.error(
                            "[%s] Relace API %s (status=%d, latency=%dms): %s",
                            trace_id,
                            exc.code,
                            resp.status_code,
                            latency_ms,
                            exc.message,
                        )
                        raise

                    # 可重試的錯誤 (429, 423, 5xx)
                    last_exc = exc
                    logger.warning(
                        "[%s] Relace API %s (status=%d, latency=%dms, attempt=%d/%d)",
                        trace_id,
                        exc.code,
                        resp.status_code,
                        latency_ms,
                        attempt + 1,
                        MAX_RETRIES + 1,
                    )
                    if attempt < MAX_RETRIES:
                        delay = exc.retry_after or RETRY_BASE_DELAY * (2**attempt)
                        delay += random.uniform(0, 0.5)  # nosec B311
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
                    raise RelaceAPIError(
                        status_code=resp.status_code,
                        code="application_error",
                        message="Relace API returned non-JSON response",
                        retryable=True,
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
        raise last_exc or RelaceAPIError(
            status_code=0,
            code="unknown",
            message=f"Failed after {MAX_RETRIES + 1} attempts",
            retryable=False,
        )
