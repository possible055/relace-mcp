import logging
import os
import time
from typing import Any, cast

import openai
from openai import AsyncOpenAI, OpenAI
from openai.types.chat import ChatCompletionMessageParam
from tenacity import RetryCallState, retry, stop_after_attempt, wait_exponential

from ..config import MAX_RETRIES, RETRY_BASE_DELAY, RelaceConfig

logger = logging.getLogger(__name__)

OPENAI_PROVIDER = "openai"


def _should_retry(retry_state: RetryCallState) -> bool:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if exc is None:
        return False
    if isinstance(exc, openai.RateLimitError):
        return True
    if isinstance(exc, openai.APIConnectionError | openai.APITimeoutError):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code >= 500
    return False


class OpenAIChatClient:
    """OpenAI-compatible chat client with retry logic for Relace and OpenAI endpoints."""

    def __init__(
        self,
        config: RelaceConfig,
        *,
        provider_env: str,
        base_url_env: str,
        model_env: str,
        default_base_url: str,
        default_model: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._provider = os.getenv(provider_env, "relace").strip().lower()

        base_url = os.getenv(base_url_env, "").strip() or (
            "https://api.openai.com/v1" if self._provider == OPENAI_PROVIDER else default_base_url
        )
        self._model = os.getenv(model_env, "").strip() or (
            "gpt-4o" if self._provider == OPENAI_PROVIDER else default_model
        )

        if self._provider == OPENAI_PROVIDER:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError(f"OPENAI_API_KEY is not set when {provider_env}=openai.")
        else:
            api_key = config.api_key

        self._sync_client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,  # We handle retries with tenacity
        )
        self._async_client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,
        )

    @property
    def provider(self) -> str:
        return self._provider

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
        temperature: float = 1.0,
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
        temperature: float = 1.0,
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
