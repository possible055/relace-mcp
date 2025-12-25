from ....config import (
    SEARCH_BUDGET_HINT_TEMPLATE,
    SEARCH_CONVERGENCE_HINT,
    SEARCH_STRATEGIES,
    SEARCH_SYSTEM_PROMPT,
    SEARCH_USER_PROMPT_TEMPLATE,
)
from .tool_schemas import TOOL_SCHEMAS, get_tool_schemas, normalize_tool_schemas
from .types import GrepSearchParams

# Shorter aliases for internal use within the search module
SYSTEM_PROMPT = SEARCH_SYSTEM_PROMPT
USER_PROMPT_TEMPLATE = SEARCH_USER_PROMPT_TEMPLATE
BUDGET_HINT_TEMPLATE = SEARCH_BUDGET_HINT_TEMPLATE
CONVERGENCE_HINT = SEARCH_CONVERGENCE_HINT
STRATEGIES = SEARCH_STRATEGIES

__all__ = [
    "GrepSearchParams",
    # Export aliases for backward compatibility within search module
    "SYSTEM_PROMPT",
    "USER_PROMPT_TEMPLATE",
    "BUDGET_HINT_TEMPLATE",
    "CONVERGENCE_HINT",
    "STRATEGIES",
    "get_tool_schemas",
    "normalize_tool_schemas",
    "TOOL_SCHEMAS",
]
