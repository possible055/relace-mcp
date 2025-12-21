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

    shown = max_chars
    for _ in range(5):
        hint_msg = f"\n... [truncated] ({len(text)} chars total, showing {shown})"
        if tool_hint:
            hint_msg += f"\n{tool_hint}"
        allowed = max_chars - len(hint_msg)
        if allowed < 0:
            allowed = 0
        if allowed == shown:
            break
        shown = allowed

    hint_msg = f"\n... [truncated] ({len(text)} chars total, showing {shown})"
    if tool_hint:
        hint_msg += f"\n{tool_hint}"

    # If the hint itself exceeds max_chars, return as much of the hint as fits.
    if len(hint_msg) >= max_chars:
        return hint_msg[:max_chars]

    truncated = text[:shown]
    return truncated + hint_msg


def estimate_context_size(messages: list[dict[str, Any]]) -> int:
    """Estimate total character count of messages."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            # OpenAI-style multimodal content: [{"type":"text","text":"..."}, ...]
            for part in content:
                if isinstance(part, str):
                    total += len(part)
                elif isinstance(part, dict):
                    for key in ("text", "input_text", "content"):
                        value = part.get(key)
                        if isinstance(value, str):
                            total += len(value)
                            break
        # tool_calls also take space
        tool_calls = msg.get("tool_calls", [])
        for tc in tool_calls:
            func = tc.get("function", {})
            total += len(func.get("arguments", ""))
    return total
