import logging
import random
import time
from typing import Any

import httpx

from .config import (
    MAX_RETRIES,
    RELACE_ENDPOINT,
    RELACE_MODEL,
    RETRY_BASE_DELAY,
    TIMEOUT_SECONDS,
    RelaceConfig,
)

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

                # 4xx: fail-fast，不 retry
                if 400 <= resp.status_code < 500:
                    logger.error(
                        "[%s] Relace API 4xx error (status=%d, latency=%dms)",
                        trace_id,
                        resp.status_code,
                        latency_ms,
                    )
                    raise RuntimeError(f"Relace API error (status {resp.status_code}): {resp.text}")

                # 5xx: 可 retry
                if resp.is_server_error:
                    logger.warning(
                        "[%s] Relace API 5xx error (status=%d, latency=%dms, attempt=%d/%d)",
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
                    raise RuntimeError(f"Relace API error (status {resp.status_code}): {resp.text}")

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
                    raise RuntimeError("Relace API returned non-JSON response") from exc

            except httpx.TimeoutException as exc:
                last_exc = exc
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
                raise RuntimeError(
                    f"Relace API request timed out after {TIMEOUT_SECONDS}s."
                ) from exc

            except httpx.RequestError as exc:
                last_exc = exc
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
                raise RuntimeError(f"Failed to call Relace API: {exc}") from exc

        raise RuntimeError(
            f"Failed to call Relace API after {MAX_RETRIES + 1} attempts"
        ) from last_exc
