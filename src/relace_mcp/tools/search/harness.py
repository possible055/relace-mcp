import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from ...clients import RelaceSearchClient
from ...config import SEARCH_MAX_TURNS, RelaceConfig
from .handlers import (
    bash_handler,
    estimate_context_size,
    grep_search_handler,
    report_back_handler,
    truncate_for_context,
    view_directory_handler,
    view_file_handler,
)
from .schemas import SYSTEM_PROMPT, TOOL_SCHEMAS, USER_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

# Context 截斷：總 messages 字元數上限（約 100k tokens）
MAX_TOTAL_CONTEXT_CHARS = 400000

# 可安全並行執行的 read-only 工具
PARALLEL_SAFE_TOOLS = frozenset({"view_file", "view_directory", "grep_search"})

# 並行執行的最大 worker 數（官方建議 4-12 tool calls per turn）
MAX_PARALLEL_WORKERS = 12


class FastAgenticSearchHarness:
    """Fast Agentic Search Agent Harness。

    負責執行 relace-search 模型的 agent loop，
    處理 tool calls 並在收到 report_back 後終止。
    """

    def __init__(self, config: RelaceConfig, client: RelaceSearchClient) -> None:
        self._config = config
        self._client = client

    def run(self, query: str) -> dict[str, Any]:
        """執行一次 Fast Agentic Search。

        Args:
            query: 使用者 query，描述要搜尋/理解的內容。

        Returns:
            包含 explanation 與 files 的 dict：
            {
                "query": str,
                "explanation": str,
                "files": {path: [[start, end], ...]},
                "turns_used": int,
            }

        Raises:
            RuntimeError: Agent 未在 max turns 內完成。
        """
        trace_id = str(uuid.uuid4())[:8]
        # 安全截斷 query（避免在多字節字符中間截斷）
        query_preview = query[:100] if len(query) <= 100 else query[:97] + "..."
        logger.info("[%s] Starting Fast Agentic Search: %s", trace_id, query_preview)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(query=query)},
        ]

        for turn in range(SEARCH_MAX_TURNS):
            logger.debug("[%s] Turn %d/%d", trace_id, turn + 1, SEARCH_MAX_TURNS)

            # 檢查 context 大小
            ctx_size = estimate_context_size(messages)

            if ctx_size > MAX_TOTAL_CONTEXT_CHARS:
                logger.warning(
                    "[%s] Context size %d exceeds limit %d, truncating old messages",
                    trace_id,
                    ctx_size,
                    MAX_TOTAL_CONTEXT_CHARS,
                )
                # 保留 system + user + 最近 6 條 messages
                messages = self._truncate_messages(messages)

            response = self._client.chat(messages, tools=TOOL_SCHEMAS, trace_id=trace_id)

            # 解析 response
            choices = response.get("choices", [])
            if not choices:
                raise RuntimeError("Relace Search API returned empty choices")

            message = choices[0].get("message", {})
            tool_calls = message.get("tool_calls", [])

            # 若無 tool_calls，檢查是否有 content（模型可能直接回答）
            if not tool_calls:
                content = message.get("content", "")
                content_preview = content[:200] if len(content) <= 200 else content[:197] + "..."
                logger.warning(
                    "[%s] No tool calls in turn %d, content: %s",
                    trace_id,
                    turn + 1,
                    content_preview,
                )
                # 將 assistant message 加入 context 繼續
                messages.append({"role": "assistant", "content": content})
                continue

            # 將 assistant message（含 tool_calls）加入 messages
            messages.append(message)

            # 並行執行 tool calls 並收集結果
            tool_results, report_back_result = self._execute_tools_parallel(tool_calls, trace_id)

            # 將所有 tool results 加入 messages（符合 OpenAI 協議）
            for tc_id, _func_name, result in tool_results:
                content = result if isinstance(result, str) else json.dumps(result)
                # 截斷過長的 tool result
                content = truncate_for_context(content)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": content,
                    }
                )

            # 所有 tool calls 處理完後，如果有 report_back 則返回
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
                    "files": report_back_result.get("files", {}),
                    "turns_used": turn + 1,
                }

        raise RuntimeError(f"Fast Agentic Search did not complete within {SEARCH_MAX_TURNS} turns")

    def _truncate_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """截斷過長的 message history，保留 system + user + 最近幾輪。"""
        # 保留 system (0) + user (1) + 最近 6 條 messages
        if len(messages) <= 8:
            return messages
        return messages[:2] + messages[-6:]

    def _execute_tools_parallel(
        self, tool_calls: list[dict[str, Any]], trace_id: str
    ) -> tuple[list[tuple[str, str, str | dict[str, Any]]], dict[str, Any] | None]:
        """並行執行 read-only 工具，順序執行其他工具。

        Args:
            tool_calls: API 回傳的 tool_calls 列表。
            trace_id: 追蹤 ID。

        Returns:
            (tool_results, report_back_result) tuple。
        """
        # 先解析所有 tool calls
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

        # 分類：可並行 vs 需順序執行
        parallel_calls = []
        sequential_calls = []
        for item in parsed_calls:
            tc_id, func_name, error, func_args = item
            if error:  # JSON 解析失敗
                sequential_calls.append(item)
            elif func_name in PARALLEL_SAFE_TOOLS:
                parallel_calls.append(item)
            else:
                sequential_calls.append(item)

        tool_results: list[tuple[str, str, str | dict[str, Any]]] = []
        report_back_result: dict[str, Any] | None = None

        # 並行執行 read-only 工具
        if parallel_calls:
            logger.debug("[%s] Executing %d tools in parallel", trace_id, len(parallel_calls))
            with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
                futures = {}
                for tc_id, func_name, _, func_args in parallel_calls:
                    logger.debug("[%s] Tool call (parallel): %s", trace_id, func_name)
                    future = executor.submit(self._dispatch_tool, func_name, func_args)
                    futures[future] = (tc_id, func_name)

                for future in as_completed(futures):
                    tc_id, func_name = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        logger.error("[%s] Tool %s raised exception: %s", trace_id, func_name, exc)
                        result = f"Error: {exc}"
                    tool_results.append((tc_id, func_name, result))

        # 順序執行 report_back 和錯誤項目
        for tc_id, func_name, error, func_args in sequential_calls:
            if error:
                tool_results.append((tc_id, func_name, error))
                continue

            logger.debug("[%s] Tool call (sequential): %s", trace_id, func_name)
            try:
                result = self._dispatch_tool(func_name, func_args)
            except Exception as exc:
                logger.error("[%s] Tool %s raised exception: %s", trace_id, func_name, exc)
                result = f"Error: {exc}"

            if func_name == "report_back" and isinstance(result, dict):
                report_back_result = result

            tool_results.append((tc_id, func_name, result))

        # 按原始順序排序（維持 API 協議一致性）
        original_order = {tc.get("id", ""): i for i, tc in enumerate(tool_calls)}
        tool_results.sort(key=lambda x: original_order.get(x[0], 999))

        return tool_results, report_back_result

    def _dispatch_tool(self, name: str, args: dict[str, Any]) -> str | dict[str, Any]:
        """分派 tool call 到對應的 handler。"""
        # 防禦：若 args 不是 dict（例如模型回傳 "arguments": "\"oops\""）
        if not isinstance(args, dict):
            return f"Error: Invalid arguments type, expected dict but got {type(args).__name__}"

        base_dir = self._config.base_dir

        if name == "view_file":
            return view_file_handler(
                path=args.get("path", ""),
                view_range=args.get("view_range", [1, 100]),
                base_dir=base_dir,
            )
        elif name == "view_directory":
            return view_directory_handler(
                path=args.get("path", ""),
                include_hidden=args.get("include_hidden", False),
                base_dir=base_dir,
            )
        elif name == "grep_search":
            return grep_search_handler(
                query=args.get("query", ""),
                case_sensitive=args.get("case_sensitive", True),
                exclude_pattern=args.get("exclude_pattern"),
                include_pattern=args.get("include_pattern"),
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
