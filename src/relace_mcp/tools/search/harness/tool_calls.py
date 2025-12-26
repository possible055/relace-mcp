import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any

from ....config import settings
from ..handlers import (
    bash_handler,
    glob_handler,
    grep_search_handler,
    report_back_handler,
    view_directory_handler,
    view_file_handler,
)
from ..logging import log_tool_call
from ..schemas import GrepSearchParams
from .constants import MAX_PARALLEL_WORKERS, PARALLEL_SAFE_TOOLS

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ....config import RelaceConfig


class ToolCallsMixin:
    _config: "RelaceConfig"

    if TYPE_CHECKING:

        def _maybe_record_observed(
            self,
            name: str,
            args: dict[str, Any],
            result: str | dict[str, Any],
        ) -> None: ...

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
                    future = executor.submit(
                        self._dispatch_tool_with_logging, func_name, func_args, trace_id
                    )
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
                result = self._dispatch_tool_with_logging(func_name, func_args, trace_id)
            except Exception as exc:
                logger.error("[%s] Tool %s raised exception: %s", trace_id, func_name, exc)
                result = f"Error: {exc}"

            self._maybe_record_observed(func_name, func_args, result)

            if func_name == "report_back" and isinstance(result, dict):
                report_back_result = result

            tool_results.append((tc_id, func_name, result))

        return tool_results, report_back_result

    def _dispatch_tool_with_logging(
        self, name: str, args: dict[str, Any], trace_id: str
    ) -> str | dict[str, Any]:
        """Dispatch tool call with timing and logging."""
        if not settings.RELACE_LOGGING:
            return self._dispatch_tool(name, args)

        start = time.perf_counter()
        result = self._dispatch_tool(name, args)
        latency_ms = (time.perf_counter() - start) * 1000

        try:
            success = not (isinstance(result, str) and result.startswith("Error:"))

            if isinstance(result, str):
                result_preview = result[:300]
            else:
                result_preview = json.dumps(result, ensure_ascii=False, default=str)[:300]

            log_tool_call(trace_id, name, args, result_preview, latency_ms, success)
        except Exception:
            # Logging failure should never break tool execution
            logger.debug("Failed to log tool call for %s", name, exc_info=True)
        return result

    def _dispatch_tool(self, name: str, args: dict[str, Any]) -> str | dict[str, Any]:
        """Dispatch tool call to corresponding handler and accumulate observed_files."""
        # Defense: if args is not dict (e.g., model returns "arguments": "\"oops\"")
        if not isinstance(args, dict):
            return f"Error: Invalid arguments type, expected dict but got {type(args).__name__}"

        base_dir = self._config.base_dir
        if base_dir is None:
            return "Error: base_dir is not configured. Set RELACE_BASE_DIR or ensure MCP Roots are available."

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
        elif name == "glob":
            return glob_handler(
                pattern=args.get("pattern", ""),
                path=args.get("path", "/repo"),
                include_hidden=args.get("include_hidden", False),
                max_results=args.get("max_results", 200),
                base_dir=base_dir,
            )

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
