import logging
import time
from typing import Any, cast

import openai
from openai import AsyncOpenAI, OpenAI
from openai.types.chat import ChatCompletionMessageParam
from tenacity import RetryCallState, retry, stop_after_attempt, wait_exponential

from ..config.provider import ProviderConfig
from ..config.settings import MAX_RETRIES, RETRY_BASE_DELAY

logger = logging.getLogger(__name__)


def _should_retry(retry_state: RetryCallState) -> bool:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if exc is None:
        return False
    if isinstance(exc, openai.RateLimitError):
        return True
    # Use a tuple for Python 3.11/3.12 compatibility (PEP 604 unions in isinstance
    # are only supported in newer Python versions).
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code >= 500
    return False


class OpenAIChatClient:
    """OpenAI-compatible chat client with retry logic."""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._model = config.model

        self._sync_client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            max_retries=0,  # We handle retries with tenacity
        )
        self._async_client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            max_retries=0,
        )

    @retry(
        stop=stop_after_attempt(MAX_RETRIES + 1),
        wait=wait_exponential(multiplier=RETRY_BASE_DELAY, max=60),
        retry=_should_retry,
        reraise=True,
    )
    def chat_completions(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float,
        extra_body: dict[str, Any] | None = None,
        trace_id: str = "unknown",
    ) -> tuple[dict[str, Any], float]:
        """Send synchronous chat completion request with automatic retry.

        Args:
            messages: List of chat messages.
            temperature: Sampling temperature (0.0-2.0).
            extra_body: Additional request parameters.
            trace_id: Request identifier for logging.

        Returns:
            Tuple of (response dict, latency in ms).

        Raises:
            openai.APIError: API call failed after retries.
        """
        start = time.perf_counter()
        try:
            response = self._sync_client.chat.completions.create(
                model=self._model,
                messages=cast(list[ChatCompletionMessageParam], messages),
                temperature=temperature,
                extra_body=extra_body,
            )
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.debug("[%s] chat_completions ok (latency=%.1fms)", trace_id, latency_ms)
            return response.model_dump(), latency_ms
        except openai.APIError as exc:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.warning(
                "[%s] chat_completions error: %s (latency=%.1fms)",
                trace_id,
                exc,
                latency_ms,
            )
            raise

    @retry(
        stop=stop_after_attempt(MAX_RETRIES + 1),
        wait=wait_exponential(multiplier=RETRY_BASE_DELAY, max=60),
        retry=_should_retry,
        reraise=True,
    )
    async def chat_completions_async(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float,
        extra_body: dict[str, Any] | None = None,
        trace_id: str = "unknown",
    ) -> tuple[dict[str, Any], float]:
        """Send asynchronous chat completion request with automatic retry.

        Args:
            messages: List of chat messages.
            temperature: Sampling temperature (0.0-2.0).
            extra_body: Additional request parameters.
            trace_id: Request identifier for logging.

        Returns:
            Tuple of (response dict, latency in ms).

        Raises:
            openai.APIError: API call failed after retries.
        """
        start = time.perf_counter()
        try:
            response = await self._async_client.chat.completions.create(
                model=self._model,
                messages=cast(list[ChatCompletionMessageParam], messages),
                temperature=temperature,
                extra_body=extra_body,
            )
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.debug("[%s] chat_completions_async ok (latency=%.1fms)", trace_id, latency_ms)
            return response.model_dump(), latency_ms
        except openai.APIError as exc:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.warning(
                "[%s] chat_completions_async error: %s (latency=%.1fms)",
                trace_id,
                exc,
                latency_ms,
            )
            raise
