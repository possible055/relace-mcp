import json
import logging
import os
import time
from typing import Any, cast

import openai
from openai import AsyncOpenAI, OpenAI
from openai.types.chat import ChatCompletionMessageParam
from tenacity import RetryCallState, retry, stop_after_attempt, wait_exponential

from ..config import RelaceConfig
from ..config.settings import MAX_RETRIES, RETRY_BASE_DELAY

logger = logging.getLogger(__name__)

OPENAI_PROVIDER = "openai"
RELACE_PROVIDER = "relace"

_TRUTHY = {"1", "true", "yes", "y", "on"}
_FALSY = {"0", "false", "no", "n", "off"}

_DEFAULT_BASE_URLS: dict[str, str] = {
    OPENAI_PROVIDER: "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "cerebras": "https://api.cerebras.ai/v1",
}


def _normalize_base_url(base_url: str) -> str:
    base_url = base_url.strip()
    if not base_url:
        return base_url

    base_url = base_url.rstrip("/")
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")].rstrip("/")
    return base_url


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    logger.warning("Invalid %s=%r; expected boolean, defaulting to %s", name, raw, default)
    return default


def _load_json_dict_env(name: str) -> dict[str, str] | None:
    raw = os.getenv(name)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{name} must be valid JSON object, got invalid JSON: {exc}") from exc

    if not isinstance(parsed, dict) or any(not isinstance(k, str) for k in parsed):
        raise RuntimeError(f"{name} must be a JSON object with string keys")

    headers: dict[str, str] = {}
    for key, value in parsed.items():
        if value is None:
            continue
        if not isinstance(value, str):
            headers[key] = str(value)
        else:
            headers[key] = value
    return headers


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
        self._provider = os.getenv(provider_env, RELACE_PROVIDER).strip().lower()
        prefix = (
            provider_env.removesuffix("_PROVIDER") if provider_env.endswith("_PROVIDER") else ""
        )

        compat_env = f"{prefix}_API_COMPAT" if prefix else ""
        compat_raw = os.getenv(compat_env, "").strip().lower() if compat_env else ""
        if compat_raw in (OPENAI_PROVIDER, RELACE_PROVIDER):
            self._api_compat = compat_raw
        elif compat_raw:
            raise RuntimeError(f"{compat_env} must be '{OPENAI_PROVIDER}' or '{RELACE_PROVIDER}'")
        else:
            self._api_compat = (
                RELACE_PROVIDER if self._provider == RELACE_PROVIDER else OPENAI_PROVIDER
            )

        base_url = os.getenv(base_url_env, "").strip()
        if not base_url:
            base_url = _DEFAULT_BASE_URLS.get(self._provider, default_base_url)
        base_url = _normalize_base_url(base_url)

        self._model = os.getenv(model_env, "").strip() or (
            "gpt-4o" if self._provider == OPENAI_PROVIDER else default_model
        )

        # 驗證 provider/model 組合合理性
        if self._provider != RELACE_PROVIDER and self._model.startswith("relace-"):
            raise RuntimeError(
                f"Model '{self._model}' appears to be a Relace-specific model, "
                f"but provider is set to '{self._provider}'. "
                f"Please set {model_env} to a model supported by your provider."
            )

        api_key = ""
        api_key_env = f"{prefix}_API_KEY" if prefix else ""
        api_key_env_env = f"{prefix}_API_KEY_ENV" if prefix else ""

        if api_key_env:
            api_key = os.getenv(api_key_env, "").strip()

        if not api_key and api_key_env_env:
            indirect_env = os.getenv(api_key_env_env, "").strip()
            if indirect_env:
                api_key = os.getenv(indirect_env, "").strip()
                if not api_key:
                    raise RuntimeError(f"{api_key_env_env} points to unset env var: {indirect_env}")

        if not api_key:
            if self._api_compat == RELACE_PROVIDER:
                api_key = config.api_key
            elif self._provider == OPENAI_PROVIDER:
                api_key = os.getenv("OPENAI_API_KEY", "").strip()
                if not api_key:
                    raise RuntimeError(f"OPENAI_API_KEY is not set when {provider_env}=openai.")
            else:
                derived_env = "".join(
                    ch if ch.isalnum() else "_" for ch in self._provider.upper()
                ).strip("_")
                derived_env = f"{derived_env}_API_KEY" if derived_env else ""
                if derived_env:
                    api_key = os.getenv(derived_env, "").strip()

                if not api_key:
                    raise RuntimeError(
                        f"No API key found for {provider_env}={self._provider}. "
                        f"Set {api_key_env} (recommended) or {api_key_env_env}, "
                        f"or export {derived_env}."
                    )

        default_headers = None
        if prefix:
            headers_env = f"{prefix}_HEADERS"
            default_headers = _load_json_dict_env(headers_env)

        self._sync_client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,  # We handle retries with tenacity
            default_headers=default_headers,
        )
        self._async_client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,
            default_headers=default_headers,
        )

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def api_compat(self) -> str:
        return self._api_compat

    @property
    def provider_display_name(self) -> str:
        """Human-readable provider name for error messages."""
        if self._provider == RELACE_PROVIDER:
            return "Relace"
        return self._provider.replace("_", " ").title()

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
