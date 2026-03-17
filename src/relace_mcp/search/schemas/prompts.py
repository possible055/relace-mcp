import logging

from ...config import settings as _settings

logger = logging.getLogger(__name__)


def _resolve_max_turns() -> int:
    return _settings.SEARCH_MAX_TURNS


def build_system_prompt(
    template: str,
    *,
    enabled_tools: set[str] | None = None,
    has_lsp: bool = False,
    lsp_section: str = "",
) -> str:
    """Render a system prompt template into final text.

    Args:
        template: Raw system_prompt string from YAML (contains {max_turns},
            {lsp_section} placeholders).
        enabled_tools: Set of enabled tool names. If bash is absent, bash
            lines are stripped.
        has_lsp: Whether LSP tools are active.
        lsp_section: Raw LSP fragment from YAML to inject when has_lsp is True.
    """
    prompt = template.replace("{max_turns}", str(_resolve_max_turns()))

    if has_lsp and lsp_section:
        prompt = prompt.replace("{lsp_section}", lsp_section.strip())
    else:
        prompt = prompt.replace("{lsp_section}", "")

    if enabled_tools is not None and "bash" not in enabled_tools:
        prompt = "\n".join(line for line in prompt.splitlines() if "`bash`" not in line)

    return prompt.replace("\n\n\n", "\n\n").strip()
