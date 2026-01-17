import asyncio
import logging
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .....clients import SearchLLMClient
from .....config import RelaceConfig
from ..._impl import estimate_context_size
from ...logging import log_search_turn
from ...schemas import get_tool_schemas
from ..constants import MAX_CONTEXT_BUDGET_CHARS, MAX_TOTAL_CONTEXT_CHARS
from ..messages import MessageHistoryMixin
from ..observed import ObservedFilesMixin
from ..tool_calls import ToolCallsMixin
from .channel_prompts import (
    CHANNEL_TURN_HINT_TEMPLATE,
    CHANNEL_TURN_INSTRUCTIONS,
    CHANNEL_USER_PROMPT_TEMPLATE,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

CHANNEL_CONTEXT_BUDGET = MAX_CONTEXT_BUDGET_CHARS // 2  # 80K chars per channel


@dataclass
class ChannelEvidence:
    """Evidence collected by a single search channel."""

    files: dict[str, list[list[int]]]
    observations: list[str] = field(default_factory=list)
    turns_used: int = 0
    partial: bool = False
    error: str | None = None


class BaseChannelHarness(ObservedFilesMixin, MessageHistoryMixin, ToolCallsMixin):
    """Base class for channel-specific search harnesses.

    Subclasses must define:
        CHANNEL_NAME: Identifier for logging
        ALLOWED_TOOLS: Tool names this channel can use
        CHANNEL_SYSTEM_PROMPT: System prompt for this channel
    """

    CHANNEL_NAME: str = "base"
    ALLOWED_TOOLS: frozenset[str] = frozenset()
    CHANNEL_SYSTEM_PROMPT: str = ""

    def __init__(
        self,
        config: RelaceConfig,
        client: SearchLLMClient,
        *,
        max_turns: int = 3,
        lsp_languages: frozenset[str] | None = None,
    ) -> None:
        self._config = config
        self._client = client
        self._max_turns = max_turns
        self._lsp_languages = lsp_languages if lsp_languages is not None else frozenset()
        self._observed_files: dict[str, list[list[int]]] = {}
        self._view_line_re = re.compile(r"^(\d+)\s")

        # Channels use dedicated prompts (no report_back)
        self._user_prompt_template = CHANNEL_USER_PROMPT_TEMPLATE
        self._turn_hint_template = CHANNEL_TURN_HINT_TEMPLATE
        self._turn_instructions = CHANNEL_TURN_INSTRUCTIONS

    def _enabled_tool_names(self) -> set[str]:
        """Return allowed tools for this channel.

        Intersects channel's ALLOWED_TOOLS with the global schema allowlist
        (honors SEARCH_ENABLED_TOOLS env var for defense-in-depth).
        """
        schema_enabled: set[str] = set()
        for schema in get_tool_schemas(self._lsp_languages):
            func = schema.get("function")
            if isinstance(func, dict):
                name = func.get("name")
                if isinstance(name, str):
                    schema_enabled.add(name)
        return set(self.ALLOWED_TOOLS) & schema_enabled

    def _get_tool_schemas(self) -> list[dict[str, Any]]:
        """Get tool schemas filtered to this channel's allowed tools."""
        all_schemas = get_tool_schemas(self._lsp_languages)
        return [s for s in all_schemas if s.get("function", {}).get("name") in self.ALLOWED_TOOLS]

    def _get_turn_hint(self, turn: int, chars_used: int) -> str:
        remaining = self._max_turns - turn
        mode = "final" if remaining == 1 else "normal"
        instruction = self._turn_instructions[mode]
        chars_pct = int((chars_used / CHANNEL_CONTEXT_BUDGET) * 100)
        return self._turn_hint_template.format(
            turn=turn + 1,
            max_turns=self._max_turns,
            chars_pct=chars_pct,
            instruction=instruction,
        )

    def run(self, query: str) -> ChannelEvidence:
        """Execute channel search synchronously."""
        trace_id = f"{self.CHANNEL_NAME}-{uuid.uuid4().hex[:6]}"
        logger.info("Starting channel")

        self._observed_files = {}

        try:
            return self._run_channel_loop(query, trace_id)
        except Exception as exc:
            logger.exception("Channel failed")
            return ChannelEvidence(
                files=self._merge_observed_ranges(),
                observations=[f"Error: {exc}"],
                turns_used=0,
                partial=True,
                error=str(exc),
            )

    async def run_async(self, query: str) -> ChannelEvidence:
        """Execute channel search asynchronously."""
        trace_id = f"{self.CHANNEL_NAME}-{uuid.uuid4().hex[:6]}"
        logger.info("Starting channel async")

        self._observed_files = {}

        try:
            return await self._run_channel_loop_async(query, trace_id)
        except Exception as exc:
            logger.exception("Channel failed")
            return ChannelEvidence(
                files=self._merge_observed_ranges(),
                observations=[f"Error: {exc}"],
                turns_used=0,
                partial=True,
                error=str(exc),
            )

    def _run_channel_loop(self, query: str, trace_id: str) -> ChannelEvidence:
        """Synchronous channel loop."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.CHANNEL_SYSTEM_PROMPT},
            {"role": "user", "content": self._user_prompt_template.format(query=query)},
        ]

        tool_schemas = self._get_tool_schemas()
        actual_turns = 0

        for turn in range(self._max_turns):
            actual_turns = turn + 1

            if turn > 0:
                chars_for_hint = estimate_context_size(messages)
                turn_hint = self._get_turn_hint(turn, chars_for_hint)
                messages.append({"role": "user", "content": turn_hint})

            ctx_size = estimate_context_size(messages)
            if ctx_size > MAX_TOTAL_CONTEXT_CHARS // 2:
                messages = self._truncate_messages(messages)

            self._repair_tool_call_integrity(messages, trace_id)

            llm_start = time.perf_counter()
            response = self._client.chat(messages, tools=tool_schemas, trace_id=trace_id)
            llm_latency_ms = (time.perf_counter() - llm_start) * 1000

            choices = response.get("choices", [])
            if not choices:
                break

            message = choices[0].get("message", {})
            message.setdefault("role", "assistant")
            tool_calls = message.get("tool_calls") or []

            usage = response.get("usage")
            log_search_turn(
                trace_id,
                turn + 1,
                self._max_turns,
                ctx_size,
                len(tool_calls),
                llm_latency_ms=llm_latency_ms,
                usage=usage,
            )

            if not tool_calls:
                content = message.get("content") or ""
                messages.append({"role": "assistant", "content": content})
                continue

            messages.append(self._sanitize_assistant_message(message))
            tool_results, _ = self._execute_tools_parallel(tool_calls, trace_id, turn=turn + 1)
            self._append_tool_results_to_messages(messages, tool_results)

        return ChannelEvidence(
            files=self._merge_observed_ranges(),
            observations=self._extract_observations(messages),
            turns_used=actual_turns,
        )

    async def _run_channel_loop_async(self, query: str, trace_id: str) -> ChannelEvidence:
        """Asynchronous channel loop."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.CHANNEL_SYSTEM_PROMPT},
            {"role": "user", "content": self._user_prompt_template.format(query=query)},
        ]

        tool_schemas = self._get_tool_schemas()
        loop = asyncio.get_running_loop()
        actual_turns = 0

        with ThreadPoolExecutor(max_workers=1) as executor:
            for turn in range(self._max_turns):
                actual_turns = turn + 1

                if turn > 0:
                    chars_for_hint = estimate_context_size(messages)
                    turn_hint = self._get_turn_hint(turn, chars_for_hint)
                    messages.append({"role": "user", "content": turn_hint})

                ctx_size = estimate_context_size(messages)
                if ctx_size > MAX_TOTAL_CONTEXT_CHARS // 2:
                    messages = self._truncate_messages(messages)

                self._repair_tool_call_integrity(messages, trace_id)

                llm_start = time.perf_counter()
                response = await self._client.chat_async(
                    messages, tools=tool_schemas, trace_id=trace_id
                )
                llm_latency_ms = (time.perf_counter() - llm_start) * 1000

                choices = response.get("choices", [])
                if not choices:
                    break

                message = choices[0].get("message", {})
                message.setdefault("role", "assistant")
                tool_calls = message.get("tool_calls") or []

                usage = response.get("usage")
                log_search_turn(
                    trace_id,
                    turn + 1,
                    self._max_turns,
                    ctx_size,
                    len(tool_calls),
                    llm_latency_ms=llm_latency_ms,
                    usage=usage,
                )

                if not tool_calls:
                    content = message.get("content") or ""
                    messages.append({"role": "assistant", "content": content})
                    continue

                messages.append(self._sanitize_assistant_message(message))
                tool_results, _ = await loop.run_in_executor(
                    executor, self._execute_tools_parallel, tool_calls, trace_id, turn + 1
                )
                self._append_tool_results_to_messages(messages, tool_results)

        return ChannelEvidence(
            files=self._merge_observed_ranges(),
            observations=self._extract_observations(messages),
            turns_used=actual_turns,
        )

    def _extract_observations(self, messages: list[dict[str, Any]]) -> list[str]:
        """Extract key observations from assistant messages."""
        observations: list[str] = []
        for msg in messages:
            if msg.get("role") == "assistant":
                content = msg.get("content")
                if content and isinstance(content, str) and len(content) > 20:
                    observations.append(content[:500])
        return observations[-3:]
