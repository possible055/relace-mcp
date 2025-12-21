import logging
import os
from typing import Any

import openai

from ..backend import OPENAI_PROVIDER, OpenAIChatClient
from ..config import (
    RELACE_SEARCH_BASE_URL,
    RELACE_SEARCH_MODEL,
    SEARCH_TIMEOUT_SECONDS,
    RelaceConfig,
)

logger = logging.getLogger(__name__)


class RelaceSearchClient:
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

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        trace_id: str = "unknown",
    ) -> dict[str, Any]:
        extra_body: dict[str, Any] = {
            "tools": tools,
            "tool_choice": "auto",
            "top_p": 0.95,
        }

        # Relace Search supports additional sampling params; OpenAI rejects unknown fields.
        if self._chat_client.provider != OPENAI_PROVIDER:
            extra_body["top_k"] = 100
            extra_body["repetition_penalty"] = 1.0

        # Allow the model to emit multiple tool calls in a single turn for lower latency.
        if os.getenv("RELACE_SEARCH_PARALLEL_TOOL_CALLS", "1").strip().lower() in (
            "1",
            "true",
            "yes",
            "y",
            "on",
        ):
            extra_body["parallel_tool_calls"] = True

        try:
            data, _latency_ms = self._chat_client.chat_completions(
                messages=messages,
                temperature=1.0,
                extra_body=extra_body,
                trace_id=trace_id,
            )
            return data
        except openai.AuthenticationError as exc:
            raise RuntimeError(f"Relace Search API authentication error: {exc}") from exc
        except openai.RateLimitError as exc:
            raise RuntimeError(f"Relace Search API rate limit: {exc}") from exc
        except openai.APITimeoutError as exc:
            raise RuntimeError(
                f"Relace Search API request timed out after {SEARCH_TIMEOUT_SECONDS}s."
            ) from exc
        except openai.APIConnectionError as exc:
            raise RuntimeError(f"Failed to connect to Relace Search API: {exc}") from exc
        except openai.APIStatusError as exc:
            raise RuntimeError(
                f"Relace Search API error (status={exc.status_code}): {exc}"
            ) from exc
