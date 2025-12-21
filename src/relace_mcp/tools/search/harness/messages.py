import json
import logging
from typing import Any

from ..handlers import (
    MAX_BASH_CHARS,
    MAX_GLOB_CHARS,
    MAX_GREP_SEARCH_CHARS,
    MAX_VIEW_DIRECTORY_CHARS,
    MAX_VIEW_FILE_CHARS,
    truncate_for_context,
)

logger = logging.getLogger(__name__)


class MessageHistoryMixin:
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
            "glob": (
                MAX_GLOB_CHARS,
                "To limit output, narrow the pattern, provide a narrower path, or reduce max_results.",
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
