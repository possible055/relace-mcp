import logging
import random
import time
from typing import Any

import httpx

from ..config import (
    MAX_RETRIES,
    RELACE_SEARCH_ENDPOINT,
    RELACE_SEARCH_MODEL,
    RETRY_BASE_DELAY,
    SEARCH_TIMEOUT_SECONDS,
    RelaceConfig,
)
from .exceptions import RelaceAPIError, raise_for_status

logger = logging.getLogger(__name__)


class RelaceSearchClient:
    """OpenAI-compatible Chat Completions client for calling relace-search model."""

    def __init__(self, config: RelaceConfig) -> None:
        self._config = config

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        trace_id: str = "unknown",
    ) -> dict[str, Any]:
        """Send chat.completions request to relace-search endpoint.

        Args:
            messages: OpenAI-format messages list.
            tools: OpenAI function tools schema list.
            trace_id: Trace ID for logging.

        Returns:
            JSON dict returned by Relace Search API (OpenAI chat.completions format).

        Raises:
            RuntimeError: When API call fails (non-retryable error or retries exhausted).
        """
        payload: dict[str, Any] = {
            "model": RELACE_SEARCH_MODEL,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 100,
            "repetition_penalty": 1.0,
        }

        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }

        last_exc: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                started_at = time.monotonic()
                with httpx.Client(timeout=SEARCH_TIMEOUT_SECONDS) as client:
                    resp = client.post(RELACE_SEARCH_ENDPOINT, json=payload, headers=headers)
                latency_ms = int((time.monotonic() - started_at) * 1000)

                try:
                    raise_for_status(resp)
                except RelaceAPIError as exc:
                    if not exc.retryable:
                        # Non-retryable error (4xx except 429/423), raise immediately
                        logger.error(
                            "[%s] Relace Search API %s (status=%d, latency=%dms): %s",
                            trace_id,
                            exc.code,
                            resp.status_code,
                            latency_ms,
                            exc.message,
                        )
                        raise RuntimeError(
                            f"Relace Search API error ({exc.code}): {exc.message}"
                        ) from exc

                    # Retryable error (429, 423, 5xx)
                    last_exc = exc
                    logger.warning(
                        "[%s] Relace Search API %s (status=%d, latency=%dms, attempt=%d/%d)",
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
                    raise RuntimeError(
                        f"Relace Search API error ({exc.code}): {exc.message}"
                    ) from exc

                # Success
                logger.info(
                    "[%s] Relace Search API success (status=%d, latency=%dms)",
                    trace_id,
                    resp.status_code,
                    latency_ms,
                )

                try:
                    return resp.json()
                except ValueError as exc:
                    # 2xx but non-JSON is abnormal server behavior
                    logger.error(
                        "[%s] Relace Search API returned non-JSON response (status=%d)",
                        trace_id,
                        resp.status_code,
                    )
                    raise RuntimeError("Relace Search API returned non-JSON response") from exc

            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning(
                    "[%s] Relace Search API timeout after %.1fs (attempt=%d/%d)",
                    trace_id,
                    SEARCH_TIMEOUT_SECONDS,
                    attempt + 1,
                    MAX_RETRIES + 1,
                )
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2**attempt) + random.uniform(0, 0.5)  # nosec B311
                    time.sleep(delay)
                    continue
                raise RuntimeError(
                    f"Relace Search API request timed out after {SEARCH_TIMEOUT_SECONDS}s."
                ) from exc

            except httpx.RequestError as exc:
                last_exc = exc
                logger.warning(
                    "[%s] Relace Search API network error: %s (attempt=%d/%d)",
                    trace_id,
                    exc,
                    attempt + 1,
                    MAX_RETRIES + 1,
                )
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2**attempt) + random.uniform(0, 0.5)  # nosec B311
                    time.sleep(delay)
                    continue
                raise RuntimeError(f"Failed to call Relace Search API: {exc}") from exc

        raise RuntimeError(
            f"Failed to call Relace Search API after {MAX_RETRIES + 1} attempts"
        ) from last_exc
