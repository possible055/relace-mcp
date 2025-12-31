from ....config import (
    SEARCH_SYSTEM_PROMPT,
    SEARCH_SYSTEM_PROMPT_OPENAI,
    SEARCH_TURN_HINT_TEMPLATE,
    SEARCH_TURN_HINT_TEMPLATE_OPENAI,
    SEARCH_TURN_INSTRUCTIONS,
    SEARCH_TURN_INSTRUCTIONS_OPENAI,
    SEARCH_USER_PROMPT_TEMPLATE,
    SEARCH_USER_PROMPT_TEMPLATE_OPENAI,
)
from .prompts import build_find_symbol_section, build_system_prompt
from .tool_schemas import TOOL_SCHEMAS, get_tool_schemas, normalize_tool_schemas
from .types import GrepSearchParams

# Shorter aliases for internal use within the search module (Relace native)
SYSTEM_PROMPT = SEARCH_SYSTEM_PROMPT
USER_PROMPT_TEMPLATE = SEARCH_USER_PROMPT_TEMPLATE
TURN_HINT_TEMPLATE = SEARCH_TURN_HINT_TEMPLATE
TURN_INSTRUCTIONS = SEARCH_TURN_INSTRUCTIONS

# OpenAI-compatible prompts
SYSTEM_PROMPT_OPENAI = SEARCH_SYSTEM_PROMPT_OPENAI
USER_PROMPT_TEMPLATE_OPENAI = SEARCH_USER_PROMPT_TEMPLATE_OPENAI
TURN_HINT_TEMPLATE_OPENAI = SEARCH_TURN_HINT_TEMPLATE_OPENAI
TURN_INSTRUCTIONS_OPENAI = SEARCH_TURN_INSTRUCTIONS_OPENAI

__all__ = [
    "GrepSearchParams",
    # Export aliases for backward compatibility within search module (Relace native)
    "SYSTEM_PROMPT",
    "USER_PROMPT_TEMPLATE",
    "TURN_HINT_TEMPLATE",
    "TURN_INSTRUCTIONS",
    # OpenAI-compatible prompts
    "SYSTEM_PROMPT_OPENAI",
    "USER_PROMPT_TEMPLATE_OPENAI",
    "TURN_HINT_TEMPLATE_OPENAI",
    "TURN_INSTRUCTIONS_OPENAI",
    # Tool schemas
    "get_tool_schemas",
    "normalize_tool_schemas",
    "TOOL_SCHEMAS",
    # Dynamic prompt building
    "build_find_symbol_section",
    "build_system_prompt",
]
