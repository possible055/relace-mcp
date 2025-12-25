import logging
from dataclasses import dataclass, field
from typing import Any

from ..backend import RELACE_PROVIDER, OpenAIChatClient
from ..config import APPLY_SYSTEM_PROMPT, RelaceConfig
from ..config.settings import (
    RELACE_APPLY_BASE_URL,
    RELACE_APPLY_MODEL,
    TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


@dataclass
class ApplyRequest:
    initial_code: str
    edit_snippet: str
    instruction: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ApplyResponse:
    merged_code: str
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0


class ApplyLLMClient:
    """LLM-based client for code merging (Instant Apply).

    Supports Relace and OpenAI-compatible providers (OpenAI, OpenRouter, Cerebras, etc.).

    Environment variables:
        RELACE_APPLY_PROVIDER: Provider name (default: relace)
        RELACE_APPLY_ENDPOINT: API base URL
        RELACE_APPLY_MODEL: Model name
        RELACE_APPLY_API_KEY: API key (or use provider-specific key)
    """

    def __init__(self, config: RelaceConfig) -> None:
        self._chat_client = OpenAIChatClient(
            config,
            provider_env="RELACE_APPLY_PROVIDER",
            base_url_env="RELACE_APPLY_ENDPOINT",
            model_env="RELACE_APPLY_MODEL",
            default_base_url=RELACE_APPLY_BASE_URL,
            default_model=RELACE_APPLY_MODEL,
            timeout_seconds=TIMEOUT_SECONDS,
        )
        # Cache api_compat for conditional system prompt injection
        self._api_compat = self._chat_client.api_compat

    async def apply(self, request: ApplyRequest) -> ApplyResponse:
        """Call Relace Instant Apply API to merge edit_snippet into initial_code.

        Args:
            request: Request containing initial_code, edit_snippet, and optional instruction.

        Returns:
            ApplyResponse with merged_code, usage stats, and latency_ms.

        Raises:
            ValueError: Cannot parse merged code from API response.
            openai.APIError: API call failed (rate limit, timeout, etc.).
        """
        messages = self._build_messages(request)
        trace_id = request.metadata.get("trace_id", "unknown")

        data, latency_ms = await self._chat_client.chat_completions_async(
            messages=messages,
            temperature=0.0,
            trace_id=trace_id,
        )

        merged_code = self._extract_merged_code(data)
        usage = data.get("usage", {})

        return ApplyResponse(
            merged_code=merged_code,
            usage=usage,
            latency_ms=latency_ms,
        )

    def _build_messages(self, request: ApplyRequest) -> list[dict[str, Any]]:
        instruction = (request.instruction or "").strip()
        parts: list[str] = []
        if instruction:
            parts.append(f"<instruction>{instruction}</instruction>")
        parts.append(f"<code>{request.initial_code}</code>")
        parts.append(f"<update>{request.edit_snippet}</update>")
        user_message = "\n".join(parts)

        messages: list[dict[str, Any]] = []
        # Only inject system prompt for OpenAI-compatible endpoints
        # Relace native API has built-in system prompt, no need to inject
        if self._api_compat != RELACE_PROVIDER:
            messages.append({"role": "system", "content": APPLY_SYSTEM_PROMPT})
        messages.append({"role": "user", "content": user_message})
        return messages

    def _extract_merged_code(self, data: dict[str, Any]) -> str:
        choices = data.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content")
            if isinstance(content, str):
                stripped = content.strip()
                if stripped.startswith("```") and stripped.endswith("```"):
                    lines = stripped.splitlines()
                    if lines and lines[0].lstrip().startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    cleaned = "\n".join(lines)
                    if content.endswith("\n") and not cleaned.endswith("\n"):
                        cleaned += "\n"
                    return cleaned
                return content

        raise ValueError("Cannot extract merged code from response")
