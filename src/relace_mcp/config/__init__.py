from pathlib import Path

import yaml

from .base_dir import resolve_base_dir

# Public API: RelaceConfig is the main configuration class
from .settings import RelaceConfig

# LLM prompts directory
_LLM_PROMPTS_DIR = Path(__file__).parent / "llm_prompts"

# Load search_relace.yaml (Fast Agentic Search - Relace native)
_PROMPTS_PATH = _LLM_PROMPTS_DIR / "search_relace.yaml"
with _PROMPTS_PATH.open(encoding="utf-8") as f:
    _PROMPTS = yaml.safe_load(f)

# Search prompt constants (prefixed for consistency with APPLY_SYSTEM_PROMPT)
SEARCH_SYSTEM_PROMPT: str = _PROMPTS["system_prompt"].strip()
SEARCH_USER_PROMPT_TEMPLATE: str = _PROMPTS["user_prompt_template"].strip()
SEARCH_TURN_HINT_TEMPLATE: str = _PROMPTS["turn_hint_template"].strip()
SEARCH_TURN_INSTRUCTIONS: dict[str, str] = _PROMPTS["turn_instructions"]

# Load search_openai.yaml (Fast Agentic Search - OpenAI-compatible)
_PROMPTS_OPENAI_PATH = _LLM_PROMPTS_DIR / "search_openai.yaml"
with _PROMPTS_OPENAI_PATH.open(encoding="utf-8") as f:
    _PROMPTS_OPENAI = yaml.safe_load(f)

# OpenAI-compatible search prompt constants
SEARCH_SYSTEM_PROMPT_OPENAI: str = _PROMPTS_OPENAI["system_prompt"].strip()
SEARCH_USER_PROMPT_TEMPLATE_OPENAI: str = _PROMPTS_OPENAI["user_prompt_template"].strip()
SEARCH_TURN_HINT_TEMPLATE_OPENAI: str = _PROMPTS_OPENAI["turn_hint_template"].strip()
SEARCH_TURN_INSTRUCTIONS_OPENAI: dict[str, str] = _PROMPTS_OPENAI["turn_instructions"]

# Load apply_openai.yaml (Fast Apply for OpenAI-compatible endpoints)
_APPLY_PROMPTS_PATH = _LLM_PROMPTS_DIR / "apply_openai.yaml"
with _APPLY_PROMPTS_PATH.open(encoding="utf-8") as f:
    _APPLY_PROMPTS = yaml.safe_load(f)

# Apply prompt constant (only injected for non-Relace endpoints)
APPLY_SYSTEM_PROMPT: str = _APPLY_PROMPTS["apply_system_prompt"].strip()

# Public API exports only
# Internal constants should be imported directly from config.settings
__all__ = [
    # Public API
    "RelaceConfig",
    "resolve_base_dir",
    # Prompts - Relace native (for internal submodule use)
    "SEARCH_SYSTEM_PROMPT",
    "SEARCH_USER_PROMPT_TEMPLATE",
    "SEARCH_TURN_HINT_TEMPLATE",
    "SEARCH_TURN_INSTRUCTIONS",
    # Prompts - OpenAI-compatible
    "SEARCH_SYSTEM_PROMPT_OPENAI",
    "SEARCH_USER_PROMPT_TEMPLATE_OPENAI",
    "SEARCH_TURN_HINT_TEMPLATE_OPENAI",
    "SEARCH_TURN_INSTRUCTIONS_OPENAI",
    # Apply prompt
    "APPLY_SYSTEM_PROMPT",
]
