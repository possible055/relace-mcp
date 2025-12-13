import json
import logging
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
from .schemas import SYSTEM_PROMPT, TOOL_SCHEMAS, USER_PROMPT_TEMPLATE, GrepSearchParams

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
        self._observed_files: dict[str, list[list[int]]] = {}
        self._view_line_re = re.compile(r"^(\d+)\s")

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
                "partial": bool,  # optional, True when error or max turns exceeded
                "error": str,  # optional, present when error occurred
            }

        Note:
            此方法永遠回傳 dict，不會拋出異常。
            當發生錯誤時，會回傳包含 error 欄位的 partial report。
        """
        trace_id = str(uuid.uuid4())[:8]
        # 安全截斷 query（避免在多字節字符中間截斷）
        query_preview = query[:100] if len(query) <= 100 else query[:97] + "..."
        logger.info("[%s] Starting Fast Agentic Search: %s", trace_id, query_preview)

        # 重置 observed_files（用於累積已探索的檔案）
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
        """執行 search loop 的內部方法。"""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(query=query)},
        ]

        for turn in range(SEARCH_MAX_TURNS):
            logger.debug("[%s] Turn %d/%d", trace_id, turn + 1, SEARCH_MAX_TURNS)

            # 強制收斂機制：最後 2 turn 注入提示
            if turn >= SEARCH_MAX_TURNS - 2:
                convergence_hint = (
                    "剩餘回合有限，請立即使用 report_back 回報目前發現，"
                    "不要追求完整覆蓋。請基於已收集的資訊做出判斷。"
                )
                messages.append({"role": "user", "content": convergence_hint})
                logger.info("[%s] Injected convergence hint at turn %d", trace_id, turn + 1)

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

            # 確保 tool_calls 與 tool results 配對完整
            self._repair_tool_call_integrity(messages, trace_id)

            response = self._client.chat(messages, tools=TOOL_SCHEMAS, trace_id=trace_id)

            # 解析 response
            choices = response.get("choices", [])
            if not choices:
                raise RuntimeError("Relace Search API returned empty choices")

            message = choices[0].get("message", {})
            # 防禦：部分 provider/mock 可能缺少 role，避免後續 block/repair 邏輯失效
            message.setdefault("role", "assistant")
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
            self._append_tool_results_to_messages(messages, tool_results)

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

        # 超限時回傳 partial report（不 raise）
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
        """解析 grep 輸出並記錄到 observed_files。

        Grep 輸出格式：path:line:content
        注意：grep 輸出的路徑是相對於 base_dir 的，可能以 ./ 開頭。
        """
        import re

        # 解析 grep 輸出，提取 path:line
        pattern = r"^([^:]+):(\d+):"
        for line in grep_output.split("\n"):
            match = re.match(pattern, line)
            if match:
                path = match.group(1)
                # 統一路徑格式：移除 ./ 前綴（grep 相對路徑），確保與 view_file 一致
                if path.startswith("./"):
                    path = path[2:]
                line_num = int(match.group(2))

                if path not in self._observed_files:
                    self._observed_files[path] = []
                # 記錄單行範圍
                self._observed_files[path].append([line_num, line_num])

    def _merge_observed_ranges(self) -> dict[str, list[list[int]]]:
        """合併並去重 observed_files 中的 ranges。

        相鄰或重疊的 ranges 會被合併，每檔案最多保留 20 段。
        """
        max_ranges_per_file = 20
        max_total_files = 50
        merged: dict[str, list[list[int]]] = {}

        # 按檔案數量排序，優先保留較多 ranges 的檔案
        sorted_files = sorted(
            self._observed_files.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )[:max_total_files]

        for path, ranges in sorted_files:
            if not ranges:
                continue

            # 排序並合併相鄰/重疊的 ranges
            sorted_ranges = sorted(ranges, key=lambda r: r[0])
            merged_ranges: list[list[int]] = []

            for r in sorted_ranges:
                if not merged_ranges:
                    merged_ranges.append(r[:])
                else:
                    last = merged_ranges[-1]
                    # 相鄰或重疊則合併（允許相鄰 1 行也合併）
                    if r[0] <= last[1] + 2:
                        last[1] = max(last[1], r[1])
                    else:
                        merged_ranges.append(r[:])

            # 限制每檔案的 ranges 數量
            merged[path] = merged_ranges[:max_ranges_per_file]

        return merged

    def _extract_view_file_range(self, output: str) -> list[int] | None:
        """從 view_file 的輸出解析實際輸出的行號範圍。

        view_file_handler 的輸出每行以「<line_number> <content>」格式開始。
        若無法解析（例如 view_range 超出檔案範圍導致沒有任何帶行號的行），回傳 None。
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

    def _normalize_view_path(self, raw_path: Any) -> str | None:
        """將 view_file 的 path 轉為相對於 repo root 的路徑字串。"""
        if not isinstance(raw_path, str):
            return None
        if raw_path in ("/repo", "/repo/"):
            return None
        path = raw_path.removeprefix("/repo/")
        if path.startswith("./"):
            path = path[2:]
        return path or None

    def _maybe_record_observed(
        self, name: str, args: dict[str, Any], result: str | dict[str, Any]
    ) -> None:
        """根據 tool 的結果累積 observed_files（供 partial report 使用）。"""
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
        """檢查並修復 tool_calls 與 tool results 的配對完整性。

        若有 tool_call 沒有對應的 tool result，會注入 error tool result。
        這是為了避免 OpenAI-compatible provider 因協議違規而返回 400。
        """
        # 收集所有 tool_call ids
        expected_ids: set[str] = set()
        for msg in messages:
            if msg.get("role") == "assistant":
                tool_calls = msg.get("tool_calls", [])
                for tc in tool_calls:
                    tc_id = tc.get("id", "")
                    if tc_id:
                        expected_ids.add(tc_id)

        # 收集所有已有的 tool result ids
        existing_ids: set[str] = set()
        for msg in messages:
            if msg.get("role") == "tool":
                tc_id = msg.get("tool_call_id", "")
                if tc_id:
                    existing_ids.add(tc_id)

        # 找出缺失的 tool results
        missing_ids = expected_ids - existing_ids
        if missing_ids:
            logger.warning(
                "[%s] Found %d missing tool results, injecting error responses",
                trace_id,
                len(missing_ids),
            )
            # 注入 error tool results
            for tc_id in missing_ids:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": "Error: Tool execution was interrupted or result was truncated.",
                    }
                )

    def _truncate_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """截斷過長的 message history，保留 system + user + 最近幾個 turn blocks。

        Turn block 定義：一個 assistant(tool_calls) + 其對應的所有 tool 結果。
        截斷時以完整 block 為單位，確保不會留下孤兒 tool message。
        """
        if len(messages) <= 8:
            return messages

        # 保留 system (0) + user (1)
        system_and_user = messages[:2]
        conversation = messages[2:]

        # 識別 turn blocks
        blocks: list[list[dict[str, Any]]] = []
        current_block: list[dict[str, Any]] = []

        for msg in conversation:
            role = msg.get("role", "")

            if role == "assistant":
                # 若當前 block 有內容，先儲存
                if current_block:
                    blocks.append(current_block)
                # 開始新 block
                current_block = [msg]
            elif role == "tool":
                # tool message 必須跟在 assistant 之後
                if current_block:
                    current_block.append(msg)
                # 如果 current_block 為空（孤兒 tool message），直接丟棄
            else:
                # 其他類型（如 user），視為獨立訊息
                if current_block:
                    blocks.append(current_block)
                    current_block = []
                blocks.append([msg])

        # 最後一個 block
        if current_block:
            blocks.append(current_block)

        # 從最新 block 往前保留，目標保留約 6-8 個 messages
        target_msg_count = 6
        kept_blocks: list[list[dict[str, Any]]] = []
        total_msgs = 0

        for block in reversed(blocks):
            block_size = len(block)
            if total_msgs + block_size <= target_msg_count * 1.5:  # 允許稍微超過
                kept_blocks.insert(0, block)
                total_msgs += block_size
            elif total_msgs == 0:
                # 至少保留最後一個 block（即使超過上限）
                kept_blocks.insert(0, block)
                break
            else:
                break

        # 組合結果
        result = system_and_user[:]
        for block in kept_blocks:
            result.extend(block)

        return result

    def _append_tool_results_to_messages(
        self,
        messages: list[dict[str, Any]],
        tool_results: list[tuple[str, str, str | dict[str, Any]]],
    ) -> None:
        """將 tool results 格式化並加入 messages。

        Args:
            messages: 要更新的 messages 列表。
            tool_results: tool results 列表。
        """
        # 工具類型對應的截斷上限與提示
        tool_limits = {
            "view_file": (
                MAX_VIEW_FILE_CHARS,
                "如需更多內容，請縮小 view_range 或分段查詢。",
            ),
            "grep_search": (
                MAX_GREP_SEARCH_CHARS,
                "如需更多匹配結果，請使用更具體的 query 或 include_pattern。",
            ),
            "bash": (
                MAX_BASH_CHARS,
                "如需限制輸出，請用 head -n / tail -n / --max-count 等參數。",
            ),
            "view_directory": (
                MAX_VIEW_DIRECTORY_CHARS,
                "如需查看更多目錄項目，請使用更具體的路徑。",
            ),
        }

        for tc_id, func_name, result in tool_results:
            content = result if isinstance(result, str) else json.dumps(result)
            # 根據工具類型選擇截斷上限與提示
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
        """解析並分類 tool calls 為並行或順序執行。

        Args:
            tool_calls: API 回傳的 tool_calls 列表。
            trace_id: 追蹤 ID。

        Returns:
            (parallel_calls, sequential_calls) tuple。
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

        return parallel_calls, sequential_calls

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
        parallel_calls, sequential_calls = self._parse_and_classify_tool_calls(tool_calls, trace_id)

        tool_results = self._execute_parallel_batch(parallel_calls, trace_id)
        seq_results, report_back_result = self._execute_sequential_batch(sequential_calls, trace_id)
        tool_results.extend(seq_results)

        # 按原始順序排序（維持 API 協議一致性）
        original_order = {tc.get("id", ""): i for i, tc in enumerate(tool_calls)}
        tool_results.sort(key=lambda x: original_order.get(x[0], 999))

        return tool_results, report_back_result

    def _execute_parallel_batch(
        self,
        parallel_calls: list[tuple[str, str, str, dict[str, Any] | None]],
        trace_id: str,
    ) -> list[tuple[str, str, str | dict[str, Any]]]:
        """並行執行 read-only 工具。

        Args:
            parallel_calls: 可並行執行的 tool calls。
            trace_id: 追蹤 ID。

        Returns:
            tool results 列表。
        """
        tool_results: list[tuple[str, str, str | dict[str, Any]]] = []

        if parallel_calls:
            logger.debug("[%s] Executing %d tools in parallel", trace_id, len(parallel_calls))
            with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
                futures = {}
                for tc_id, func_name, _, func_args in parallel_calls:
                    # 防禦：若 func_args 不是 dict（理論上不應發生，因為 error 會被分到 sequential）
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
        """順序執行 tool calls，並檢測 report_back。

        Args:
            sequential_calls: 需順序執行的 tool calls。
            trace_id: 追蹤 ID。

        Returns:
            (tool_results, report_back_result) tuple。
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
        """分派 tool call 到對應的 handler，並累積 observed_files。"""
        # 防禦：若 args 不是 dict（例如模型回傳 "arguments": "\"oops\""）
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
