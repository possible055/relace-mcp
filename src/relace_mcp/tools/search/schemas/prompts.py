import logging
import os
from collections.abc import Mapping

logger = logging.getLogger(__name__)

_DEFAULT_MAX_TURNS = 6


def _resolve_max_turns() -> int:
    raw = os.getenv("SEARCH_MAX_TURNS", "").strip()
    if not raw:
        return _DEFAULT_MAX_TURNS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_TURNS
    return value if value > 0 else _DEFAULT_MAX_TURNS


def build_system_prompt(
    template: str,
    languages: frozenset[str],
    enabled_tools: set[str] | None = None,
    context: Mapping[str, object] | None = None,
) -> str:
    prompt = template.replace("{max_turns}", str(_resolve_max_turns()))

    if enabled_tools is not None and "bash" not in enabled_tools:
        prompt = "\n".join(line for line in prompt.splitlines() if "`bash`" not in line)

    return prompt.replace("\n\n\n", "\n\n").strip()
