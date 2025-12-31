import importlib
import logging
import re
import time
import uuid
from typing import Any

from ....backend import RELACE_PROVIDER
from ....clients import SearchLLMClient
from ....config import RelaceConfig
from ..handlers import estimate_context_size
from ..logging import (
    log_search_complete,
    log_search_error,
    log_search_start,
    log_search_turn,
)
from ..schemas import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_OPENAI,
    TURN_HINT_TEMPLATE,
    TURN_HINT_TEMPLATE_OPENAI,
    TURN_INSTRUCTIONS,
    TURN_INSTRUCTIONS_OPENAI,
    USER_PROMPT_TEMPLATE,
    USER_PROMPT_TEMPLATE_OPENAI,
    build_system_prompt,
    get_tool_schemas,
)
from .constants import (
    MAX_CONTEXT_BUDGET_CHARS,
    MAX_TOTAL_CONTEXT_CHARS,
)
from .messages import MessageHistoryMixin
from .observed import ObservedFilesMixin
from .tool_calls import ToolCallsMixin

logger = logging.getLogger(__name__)

_HARNESS_PACKAGE = __package__ or "relace_mcp.tools.search.harness"
_harness_mod = importlib.import_module(_HARNESS_PACKAGE)


class FastAgenticSearchHarness(ObservedFilesMixin, MessageHistoryMixin, ToolCallsMixin):
    """Fast Agentic Search Agent Harness.

    Responsible for executing the relace-search model's agent loop,
    processing tool calls and terminating upon receiving report_back.
    """

    def __init__(
        self,
        config: RelaceConfig,
        client: SearchLLMClient,
        *,
        lsp_languages: frozenset[str] | None = None,
    ) -> None:
        self._config = config
        self._client = client
        self._observed_files: dict[str, list[list[int]]] = {}
        self._view_line_re = re.compile(r"^(\d+)\s")
        self._lsp_languages = lsp_languages if lsp_languages is not None else frozenset()

        # Select base prompts based on API compatibility mode
        if client.api_compat == RELACE_PROVIDER:
            base_prompt = SYSTEM_PROMPT
            self._user_prompt_template = USER_PROMPT_TEMPLATE
            self._turn_hint_template = TURN_HINT_TEMPLATE
            self._turn_instructions = TURN_INSTRUCTIONS
        else:
            base_prompt = SYSTEM_PROMPT_OPENAI
            self._user_prompt_template = USER_PROMPT_TEMPLATE_OPENAI
            self._turn_hint_template = TURN_HINT_TEMPLATE_OPENAI
            self._turn_instructions = TURN_INSTRUCTIONS_OPENAI

        # Build dynamic system prompt with LSP language info
        self._system_prompt = build_system_prompt(base_prompt, self._lsp_languages)

    def _get_turn_hint(self, turn: int, max_turns: int, chars_used: int) -> str:
        """Generate turn status hint.

        Only shows urgency instruction on final turn.

        Args:
            turn: Current turn number (0-indexed internally, displayed as 1-indexed).
            max_turns: Maximum allowed turns.
            chars_used: Total characters used in context so far.
        """
        remaining = max_turns - turn
        mode = "final" if remaining == 1 else "normal"
        instruction = self._turn_instructions[mode]
        chars_pct = int((chars_used / MAX_CONTEXT_BUDGET_CHARS) * 100)

        return self._turn_hint_template.format(
            turn=turn + 1,
            max_turns=max_turns,
            chars_pct=chars_pct,
            instruction=instruction,
        )

    def run(self, query: str) -> dict[str, Any]:
        """Execute one Fast Agentic Search.

        Args:
            query: User query describing what to search/understand.

        Returns:
            Dict containing explanation and files:
            {
                "query": str,
                "explanation": str,
                "files": {path: [[start, end], ...]},
                "turns_used": int,
                "partial": bool,  # optional, True when error or max turns exceeded
                "error": str,  # optional, present when error occurred
            }

        Note:
            This method always returns a dict, never raises exceptions.
            When errors occur, returns a partial report with error field.
        """
        trace_id = str(uuid.uuid4())[:8]
        # Safe query truncation (avoid cutting in middle of multi-byte characters)
        query_preview = query[:100] if len(query) <= 100 else query[:97] + "..."
        logger.info("[%s] Starting Fast Agentic Search: %s", trace_id, query_preview)
        log_search_start(trace_id, query)
        start_time = time.perf_counter()

        # Reset observed_files (used to accumulate explored files)
        self._observed_files = {}

        try:
            result = self._run_search_loop(query, trace_id)
            total_ms = (time.perf_counter() - start_time) * 1000
            log_search_complete(
                trace_id,
                result.get("turns_used", 0),
                len(result.get("files", {})),
                result.get("partial", False),
                total_ms,
            )
            return result
        except Exception as exc:
            logger.error("[%s] Search failed with error: %s", trace_id, exc)
            log_search_error(trace_id, str(exc))
            merged_files = self._merge_observed_ranges()
            return {
                "query": query,
                "explanation": f"[ERROR] Search failed: {exc}",
                "files": merged_files,
                "turns_used": 0,
                "partial": True,
                "error": str(exc),
            }

    def _run_search_loop(self, query: str, trace_id: str) -> dict[str, Any]:
        """Internal method to execute the search loop."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": self._user_prompt_template.format(query=query)},
        ]

        for turn in range(_harness_mod.SEARCH_MAX_TURNS):
            logger.debug(
                "[%s] Turn %d/%d",
                trace_id,
                turn + 1,
                _harness_mod.SEARCH_MAX_TURNS,
            )

            # Inject unified turn hint (from turn 2 onwards)
            if turn > 0:
                chars_for_hint = estimate_context_size(messages)
                turn_hint = self._get_turn_hint(turn, _harness_mod.SEARCH_MAX_TURNS, chars_for_hint)
                messages.append({"role": "user", "content": turn_hint})
                logger.debug(
                    "[%s] Injected turn hint at turn %d (chars: %d/%d)",
                    trace_id,
                    turn + 1,
                    chars_for_hint,
                    MAX_CONTEXT_BUDGET_CHARS,
                )

            # Check context size AFTER all user messages are added
            ctx_size = estimate_context_size(messages)

            if ctx_size > MAX_TOTAL_CONTEXT_CHARS:
                logger.warning(
                    "[%s] Context size %d exceeds limit %d, truncating old messages",
                    trace_id,
                    ctx_size,
                    MAX_TOTAL_CONTEXT_CHARS,
                )
                # Keep system + user + most recent 6 messages
                messages = self._truncate_messages(messages)

            # Ensure tool_calls and tool results are paired correctly
            self._repair_tool_call_integrity(messages, trace_id)

            # Track LLM API latency
            llm_start = time.perf_counter()
            response = self._client.chat(
                messages, tools=get_tool_schemas(self._lsp_languages), trace_id=trace_id
            )
            llm_latency_ms = (time.perf_counter() - llm_start) * 1000

            # Parse response
            choices = response.get("choices", [])
            if not choices:
                name = self._client._chat_client.provider_display_name
                raise RuntimeError(f"{name} Search API returned empty choices")

            message = choices[0].get("message", {})
            # Defense: some providers/mocks may lack role, avoid breaking block/repair logic
            message.setdefault("role", "assistant")
            tool_calls = message.get("tool_calls", [])

            # Extract usage for token tracking
            usage = response.get("usage")

            # Log turn state after getting response (includes LLM latency and token usage)
            log_search_turn(
                trace_id,
                turn + 1,
                _harness_mod.SEARCH_MAX_TURNS,
                ctx_size,
                len(tool_calls),
                llm_latency_ms=llm_latency_ms,
                usage=usage,
            )

            # If no tool_calls, check for content (model may respond directly)
            if not tool_calls:
                content = message.get("content", "")
                content_preview = content[:200] if len(content) <= 200 else content[:197] + "..."
                logger.warning(
                    "[%s] No tool calls in turn %d, content: %s",
                    trace_id,
                    turn + 1,
                    content_preview,
                )
                # Add assistant message to context and continue
                messages.append({"role": "assistant", "content": content})
                continue

            # Add assistant message (with tool_calls) to messages
            messages.append(message)

            # Execute tool calls in parallel and collect results
            tool_results, report_back_result = self._execute_tools_parallel(
                tool_calls, trace_id, turn=turn + 1
            )

            # Add all tool results to messages (per OpenAI protocol)
            self._append_tool_results_to_messages(messages, tool_results)

            # After processing all tool calls, if report_back was called, return
            if report_back_result is not None:
                logger.info(
                    "[%s] Search completed in %d turns, found %d files",
                    trace_id,
                    turn + 1,
                    len(report_back_result.get("files", {})),
                )
                return {
                    "query": query,
                    "explanation": report_back_result.get("explanation", ""),
                    "files": self._normalize_report_files(report_back_result.get("files", {})),
                    "turns_used": turn + 1,
                }

        # Exceeded limit, return partial report (don't raise)
        logger.warning(
            "[%s] Search did not complete within %d turns, returning partial results",
            trace_id,
            _harness_mod.SEARCH_MAX_TURNS,
        )
        merged_files = self._merge_observed_ranges()
        return {
            "query": query,
            "explanation": (
                f"[PARTIAL] Search did not complete within {_harness_mod.SEARCH_MAX_TURNS} turns. "
                f"Returning {len(merged_files)} observed files based on exploration."
            ),
            "files": merged_files,
            "turns_used": _harness_mod.SEARCH_MAX_TURNS,
            "partial": True,
        }
