import logging
from collections.abc import Mapping

logger = logging.getLogger(__name__)


def build_system_prompt(
    template: str,
    languages: frozenset[str],
    enabled_tools: set[str] | None = None,
    context: Mapping[str, object] | None = None,
) -> str:
    return template.replace("\n\n\n", "\n\n").strip()
