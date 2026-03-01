import asyncio
import logging
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ....clients.search import SearchLLMClient

from ....config import RelaceConfig, load_prompt_file
from ....config.settings import RELACE_PROVIDER, SEARCH_MAX_TURNS, SEARCH_TIMEOUT_SECONDS
from .._impl import estimate_context_size
from ..logging import (
    log_search_complete,
    log_search_error,
    log_search_start,
    log_search_turn,
)
from ..schemas import (
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

# YAML file selection: (tool_kind, backend) -> file stem
_PROMPT_FILES = {
    ("search", "relace"): "search_relace",
    ("search", "openai"): "search_openai",
    ("retrieval", "relace"): "retrieval_relace",
    ("retrieval", "openai"): "retrieval_openai",
}


class FastAgenticSearchHarness(ObservedFilesMixin, MessageHistoryMixin, ToolCallsMixin):
    """Fast Agentic Search Agent Harness.

    Responsible for executing the relace-search model's agent loop,
    processing tool calls and terminating upon receiving report_back.
    """

    def __init__(
        self,
        config: RelaceConfig,
        client: "SearchLLMClient",
        *,
        lsp_languages: frozenset[str] | None = None,
        user_prompt_override: str | None = None,
        retrieval: bool = False,
        trace: bool = False,
    ) -> None:
        self._config = config
        self._trace = trace
        self._client = client
        self._observed_files: dict[str, list[list[int]]] = {}
        self._view_line_re = re.compile(r"^(\d+)\s")
        self._lsp_languages = lsp_languages if lsp_languages is not None else frozenset()
        self._user_prompt_override = user_prompt_override

        # Resolve enabled tools first (runtime LSP detection happens here)
        enabled_tools = self._enabled_tool_names()
        _lsp_tool_names = {"find_symbol", "search_symbol", "get_type", "list_symbols", "call_graph"}
        has_lsp = bool(enabled_tools & _lsp_tool_names)

        # Select prompt YAML: (tool_kind, backend) → file stem
        tool_kind = "retrieval" if retrieval else "search"
        backend = "relace" if client.api_compat == RELACE_PROVIDER else "openai"
        prompt_name = _PROMPT_FILES[(tool_kind, backend)]
        prompts = load_prompt_file(prompt_name)

        self._user_prompt_template = prompts["user_prompt_template"].strip()
        self._turn_hint_template = prompts["turn_hint_template"].strip()
        self._turn_instructions = prompts["turn_instructions"]

        self._system_prompt = build_system_prompt(
            prompts["system_prompt"],
            enabled_tools=enabled_tools,
            has_lsp=has_lsp,
            lsp_section=prompts.get("lsp_section", ""),
        )

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

        return str(self._turn_hint_template).format(
            turn=turn + 1,
            max_turns=max_turns,
            chars_pct=chars_pct,
            instruction=instruction,
        )

    def run(
        self, query: str, semantic_hints_section: str = "", *, trace_id: str | None = None
    ) -> dict[str, Any]:
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
                "trace_id": str,
            }

        Note:
            This method always returns a dict, never raises exceptions.
            When errors occur, returns a partial report with error field.
        """
        tid = trace_id or str(uuid.uuid4())[:8]
        # Safe query truncation (avoid cutting in middle of multi-byte characters)
        logger.debug("[%s] Starting Fast Agentic Search (query_len=%d)", tid, len(query))
        log_search_start(tid, query)
        start_time = time.perf_counter()

        # Reset observed_files (used to accumulate explored files)
        self._observed_files = {}

        try:
            result = self._run_search_loop(
                query,
                tid,
                start_time=start_time,
                semantic_hints_section=semantic_hints_section,
            )
            result["trace_id"] = tid
            total_ms = (time.perf_counter() - start_time) * 1000
            log_search_complete(
                tid,
                result.get("turns_used", 0),
                len(result.get("files", {})),
                result.get("partial", False),
                total_ms,
            )
            return result
        except Exception as exc:
            logger.exception("[%s] Search failed with error", tid)
            log_search_error(tid, str(exc))
            merged_files = self._merge_observed_ranges()
            return {
                "query": query,
                "explanation": f"[ERROR] Search failed: {exc}",
                "files": merged_files,
                "turns_used": 0,
                "partial": True,
                "error": str(exc),
                "trace_id": tid,
            }

    async def run_async(
        self, query: str, semantic_hints_section: str = "", *, trace_id: str | None = None
    ) -> dict[str, Any]:
        """Execute one Fast Agentic Search asynchronously.

        Note:
            This method always returns a dict, never raises exceptions.
            When errors occur, returns a partial report with error field.
        """
        tid = trace_id or str(uuid.uuid4())[:8]
        # Safe query truncation (avoid cutting in middle of multi-byte characters)
        query_preview = query[:100] if len(query) <= 100 else query[:97] + "..."
        # Sanitize preview for log injection safety (remove newlines and control chars)
        query_preview = query_preview.replace("\n", " ").replace("\r", " ")
        logger.debug(
            "[%s] Starting Fast Agentic Search async (query_len=%d, preview=%s)",
            tid,
            len(query),
            query_preview,
        )
        log_search_start(tid, query)
        start_time = time.perf_counter()

        # Reset observed_files (used to accumulate explored files)
        self._observed_files = {}

        try:
            result = await self._run_search_loop_async(
                query,
                tid,
                start_time=start_time,
                semantic_hints_section=semantic_hints_section,
            )
            result["trace_id"] = tid
            total_ms = (time.perf_counter() - start_time) * 1000
            log_search_complete(
                tid,
                result.get("turns_used", 0),
                len(result.get("files", {})),
                result.get("partial", False),
                total_ms,
            )
            return result
        except Exception as exc:
            logger.exception("[%s] Search failed with error", tid)
            log_search_error(tid, str(exc))
            merged_files = self._merge_observed_ranges()
            return {
                "query": query,
                "explanation": f"[ERROR] Search failed: {exc}",
                "files": merged_files,
                "turns_used": 0,
                "partial": True,
                "error": str(exc),
                "trace_id": tid,
            }

    def _run_search_loop(
        self,
        query: str,
        trace_id: str,
        *,
        start_time: float,
        semantic_hints_section: str = "",
    ) -> dict[str, Any]:
        """Internal method to execute the search loop."""
        user_content = (
            self._user_prompt_override
            if self._user_prompt_override
            else self._user_prompt_template.format(
                query=query,
                semantic_hints_section=semantic_hints_section,
            )
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_content},
        ]

        turns_log: list[dict[str, Any]] = []

        for turn in range(SEARCH_MAX_TURNS):
            if (time.perf_counter() - start_time) > SEARCH_TIMEOUT_SECONDS:
                merged_files = self._merge_observed_ranges()
                result_dict = {
                    "query": query,
                    "explanation": (
                        f"[PARTIAL] Search exceeded SEARCH_TIMEOUT_SECONDS={SEARCH_TIMEOUT_SECONDS}s. "
                        f"Returning {len(merged_files)} observed files based on exploration."
                    ),
                    "files": merged_files,
                    "turns_used": turn,
                    "partial": True,
                    "error": f"Search timed out after {SEARCH_TIMEOUT_SECONDS}s",
                }
                if self._trace:
                    result_dict["turns_log"] = turns_log
                return result_dict
            logger.debug(
                "[%s] Turn %d/%d",
                trace_id,
                turn + 1,
                SEARCH_MAX_TURNS,
            )

            # Inject unified turn hint (from turn 2 onwards)
            if turn > 0:
                chars_for_hint = estimate_context_size(messages)
                turn_hint = self._get_turn_hint(turn, SEARCH_MAX_TURNS, chars_for_hint)
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
                name = self._client._provider_config.display_name
                raise RuntimeError(f"{name} Search API returned empty choices")

            message = choices[0].get("message", {})
            # Defense: some providers/mocks may lack role, avoid breaking block/repair logic
            message.setdefault("role", "assistant")
            tool_calls = message.get("tool_calls") or []

            # Debug: log actual tool call names returned by model
            tc_names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
            logger.debug(
                "[%s] Turn %d: %d tool_calls returned: %s",
                trace_id,
                turn + 1,
                len(tool_calls),
                tc_names,
            )

            # Extract usage for token tracking
            usage = response.get("usage")

            # Log turn state after getting response (includes LLM latency and token usage)
            log_search_turn(
                trace_id,
                turn + 1,
                SEARCH_MAX_TURNS,
                ctx_size,
                len(tool_calls),
                llm_latency_ms=llm_latency_ms,
                usage=usage,
            )

            # If no tool_calls, check for content (model may respond directly)
            if not tool_calls:
                content = message.get("content") or ""
                logger.warning(
                    "[%s] No tool calls in turn %d (content_len=%d)",
                    trace_id,
                    turn + 1,
                    len(content),
                )
                # Add assistant message to context and continue
                messages.append({"role": "assistant", "content": content})
                if self._trace:
                    trace_entry: dict[str, Any] = {
                        "turn": turn + 1,
                        "llm_latency_ms": round(llm_latency_ms, 1),
                        "llm_response": response,
                        "tool_calls_raw": [],
                        "tool_results": [],
                        "report_back": None,
                    }
                    turns_log.append(trace_entry)
                continue

            # Guardrail: detect report_back mixed with other tools
            tool_calls, message, mixed_rb_ids = self._strip_mixed_report_back(
                tool_calls, message, trace_id
            )

            # Add assistant message (with tool_calls) to messages
            messages.append(self._sanitize_assistant_message(message))

            # Execute tool calls in parallel and collect results
            tool_results, report_back_result = self._execute_tools_parallel(
                tool_calls, trace_id, turn=turn + 1
            )

            # Add all tool results to messages (per OpenAI protocol)
            self._append_tool_results_to_messages(messages, tool_results)

            if self._trace:
                trace_entry = {
                    "turn": turn + 1,
                    "llm_latency_ms": round(llm_latency_ms, 1),
                    "llm_response": response,
                    "tool_calls_raw": tool_calls,
                    "tool_results": [
                        {
                            "id": tc_id,
                            "name": tc_name,
                            "result": tc_result if isinstance(tc_result, str) else tc_result,
                        }
                        for tc_id, tc_name, tc_result in tool_results
                    ],
                    "report_back": report_back_result,
                }
                turns_log.append(trace_entry)

            # If we stripped report_back, inject a correction hint for next turn
            if mixed_rb_ids:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your previous turn mixed report_back with other tools — "
                            "report_back was discarded. If you are done exploring, "
                            "call report_back ALONE as the ONLY tool in your next turn."
                        ),
                    }
                )

            # After processing all tool calls, if report_back was called, return
            if report_back_result is not None:
                logger.debug(
                    "[%s] Search completed in %d turns, found %d files",
                    trace_id,
                    turn + 1,
                    len(report_back_result.get("files", {})),
                )
                result_dict = {
                    "query": query,
                    "explanation": report_back_result.get("explanation", ""),
                    "files": self._normalize_report_files(report_back_result.get("files", {})),
                    "turns_used": turn + 1,
                }
                if self._trace:
                    result_dict["turns_log"] = turns_log
                return result_dict

        # Exceeded limit, return partial report (don't raise)
        logger.warning(
            "[%s] Search did not complete within %d turns, returning partial results",
            trace_id,
            SEARCH_MAX_TURNS,
        )
        merged_files = self._merge_observed_ranges()
        result_dict = {
            "query": query,
            "explanation": (
                f"[PARTIAL] Search did not complete within {SEARCH_MAX_TURNS} turns. "
                f"Returning {len(merged_files)} observed files based on exploration."
            ),
            "files": merged_files,
            "turns_used": SEARCH_MAX_TURNS,
            "partial": True,
        }
        if self._trace:
            result_dict["turns_log"] = turns_log
        return result_dict

    async def _run_search_loop_async(
        self,
        query: str,
        trace_id: str,
        *,
        start_time: float,
        semantic_hints_section: str = "",
    ) -> dict[str, Any]:
        """Internal method to execute the search loop asynchronously."""
        user_content = (
            self._user_prompt_override
            if self._user_prompt_override
            else self._user_prompt_template.format(
                query=query,
                semantic_hints_section=semantic_hints_section,
            )
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_content},
        ]

        turns_log: list[dict[str, Any]] = []

        loop = asyncio.get_running_loop()
        # Use an explicit ThreadPoolExecutor for blocking tool execution.
        with ThreadPoolExecutor(max_workers=1) as executor:
            for turn in range(SEARCH_MAX_TURNS):
                if (time.perf_counter() - start_time) > SEARCH_TIMEOUT_SECONDS:
                    merged_files = self._merge_observed_ranges()
                    result_dict = {
                        "query": query,
                        "explanation": (
                            f"[PARTIAL] Search exceeded SEARCH_TIMEOUT_SECONDS={SEARCH_TIMEOUT_SECONDS}s. "
                            f"Returning {len(merged_files)} observed files based on exploration."
                        ),
                        "files": merged_files,
                        "turns_used": turn,
                        "partial": True,
                        "error": f"Search timed out after {SEARCH_TIMEOUT_SECONDS}s",
                    }
                    if self._trace:
                        result_dict["turns_log"] = turns_log
                    return result_dict
                logger.debug(
                    "[%s] Turn %d/%d",
                    trace_id,
                    turn + 1,
                    SEARCH_MAX_TURNS,
                )

                # Inject unified turn hint (from turn 2 onwards)
                if turn > 0:
                    chars_for_hint = estimate_context_size(messages)
                    turn_hint = self._get_turn_hint(turn, SEARCH_MAX_TURNS, chars_for_hint)
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
                response = await self._client.chat_async(
                    messages, tools=get_tool_schemas(self._lsp_languages), trace_id=trace_id
                )
                llm_latency_ms = (time.perf_counter() - llm_start) * 1000

                # Parse response
                choices = response.get("choices", [])
                if not choices:
                    name = self._client._provider_config.display_name
                    raise RuntimeError(f"{name} Search API returned empty choices")

                message = choices[0].get("message", {})
                # Defense: some providers/mocks may lack role, avoid breaking block/repair logic
                message.setdefault("role", "assistant")
                tool_calls = message.get("tool_calls") or []

                # Extract usage for token tracking
                usage = response.get("usage")

                # Log turn state after getting response (includes LLM latency and token usage)
                log_search_turn(
                    trace_id,
                    turn + 1,
                    SEARCH_MAX_TURNS,
                    ctx_size,
                    len(tool_calls),
                    llm_latency_ms=llm_latency_ms,
                    usage=usage,
                )

                # If no tool_calls, check for content (model may respond directly)
                if not tool_calls:
                    content = message.get("content") or ""
                    logger.warning(
                        "[%s] No tool calls in turn %d (content_len=%d)",
                        trace_id,
                        turn + 1,
                        len(content),
                    )
                    # Add assistant message to context and continue
                    messages.append({"role": "assistant", "content": content})
                    if self._trace:
                        trace_entry: dict[str, Any] = {
                            "turn": turn + 1,
                            "llm_latency_ms": round(llm_latency_ms, 1),
                            "llm_response": response,
                            "tool_calls_raw": [],
                            "tool_results": [],
                            "report_back": None,
                        }
                        turns_log.append(trace_entry)
                    continue

                # Guardrail: detect report_back mixed with other tools
                tool_calls, message, mixed_rb_ids = self._strip_mixed_report_back(
                    tool_calls, message, trace_id
                )

                # Add assistant message (with tool_calls) to messages
                messages.append(self._sanitize_assistant_message(message))

                # Execute tool calls off the event loop to avoid blocking.
                tool_results, report_back_result = await loop.run_in_executor(
                    executor,
                    self._execute_tools_parallel,
                    tool_calls,
                    trace_id,
                    turn + 1,
                )

                # Add all tool results to messages (per OpenAI protocol)
                self._append_tool_results_to_messages(messages, tool_results)

                if self._trace:
                    trace_entry = {
                        "turn": turn + 1,
                        "llm_latency_ms": round(llm_latency_ms, 1),
                        "llm_response": response,
                        "tool_calls_raw": tool_calls,
                        "tool_results": [
                            {
                                "id": tc_id,
                                "name": tc_name,
                                "result": tc_result if isinstance(tc_result, str) else tc_result,
                            }
                            for tc_id, tc_name, tc_result in tool_results
                        ],
                        "report_back": report_back_result,
                    }
                    turns_log.append(trace_entry)

                # If we stripped report_back, inject a correction hint for next turn
                if mixed_rb_ids:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Your previous turn mixed report_back with other tools — "
                                "report_back was discarded. If you are done exploring, "
                                "call report_back ALONE as the ONLY tool in your next turn."
                            ),
                        }
                    )

                # After processing all tool calls, if report_back was called, return
                if report_back_result is not None:
                    logger.debug(
                        "[%s] Search completed in %d turns, found %d files",
                        trace_id,
                        turn + 1,
                        len(report_back_result.get("files", {})),
                    )
                    result_dict = {
                        "query": query,
                        "explanation": report_back_result.get("explanation", ""),
                        "files": self._normalize_report_files(report_back_result.get("files", {})),
                        "turns_used": turn + 1,
                    }
                    if self._trace:
                        result_dict["turns_log"] = turns_log
                    return result_dict

        # Exceeded limit, return partial report (don't raise)
        logger.warning(
            "[%s] Search did not complete within %d turns, returning partial results",
            trace_id,
            SEARCH_MAX_TURNS,
        )
        merged_files = self._merge_observed_ranges()
        result_dict = {
            "query": query,
            "explanation": (
                f"[PARTIAL] Search did not complete within {SEARCH_MAX_TURNS} turns. "
                f"Returning {len(merged_files)} observed files based on exploration."
            ),
            "files": merged_files,
            "turns_used": SEARCH_MAX_TURNS,
            "partial": True,
        }
        if self._trace:
            result_dict["turns_log"] = turns_log
        return result_dict
