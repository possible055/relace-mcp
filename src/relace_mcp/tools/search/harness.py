import json
import logging
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from ...clients import RelaceSearchClient
from ...config import SEARCH_MAX_TURNS, RelaceConfig
from .handlers import (
    MAX_BASH_CHARS,
    MAX_GREP_SEARCH_CHARS,
    MAX_VIEW_DIRECTORY_CHARS,
    MAX_VIEW_FILE_CHARS,
    bash_handler,
    estimate_context_size,
    grep_search_handler,
    report_back_handler,
    truncate_for_context,
    view_directory_handler,
    view_file_handler,
)
from .schemas import (
    BUDGET_HINT_TEMPLATE,
    CONVERGENCE_HINT,
    STRATEGIES,
    SYSTEM_PROMPT,
    TOOL_SCHEMAS,
    USER_PROMPT_TEMPLATE,
    GrepSearchParams,
)

logger = logging.getLogger(__name__)

# Context truncation: total messages character limit (approx 100k tokens)
MAX_TOTAL_CONTEXT_CHARS = 400000

# Read-only tools safe for parallel execution
PARALLEL_SAFE_TOOLS = frozenset({"view_file", "view_directory", "grep_search"})

# Maximum parallel workers (official recommendation: 4-12 tool calls per turn)
MAX_PARALLEL_WORKERS = 12

# Budget Tracker strategy thresholds (for SEARCH_MAX_TURNS=6)
BUDGET_HIGH_THRESHOLD = 4  # Remaining 4+ turns: broad exploration
BUDGET_MID_THRESHOLD = 2  # Remaining 2-3 turns: focus and prepare
# Remaining < 2 turns: report immediately


class FastAgenticSearchHarness:
    """Fast Agentic Search Agent Harness.

    Responsible for executing the relace-search model's agent loop,
    processing tool calls and terminating upon receiving report_back.
    """

    def __init__(self, config: RelaceConfig, client: RelaceSearchClient) -> None:
        self._config = config
        self._client = client
        self._observed_files: dict[str, list[list[int]]] = {}
        self._view_line_re = re.compile(r"^(\d+)\s")

    def _get_budget_hint(self, turn: int, max_turns: int) -> str:
        """Generate Budget Tracker hint message.

        Provides strategy suggestions based on remaining turns to help model converge autonomously.
        """
        remaining = max_turns - turn
        remaining_pct = 100 - (turn / max_turns) * 100

        if remaining >= BUDGET_HIGH_THRESHOLD:
            strategy = STRATEGIES["high"]
        elif remaining >= BUDGET_MID_THRESHOLD:
            strategy = STRATEGIES["mid"]
        else:
            strategy = STRATEGIES["low"]

        return BUDGET_HINT_TEMPLATE.format(
            turn=turn + 1,
            max_turns=max_turns,
            remaining=remaining,
            remaining_pct=f"{remaining_pct:.0f}",
            strategy=strategy,
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

        # Reset observed_files (used to accumulate explored files)
        self._observed_files = {}

        try:
            return self._run_search_loop(query, trace_id)
        except Exception as exc:
            logger.error("[%s] Search failed with error: %s", trace_id, exc)
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
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(query=query)},
        ]

        for turn in range(SEARCH_MAX_TURNS):
            logger.debug("[%s] Turn %d/%d", trace_id, turn + 1, SEARCH_MAX_TURNS)

            # Budget Tracker: inject budget state each turn (starting from turn 2)
            if turn > 0:
                budget_hint = self._get_budget_hint(turn, SEARCH_MAX_TURNS)
                messages.append({"role": "user", "content": budget_hint})
                logger.debug("[%s] Injected budget hint at turn %d", trace_id, turn + 1)

            # Progressive convergence hint: start from midpoint (not last 2 turns)
            remaining = SEARCH_MAX_TURNS - turn
            if remaining < BUDGET_MID_THRESHOLD:
                # Last 2 turns: force convergence
                messages.append({"role": "user", "content": CONVERGENCE_HINT})
                logger.info("[%s] Injected convergence hint at turn %d", trace_id, turn + 1)

            # Check context size
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

            response = self._client.chat(messages, tools=TOOL_SCHEMAS, trace_id=trace_id)

            # Parse response
            choices = response.get("choices", [])
            if not choices:
                raise RuntimeError("Relace Search API returned empty choices")

            message = choices[0].get("message", {})
            # Defense: some providers/mocks may lack role, avoid breaking block/repair logic
            message.setdefault("role", "assistant")
            tool_calls = message.get("tool_calls", [])

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
            tool_results, report_back_result = self._execute_tools_parallel(tool_calls, trace_id)

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
            SEARCH_MAX_TURNS,
        )
        merged_files = self._merge_observed_ranges()
        return {
            "query": query,
            "explanation": (
                f"[PARTIAL] Search did not complete within {SEARCH_MAX_TURNS} turns. "
                f"Returning {len(merged_files)} observed files based on exploration."
            ),
            "files": merged_files,
            "turns_used": SEARCH_MAX_TURNS,
            "partial": True,
        }

    def _record_grep_results(self, grep_output: str) -> None:
        """Parse grep output and record to observed_files.

        Grep output format: path:line:content
        Note: grep output paths are relative to base_dir, converted to absolute paths.
        """
        import re

        # Parse grep output, extract path:line
        pattern = r"^([^:]+):(\d+):"
        for line in grep_output.split("\n"):
            match = re.match(pattern, line)
            if match:
                rel_path = match.group(1)
                # Normalize path format: remove ./ prefix
                if rel_path.startswith("./"):
                    rel_path = rel_path[2:]
                # Convert to absolute path
                abs_path = os.path.join(self._config.base_dir, rel_path)
                line_num = int(match.group(2))

                if abs_path not in self._observed_files:
                    self._observed_files[abs_path] = []
                # Record single-line range
                self._observed_files[abs_path].append([line_num, line_num])

    def _merge_observed_ranges(self) -> dict[str, list[list[int]]]:
        """Merge and deduplicate ranges in observed_files.

        Adjacent or overlapping ranges are merged, max 20 segments per file.
        """
        max_ranges_per_file = 20
        max_total_files = 50
        merged: dict[str, list[list[int]]] = {}

        # Sort by number of ranges, prioritize files with more ranges
        sorted_files = sorted(
            self._observed_files.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )[:max_total_files]

        for path, ranges in sorted_files:
            if not ranges:
                continue

            # Sort and merge adjacent/overlapping ranges
            sorted_ranges = sorted(ranges, key=lambda r: r[0])
            merged_ranges: list[list[int]] = []

            for r in sorted_ranges:
                if not merged_ranges:
                    merged_ranges.append(r[:])
                else:
                    last = merged_ranges[-1]
                    # Merge if adjacent or overlapping (allow 1-line gap)
                    if r[0] <= last[1] + 2:
                        last[1] = max(last[1], r[1])
                    else:
                        merged_ranges.append(r[:])

            # Limit ranges per file
            merged[path] = merged_ranges[:max_ranges_per_file]

        return merged

    def _extract_view_file_range(self, output: str) -> list[int] | None:
        """Parse actual line range from view_file output.

        view_file_handler output starts each line with "<line_number> <content>".
        Returns None if parsing fails (e.g., view_range out of file bounds produces no numbered lines).
        """
        start: int | None = None
        end: int | None = None
        for line in output.splitlines():
            match = self._view_line_re.match(line)
            if not match:
                continue
            line_no = int(match.group(1))
            if start is None:
                start = line_no
            end = line_no
        if start is None or end is None:
            return None
        return [start, end]

    def _to_absolute_path(self, path: str) -> str:
        """Convert any path format to absolute filesystem path.

        Handles: /repo/..., relative paths, and already-absolute paths.
        """
        if path.startswith("/repo/"):
            return os.path.join(self._config.base_dir, path[6:])
        if path in ("/repo", "/repo/"):
            return self._config.base_dir
        if os.path.isabs(path):
            return path
        return os.path.join(self._config.base_dir, path)

    def _normalize_view_path(self, raw_path: Any) -> str | None:
        """Convert /repo/... path to absolute filesystem path.

        Used to record observed files with absolute paths for the final report.
        Returns None if the path format is invalid.
        """
        if not isinstance(raw_path, str):
            return None
        if not raw_path.startswith("/repo"):
            return None
        return self._to_absolute_path(raw_path)

    def _normalize_report_files(
        self, files: dict[str, list[list[int]]]
    ) -> dict[str, list[list[int]]]:
        """Normalize report_back file paths to absolute paths."""
        if not isinstance(files, dict):
            return {}
        return {self._to_absolute_path(path): ranges for path, ranges in files.items()}

    def _maybe_record_observed(
        self, name: str, args: dict[str, Any], result: str | dict[str, Any]
    ) -> None:
        """Accumulate observed_files based on tool results (for partial report use)."""
        if not isinstance(result, str) or result.startswith("Error:"):
            return

        if name == "view_file":
            normalized_path = self._normalize_view_path(args.get("path"))
            if not normalized_path:
                return
            line_range = self._extract_view_file_range(result)
            if not line_range:
                return
            self._observed_files.setdefault(normalized_path, []).append(line_range)
            return

        if name == "grep_search":
            self._record_grep_results(result)

    def _repair_tool_call_integrity(self, messages: list[dict[str, Any]], trace_id: str) -> None:
        """Check and repair tool_calls and tool results pairing integrity.

        Injects error tool result if a tool_call has no corresponding result.
        This prevents OpenAI-compatible providers from returning 400 due to protocol violation.
        """
        # Collect all tool_call ids
        expected_ids: set[str] = set()
        for msg in messages:
            if msg.get("role") == "assistant":
                tool_calls = msg.get("tool_calls", [])
                for tc in tool_calls:
                    tc_id = tc.get("id", "")
                    if tc_id:
                        expected_ids.add(tc_id)

        # Collect all existing tool result ids
        existing_ids: set[str] = set()
        for msg in messages:
            if msg.get("role") == "tool":
                tc_id = msg.get("tool_call_id", "")
                if tc_id:
                    existing_ids.add(tc_id)

        # Find missing tool results
        missing_ids = expected_ids - existing_ids
        if missing_ids:
            logger.warning(
                "[%s] Found %d missing tool results, injecting error responses",
                trace_id,
                len(missing_ids),
            )
            # Inject error tool results
            for tc_id in missing_ids:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": "Error: Tool execution was interrupted or result was truncated.",
                    }
                )

    def _truncate_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Truncate overly long message history, keep system + user + recent turn blocks.

        Turn block definition: one assistant(tool_calls) + all its corresponding tool results.
        Truncates by complete blocks to avoid orphan tool messages.
        """
        if len(messages) <= 8:
            return messages

        # Keep system (0) + user (1)
        system_and_user = messages[:2]
        conversation = messages[2:]

        # Identify turn blocks
        blocks: list[list[dict[str, Any]]] = []
        current_block: list[dict[str, Any]] = []

        for msg in conversation:
            role = msg.get("role", "")

            if role == "assistant":
                # If current block has content, save it first
                if current_block:
                    blocks.append(current_block)
                # Start new block
                current_block = [msg]
            elif role == "tool":
                # tool message must follow assistant
                if current_block:
                    current_block.append(msg)
                # If current_block is empty (orphan tool message), discard
            else:
                # Other types (like user), treat as independent message
                if current_block:
                    blocks.append(current_block)
                    current_block = []
                blocks.append([msg])

        # Last block
        if current_block:
            blocks.append(current_block)

        # Keep blocks from newest, target ~6-8 messages
        target_msg_count = 6
        kept_blocks: list[list[dict[str, Any]]] = []
        total_msgs = 0

        for block in reversed(blocks):
            block_size = len(block)
            if total_msgs + block_size <= target_msg_count * 1.5:  # Allow slight overflow
                kept_blocks.insert(0, block)
                total_msgs += block_size
            elif total_msgs == 0:
                # Keep at least the last block (even if exceeds limit)
                kept_blocks.insert(0, block)
                break
            else:
                break

        # Combine result
        result = system_and_user[:]
        for block in kept_blocks:
            result.extend(block)

        return result

    def _append_tool_results_to_messages(
        self,
        messages: list[dict[str, Any]],
        tool_results: list[tuple[str, str, str | dict[str, Any]]],
    ) -> None:
        """Format tool results and add to messages.

        Args:
            messages: Messages list to update.
            tool_results: Tool results list.
        """
        # Tool type to truncation limit and hint mapping
        tool_limits = {
            "view_file": (
                MAX_VIEW_FILE_CHARS,
                "For more content, narrow view_range or query in segments.",
            ),
            "grep_search": (
                MAX_GREP_SEARCH_CHARS,
                "For more matches, use more specific query or include_pattern.",
            ),
            "bash": (
                MAX_BASH_CHARS,
                "To limit output, use head -n / tail -n / --max-count params.",
            ),
            "view_directory": (
                MAX_VIEW_DIRECTORY_CHARS,
                "To see more entries, use a more specific path.",
            ),
        }

        for tc_id, func_name, result in tool_results:
            content = result if isinstance(result, str) else json.dumps(result)
            # Select truncation limit and hint based on tool type
            max_chars, hint = tool_limits.get(func_name, (MAX_VIEW_FILE_CHARS, ""))
            content = truncate_for_context(content, max_chars=max_chars, tool_hint=hint)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": content,
                }
            )

    def _parse_and_classify_tool_calls(
        self, tool_calls: list[dict[str, Any]], trace_id: str
    ) -> tuple[
        list[tuple[str, str, str, dict[str, Any] | None]],
        list[tuple[str, str, str, dict[str, Any] | None]],
    ]:
        """Parse and classify tool calls for parallel or sequential execution.

        Args:
            tool_calls: Tool calls list returned by API.
            trace_id: Trace ID.

        Returns:
            (parallel_calls, sequential_calls) tuple.
        """
        parsed_calls: list[tuple[str, str, str, dict[str, Any] | None]] = []
        for tc in tool_calls:
            tc_id = tc.get("id", "")
            function = tc.get("function", {})
            func_name = function.get("name", "")
            func_args_str = function.get("arguments", "{}")

            try:
                func_args = json.loads(func_args_str)
            except json.JSONDecodeError as exc:
                logger.error("[%s] Invalid JSON in tool call %s: %s", trace_id, func_name, exc)
                parsed_calls.append(
                    (tc_id, func_name, f"Error: Invalid JSON arguments: {exc}", None)
                )
                continue

            parsed_calls.append((tc_id, func_name, "", func_args))

        # Classify: parallelizable vs sequential execution
        parallel_calls = []
        sequential_calls = []
        for item in parsed_calls:
            tc_id, func_name, error, func_args = item
            if error:  # JSON parse failure
                sequential_calls.append(item)
            elif func_name in PARALLEL_SAFE_TOOLS:
                parallel_calls.append(item)
            else:
                sequential_calls.append(item)

        return parallel_calls, sequential_calls

    def _execute_tools_parallel(
        self, tool_calls: list[dict[str, Any]], trace_id: str
    ) -> tuple[list[tuple[str, str, str | dict[str, Any]]], dict[str, Any] | None]:
        """Execute read-only tools in parallel, other tools sequentially.

        Args:
            tool_calls: Tool calls list returned by API.
            trace_id: Trace ID.

        Returns:
            (tool_results, report_back_result) tuple.
        """
        parallel_calls, sequential_calls = self._parse_and_classify_tool_calls(tool_calls, trace_id)

        tool_results = self._execute_parallel_batch(parallel_calls, trace_id)
        seq_results, report_back_result = self._execute_sequential_batch(sequential_calls, trace_id)
        tool_results.extend(seq_results)

        # Sort by original order (maintain API protocol consistency)
        original_order = {tc.get("id", ""): i for i, tc in enumerate(tool_calls)}
        tool_results.sort(key=lambda x: original_order.get(x[0], 999))

        return tool_results, report_back_result

    def _execute_parallel_batch(
        self,
        parallel_calls: list[tuple[str, str, str, dict[str, Any] | None]],
        trace_id: str,
    ) -> list[tuple[str, str, str | dict[str, Any]]]:
        """Execute read-only tools in parallel.

        Args:
            parallel_calls: Tool calls safe for parallel execution.
            trace_id: Trace ID.

        Returns:
            Tool results list.
        """
        tool_results: list[tuple[str, str, str | dict[str, Any]]] = []

        if parallel_calls:
            logger.debug("[%s] Executing %d tools in parallel", trace_id, len(parallel_calls))
            with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
                futures = {}
                for tc_id, func_name, _, func_args in parallel_calls:
                    # Defense: if func_args is not dict (shouldn't happen as errors go to sequential)
                    if func_args is None:
                        tool_results.append((tc_id, func_name, "Error: Missing arguments"))
                        continue
                    logger.debug("[%s] Tool call (parallel): %s", trace_id, func_name)
                    future = executor.submit(self._dispatch_tool, func_name, func_args)
                    futures[future] = (tc_id, func_name, func_args)

                for future in as_completed(futures):
                    tc_id, func_name, func_args = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        logger.error("[%s] Tool %s raised exception: %s", trace_id, func_name, exc)
                        result = f"Error: {exc}"
                    self._maybe_record_observed(func_name, func_args, result)
                    tool_results.append((tc_id, func_name, result))

        return tool_results

    def _execute_sequential_batch(
        self,
        sequential_calls: list[tuple[str, str, str, dict[str, Any] | None]],
        trace_id: str,
    ) -> tuple[list[tuple[str, str, str | dict[str, Any]]], dict[str, Any] | None]:
        """Execute tool calls sequentially and detect report_back.

        Args:
            sequential_calls: Tool calls requiring sequential execution.
            trace_id: Trace ID.

        Returns:
            (tool_results, report_back_result) tuple.
        """
        tool_results: list[tuple[str, str, str | dict[str, Any]]] = []
        report_back_result: dict[str, Any] | None = None

        for tc_id, func_name, error, func_args in sequential_calls:
            if error:
                tool_results.append((tc_id, func_name, error))
                continue

            if func_args is None:
                tool_results.append((tc_id, func_name, "Error: Missing arguments"))
                continue

            logger.debug("[%s] Tool call (sequential): %s", trace_id, func_name)
            try:
                result = self._dispatch_tool(func_name, func_args)
            except Exception as exc:
                logger.error("[%s] Tool %s raised exception: %s", trace_id, func_name, exc)
                result = f"Error: {exc}"

            self._maybe_record_observed(func_name, func_args, result)

            if func_name == "report_back" and isinstance(result, dict):
                report_back_result = result

            tool_results.append((tc_id, func_name, result))

        return tool_results, report_back_result

    def _dispatch_tool(self, name: str, args: dict[str, Any]) -> str | dict[str, Any]:
        """Dispatch tool call to corresponding handler and accumulate observed_files."""
        # Defense: if args is not dict (e.g., model returns "arguments": "\"oops\"")
        if not isinstance(args, dict):
            return f"Error: Invalid arguments type, expected dict but got {type(args).__name__}"

        base_dir = self._config.base_dir

        if name == "view_file":
            path = args.get("path", "")
            view_range = args.get("view_range", [1, 100])
            return view_file_handler(
                path=path,
                view_range=view_range,
                base_dir=base_dir,
            )
        elif name == "view_directory":
            return view_directory_handler(
                path=args.get("path", ""),
                include_hidden=args.get("include_hidden", False),
                base_dir=base_dir,
            )
        elif name == "grep_search":
            params = GrepSearchParams(
                query=args.get("query", ""),
                case_sensitive=args.get("case_sensitive", True),
                exclude_pattern=args.get("exclude_pattern"),
                include_pattern=args.get("include_pattern"),
                base_dir=base_dir,
            )
            return grep_search_handler(params)

        elif name == "report_back":
            return report_back_handler(
                explanation=args.get("explanation", ""),
                files=args.get("files", {}),
            )
        elif name == "bash":
            return bash_handler(
                command=args.get("command", ""),
                base_dir=base_dir,
            )
        else:
            return f"Error: Unknown tool '{name}'"
