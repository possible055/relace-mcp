import re
from typing import Any

from .harness.constants import MAX_CONTEXT_BUDGET_CHARS


def render_system_message(
    template: str,
    *,
    max_turns: int,
    enabled_tools: set[str] | None = None,
    has_lsp: bool = False,
    lsp_section: str = "",
    step2_discovery: str = "",
    step3_verification: str = "",
    # Modular LSP fragments (used by openai backend).
    lsp_routing_rules: str = "",
    lsp_tools_section: str = "",
    lsp_followup_rules: str = "",
) -> str:
    """Render a system message template into final text."""
    message = template.replace("{max_turns}", str(max_turns))

    # Legacy monolithic LSP block (relace backend).
    if has_lsp and lsp_section:
        message = message.replace("{lsp_section}", lsp_section.strip())
    else:
        message = message.replace("{lsp_section}", "")

    # Legacy step-based strategy blocks (relace backend).
    message = message.replace("{step2_discovery}", step2_discovery.strip())
    message = message.replace("{step3_verification}", step3_verification.strip())

    # Modular LSP capability fragments (openai backend).
    message = message.replace("{lsp_routing_rules}", lsp_routing_rules.strip())
    message = message.replace("{lsp_tools_section}", lsp_tools_section.strip())
    message = message.replace("{lsp_followup_rules}", lsp_followup_rules.strip())

    if enabled_tools is not None and "bash" not in enabled_tools:
        message = "\n".join(line for line in message.splitlines() if "`bash`" not in line)

    return re.sub(r"\n{3,}", "\n\n", message).strip()


def should_append_turn_status(turn: int, mode: str, max_turns: int) -> bool:
    """Decide whether the current turn should append a turn-status message."""
    if turn <= 0 or mode == "off":
        return False
    if mode == "final-only":
        return turn == max_turns - 1
    return True


def render_turn_status_message(
    turn: int,
    max_turns: int,
    chars_used: int,
    turn_status_messages: dict[str, str],
) -> str:
    """Render the user-visible turn-status message.

    Message key selection (0-indexed *turn*):
      - remaining == 1  → "final"
      - remaining == 2  → "penultimate" (falls back to "normal" if absent)
      - otherwise       → "normal"
    """
    remaining = max_turns - turn
    if remaining == 1:
        message_key = "final"
    elif remaining == 2 and "penultimate" in turn_status_messages:
        message_key = "penultimate"
    else:
        message_key = "normal"
    template = turn_status_messages.get(message_key, "")
    if not template:
        return ""
    chars_pct = int((chars_used / MAX_CONTEXT_BUDGET_CHARS) * 100)

    return template.format(
        turn=turn + 1,
        max_turns=max_turns,
        chars_pct=chars_pct,
    )


def format_hints_list(hints: list[dict[str, Any]]) -> str:
    """Format semantic hints as a bullet list for {hints_list} placeholder."""
    return "\n".join(f"- {h['filename']} (score: {h['score']:.2f})" for h in hints)
