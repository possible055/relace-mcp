from ...config import settings as _settings
from ..prompt_messages import render_system_message


def _resolve_lsp_variant_block(
    value: str | dict[str, str] | None,
    *,
    has_lsp: bool,
    field_name: str,
) -> str:
    """Resolve prompt block text for the current LSP mode."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be a string or mapping, got {type(value).__name__}")

    mode_key = "lsp_on" if has_lsp else "lsp_off"
    selected = value.get(mode_key, value.get("default", ""))
    if selected is None:
        return ""
    if not isinstance(selected, str):
        raise TypeError(f"{field_name}.{mode_key} must be a string, got {type(selected).__name__}")
    return selected


def build_system_prompt(
    template: str,
    *,
    enabled_tools: set[str] | None = None,
    has_lsp: bool = False,
    lsp_section: str = "",
    step2_discovery: str | dict[str, str] | None = None,
    step3_verification: str | dict[str, str] | None = None,
) -> str:
    """Render a system message template into final text.

    Args:
        template: Raw system message template from YAML (contains {max_turns},
            {lsp_section} placeholders).
        enabled_tools: Set of enabled tool names. If bash is absent, bash
            lines are stripped.
        has_lsp: Whether LSP tools are active.
        lsp_section: Raw LSP fragment from YAML to inject when has_lsp is True.
        step2_discovery: Step 2 prompt block. Supports plain string or
            mode mapping with keys: lsp_on, lsp_off, default.
        step3_verification: Step 3 prompt block. Supports plain string or
            mode mapping with keys: lsp_on, lsp_off, default.
    """
    resolved_step2 = _resolve_lsp_variant_block(
        step2_discovery,
        has_lsp=has_lsp,
        field_name="step2_discovery",
    )
    resolved_step3 = _resolve_lsp_variant_block(
        step3_verification,
        has_lsp=has_lsp,
        field_name="step3_verification",
    )

    return render_system_message(
        template,
        max_turns=_settings.SEARCH_MAX_TURNS,
        enabled_tools=enabled_tools,
        has_lsp=has_lsp,
        lsp_section=lsp_section,
        step2_discovery=resolved_step2,
        step3_verification=resolved_step3,
    )
