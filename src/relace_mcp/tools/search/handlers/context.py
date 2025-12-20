from typing import Any

from .constants import MAX_TOOL_RESULT_CHARS


def truncate_for_context(
    text: str, max_chars: int = MAX_TOOL_RESULT_CHARS, tool_hint: str = ""
) -> str:
    """Truncate overly long tool result to avoid context overflow.

    Args:
        text: Text to truncate.
        max_chars: Maximum characters.
        tool_hint: Tool hint message shown when truncated.
    """
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    hint_msg = f"\n... [truncated] ({len(text)} chars total, showing {max_chars})"
    if tool_hint:
        hint_msg += f"\n{tool_hint}"
    return truncated + hint_msg


def estimate_context_size(messages: list[dict[str, Any]]) -> int:
    """Estimate total character count of messages."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(content)
        # tool_calls also take space
        tool_calls = msg.get("tool_calls", [])
        for tc in tool_calls:
            func = tc.get("function", {})
            total += len(func.get("arguments", ""))
    return total
