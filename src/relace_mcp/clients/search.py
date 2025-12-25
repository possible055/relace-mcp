import logging
from typing import Any

import openai

from ..backend import RELACE_PROVIDER, OpenAIChatClient
from ..backend.openai_backend import _env_bool
from ..config import RelaceConfig
from ..config.settings import (
    RELACE_SEARCH_BASE_URL,
    RELACE_SEARCH_MODEL,
    SEARCH_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


def _strip_tool_strict(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stripped: list[dict[str, Any]] = []
    for tool in tools:
        tool_copy = dict(tool)
        func = tool_copy.get("function")
        if isinstance(func, dict) and "strict" in func:
            func_copy = dict(func)
            func_copy.pop("strict", None)
            tool_copy["function"] = func_copy
        stripped.append(tool_copy)
    return stripped


class SearchLLMClient:
    """Search client for Fast Agentic Search.

    Supports Relace and OpenAI-compatible providers (OpenAI, OpenRouter, Cerebras, etc.).

    Environment variables:
        RELACE_SEARCH_PROVIDER: Provider name (default: relace)
        RELACE_SEARCH_ENDPOINT: API base URL
        RELACE_SEARCH_MODEL: Model name
        RELACE_SEARCH_API_KEY: API key (or use provider-specific key)
        RELACE_SEARCH_PARALLEL_TOOL_CALLS: Enable parallel tool calls (default: true)
        RELACE_SEARCH_TOOL_STRICT: Include strict field in tool schemas (default: true)

    Note:
        When using OpenAI-compatible providers with strict=true, parallel_tool_calls
        is automatically disabled to comply with OpenAI Structured Outputs limitations.
    """

    def __init__(self, config: RelaceConfig) -> None:
        self._chat_client = OpenAIChatClient(
            config,
            provider_env="RELACE_SEARCH_PROVIDER",
            base_url_env="RELACE_SEARCH_ENDPOINT",
            model_env="RELACE_SEARCH_MODEL",
            default_base_url=RELACE_SEARCH_BASE_URL,
            default_model=RELACE_SEARCH_MODEL,
            timeout_seconds=SEARCH_TIMEOUT_SECONDS,
        )
        self._disable_relace_sampling = False
        self._disable_parallel_tool_calls = False
        self._strip_tool_strict = False

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        trace_id: str = "unknown",
    ) -> dict[str, Any]:
        if self._strip_tool_strict:
            tools = _strip_tool_strict(tools)

        include_relace_sampling = (
            self._chat_client.api_compat == RELACE_PROVIDER and not self._disable_relace_sampling
        )
        include_parallel_tool_calls = (
            _env_bool("RELACE_SEARCH_PARALLEL_TOOL_CALLS", default=True)
            and not self._disable_parallel_tool_calls
        )

        # OpenAI Structured Outputs 與 parallel_tool_calls 不相容
        # 當使用 OpenAI-compatible provider 且 tools 含 strict=true 時，自動禁用 parallel_tool_calls
        if self._chat_client.api_compat != RELACE_PROVIDER and include_parallel_tool_calls:
            tool_has_strict = any(
                isinstance(t, dict)
                and isinstance(t.get("function"), dict)
                and t.get("function", {}).get("strict")
                for t in tools
            )
            if tool_has_strict:
                logger.warning(
                    "[%s] OpenAI Structured Outputs does not support parallel_tool_calls "
                    "with strict=true. Disabling parallel_tool_calls for compatibility. "
                    "Set RELACE_SEARCH_PARALLEL_TOOL_CALLS=0 to suppress this warning.",
                    trace_id,
                )
                include_parallel_tool_calls = False

        extra_body: dict[str, Any] = {
            "tools": tools,
            "tool_choice": "auto",
            "top_p": 0.95,
        }

        if include_relace_sampling:
            extra_body["top_k"] = 100
            extra_body["repetition_penalty"] = 1.0

        if include_parallel_tool_calls:
            extra_body["parallel_tool_calls"] = True

        try:
            data, _latency_ms = self._chat_client.chat_completions(
                messages=messages,
                temperature=1.0,
                extra_body=extra_body,
                trace_id=trace_id,
            )
            return data
        except (openai.BadRequestError, openai.UnprocessableEntityError) as exc:
            try:
                retried = self._retry_compat_on_schema_error(
                    exc,
                    messages=messages,
                    tools=tools,
                    trace_id=trace_id,
                    include_relace_sampling=include_relace_sampling,
                    include_parallel_tool_calls=include_parallel_tool_calls,
                )
            except openai.APIError as retry_exc:
                name = self._chat_client.provider_display_name
                raise RuntimeError(
                    f"{name} Search API request failed after compatibility retry: {retry_exc}"
                ) from retry_exc
            if retried is not None:
                return retried
            name = self._chat_client.provider_display_name
            raise RuntimeError(f"{name} Search API request schema rejected: {exc}") from exc
        except openai.AuthenticationError as exc:
            name = self._chat_client.provider_display_name
            raise RuntimeError(f"{name} Search API authentication error: {exc}") from exc
        except openai.RateLimitError as exc:
            name = self._chat_client.provider_display_name
            raise RuntimeError(f"{name} Search API rate limit: {exc}") from exc
        except openai.APITimeoutError as exc:
            name = self._chat_client.provider_display_name
            raise RuntimeError(
                f"{name} Search API request timed out after {SEARCH_TIMEOUT_SECONDS}s."
            ) from exc
        except openai.APIConnectionError as exc:
            name = self._chat_client.provider_display_name
            raise RuntimeError(f"Failed to connect to {name} Search API: {exc}") from exc
        except openai.APIStatusError as exc:
            name = self._chat_client.provider_display_name
            if exc.status_code == 404:
                raise RuntimeError(
                    f"{name} Search API returned 404. If using an OpenAI-compatible endpoint, "
                    "set RELACE_SEARCH_ENDPOINT to the provider base URL (do not include "
                    "`/chat/completions`)."
                ) from exc
            raise RuntimeError(
                f"{name} Search API error (status={exc.status_code}): {exc}"
            ) from exc

    def _retry_compat_on_schema_error(
        self,
        exc: openai.APIStatusError,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        trace_id: str,
        include_relace_sampling: bool,
        include_parallel_tool_calls: bool,
    ) -> dict[str, Any] | None:
        had_strict = any(
            isinstance(t, dict)
            and isinstance(t.get("function"), dict)
            and "strict" in t.get("function", {})
            for t in tools
        )
        if not include_relace_sampling and not include_parallel_tool_calls and not had_strict:
            return None

        stripped_tools = _strip_tool_strict(tools)
        compat_body: dict[str, Any] = {
            "tools": stripped_tools,
            "tool_choice": "auto",
            "top_p": 0.95,
        }

        logger.warning(
            "[%s] Request rejected (status=%s, provider=%s, api_compat=%s). Retrying with "
            "compatibility payload (no relace sampling params, no parallel_tool_calls, "
            "no strict tool fields). Error: %s",
            trace_id,
            exc.status_code,
            self._chat_client.provider,
            self._chat_client.api_compat,
            exc,
        )
        data, _latency_ms = self._chat_client.chat_completions(
            messages=messages,
            temperature=1.0,
            extra_body=compat_body,
            trace_id=f"{trace_id}:compat",
        )
        if include_relace_sampling:
            self._disable_relace_sampling = True
        if include_parallel_tool_calls:
            self._disable_parallel_tool_calls = True
        if had_strict:
            self._strip_tool_strict = True
        return data
