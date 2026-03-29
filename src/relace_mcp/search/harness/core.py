import asyncio
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...clients.search import SearchLLMClient

from ...config import RelaceConfig, load_prompt_file
from ...config import settings as _settings
from .._impl import estimate_context_size
from ..logging import (
    log_search_complete,
    log_search_error,
    log_search_start,
    log_search_turn,
)
from ..prompt_messages import render_turn_status_message, should_append_turn_status
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

_PROMPT_FILES = {
    "relace": "search_relace",
    "openai": "search_openai",
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
        prompts: dict[str, Any] | None = None,
        trace: bool = False,
        freshness_message: str = "",
        hints_list: str = "",
    ) -> None:
        self._config = config
        self._trace = trace
        self._client = client
        self._observed_files: dict[str, list[list[int]]] = {}
        self._view_line_re = re.compile(r"^(\d+)\s")
        self._lsp_languages = lsp_languages if lsp_languages is not None else frozenset()
        self._user_prompt_override = user_prompt_override
        self._format_kwargs: dict[str, str] = {
            "freshness_message": freshness_message,
            "hints_list": hints_list,
            "max_turns": str(_settings.SEARCH_MAX_TURNS),
        }

        # Resolve enabled tools first (runtime LSP detection happens here)
        enabled_tools = self._enabled_tool_names()
        _lsp_tool_names = {"find_symbol", "search_symbol"}
        has_lsp = bool(enabled_tools & _lsp_tool_names)

        # Default to search prompts unless the caller explicitly provided a bundle.
        backend = "relace" if client.api_compat == _settings.RELACE_PROVIDER else "openai"
        prompt_bundle = prompts if prompts is not None else load_prompt_file(_PROMPT_FILES[backend])

        self._user_message_template = prompt_bundle["user_message_template"].strip()
        self._turn_status_messages = {
            key: value.strip() for key, value in prompt_bundle["turn_status_messages"].items()
        }
        self._report_back_retry_message = prompt_bundle.get("report_back_retry_message", "").strip()

        self._system_message = build_system_prompt(
            prompt_bundle["system_message_template"],
            enabled_tools=enabled_tools,
            has_lsp=has_lsp,
            lsp_section=prompt_bundle.get("lsp_section", ""),
            step2_discovery=prompt_bundle.get("step2_discovery"),
            step3_verification=prompt_bundle.get("step3_verification"),
        )

    def _append_turn_status_if_needed(
        self, messages: list[dict[str, Any]], turn: int, trace_id: str
    ) -> None:
        """Append the configured turn-status message when policy allows it."""
        max_turns = _settings.SEARCH_MAX_TURNS
        mode = _settings.SEARCH_TURN_STATUS_MODE
        if not should_append_turn_status(turn, mode, max_turns):
            return

        chars_for_status = estimate_context_size(messages)
        turn_status_message = render_turn_status_message(
            turn,
            max_turns,
            chars_for_status,
            self._turn_status_messages,
        )
        messages.append({"role": "user", "content": turn_status_message})
        logger.debug(
            "[%s] Injected turn status at turn %d (chars: %d/%d, mode=%s)",
            trace_id,
            turn + 1,
            chars_for_status,
            MAX_CONTEXT_BUDGET_CHARS,
            mode,
        )

    def run(
        self,
        query: str,
        *,
        trace_id: str | None = None,
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
        self,
        query: str,
        *,
        trace_id: str | None = None,
        on_progress: Callable[[int, int], Awaitable[None]] | None = None,
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
                on_progress=on_progress,
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
    ) -> dict[str, Any]:
        """Internal method to execute the search loop."""
        user_content = (
            self._user_prompt_override
            if self._user_prompt_override
            else self._user_message_template.format(query=query, **self._format_kwargs)
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_message},
            {"role": "user", "content": user_content},
        ]

        turns_log: list[dict[str, Any]] = []
        result_dict: dict[str, Any]

        for turn in range(_settings.SEARCH_MAX_TURNS):
            if (time.perf_counter() - start_time) > _settings.SEARCH_TIMEOUT_SECONDS:
                merged_files = self._merge_observed_ranges()
                result_dict = {
                    "query": query,
                    "explanation": (
                        f"[PARTIAL] Search exceeded SEARCH_TIMEOUT_SECONDS={_settings.SEARCH_TIMEOUT_SECONDS}s. "
                        f"Returning {len(merged_files)} observed files based on exploration."
                    ),
                    "files": merged_files,
                    "turns_used": turn,
                    "partial": True,
                    "error": f"Search timed out after {_settings.SEARCH_TIMEOUT_SECONDS}s",
                }
                if self._trace:
                    result_dict["turns_log"] = turns_log
                return result_dict
            logger.debug(
                "[%s] Turn %d/%d",
                trace_id,
                turn + 1,
                _settings.SEARCH_MAX_TURNS,
            )

            self._append_turn_status_if_needed(messages, turn, trace_id)

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
                _settings.SEARCH_MAX_TURNS,
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
            tool_results, tool_traces, report_back_result = self._execute_tools_parallel(
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
                    "tool_results": tool_traces,
                    "report_back": report_back_result,
                }
                turns_log.append(trace_entry)

            # If we stripped report_back, inject a correction hint for next turn
            if mixed_rb_ids and self._report_back_retry_message:
                messages.append({"role": "user", "content": self._report_back_retry_message})

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
            _settings.SEARCH_MAX_TURNS,
        )
        merged_files = self._merge_observed_ranges()
        result_dict = {
            "query": query,
            "explanation": (
                f"[PARTIAL] Search did not complete within {_settings.SEARCH_MAX_TURNS} turns. "
                f"Returning {len(merged_files)} observed files based on exploration."
            ),
            "files": merged_files,
            "turns_used": _settings.SEARCH_MAX_TURNS,
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
        on_progress: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        """Internal method to execute the search loop asynchronously."""
        user_content = (
            self._user_prompt_override
            if self._user_prompt_override
            else self._user_message_template.format(query=query, **self._format_kwargs)
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_message},
            {"role": "user", "content": user_content},
        ]

        turns_log: list[dict[str, Any]] = []
        result_dict: dict[str, Any]

        loop = asyncio.get_running_loop()
        # Use an explicit ThreadPoolExecutor for blocking tool execution.
        with ThreadPoolExecutor(max_workers=1) as executor:
            for turn in range(_settings.SEARCH_MAX_TURNS):
                if (time.perf_counter() - start_time) > _settings.SEARCH_TIMEOUT_SECONDS:
                    merged_files = self._merge_observed_ranges()
                    result_dict = {
                        "query": query,
                        "explanation": (
                            f"[PARTIAL] Search exceeded SEARCH_TIMEOUT_SECONDS={_settings.SEARCH_TIMEOUT_SECONDS}s. "
                            f"Returning {len(merged_files)} observed files based on exploration."
                        ),
                        "files": merged_files,
                        "turns_used": turn,
                        "partial": True,
                        "error": f"Search timed out after {_settings.SEARCH_TIMEOUT_SECONDS}s",
                    }
                    if self._trace:
                        result_dict["turns_log"] = turns_log
                    return result_dict
                logger.debug(
                    "[%s] Turn %d/%d",
                    trace_id,
                    turn + 1,
                    _settings.SEARCH_MAX_TURNS,
                )

                self._append_turn_status_if_needed(messages, turn, trace_id)

                if on_progress is not None:
                    try:
                        await on_progress(turn + 1, _settings.SEARCH_MAX_TURNS)
                    except Exception:  # nosec B110 — progress is best-effort
                        pass

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
                    _settings.SEARCH_MAX_TURNS,
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
                tool_results, tool_traces, report_back_result = await loop.run_in_executor(
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
                        "tool_results": tool_traces,
                        "report_back": report_back_result,
                    }
                    turns_log.append(trace_entry)

                # If we stripped report_back, inject a correction hint for next turn
                if mixed_rb_ids and self._report_back_retry_message:
                    messages.append({"role": "user", "content": self._report_back_retry_message})

                # After processing all tool calls, if report_back was called, return
                if report_back_result is not None:
                    logger.debug(
                        "[%s] Search completed in %d turns, found %d files",
                        trace_id,
                        turn + 1,
                        len(report_back_result.get("files", {})),
                    )
                    if on_progress is not None:
                        try:
                            await on_progress(
                                _settings.SEARCH_MAX_TURNS,
                                _settings.SEARCH_MAX_TURNS,
                            )
                        except Exception:  # nosec B110 — progress is best-effort
                            pass
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
            _settings.SEARCH_MAX_TURNS,
        )
        merged_files = self._merge_observed_ranges()
        result_dict = {
            "query": query,
            "explanation": (
                f"[PARTIAL] Search did not complete within {_settings.SEARCH_MAX_TURNS} turns. "
                f"Returning {len(merged_files)} observed files based on exploration."
            ),
            "files": merged_files,
            "turns_used": _settings.SEARCH_MAX_TURNS,
            "partial": True,
        }
        if self._trace:
            result_dict["turns_log"] = turns_log
        return result_dict
