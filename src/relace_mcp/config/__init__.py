from pathlib import Path

import yaml

from .base_dir import resolve_base_dir

# Public API: RelaceConfig is the main configuration class
from .settings import RelaceConfig

# Load search_prompts.yaml (Fast Agentic Search)
_PROMPTS_PATH = Path(__file__).parent / "search_prompts.yaml"
with _PROMPTS_PATH.open(encoding="utf-8") as f:
    _PROMPTS = yaml.safe_load(f)

# Search prompt constants (prefixed for consistency with APPLY_SYSTEM_PROMPT)
SEARCH_SYSTEM_PROMPT: str = _PROMPTS["system_prompt"].strip()
SEARCH_USER_PROMPT_TEMPLATE: str = _PROMPTS["user_prompt_template"].strip()
SEARCH_BUDGET_HINT_TEMPLATE: str = _PROMPTS["budget_hint_template"].strip()
SEARCH_CONVERGENCE_HINT: str = _PROMPTS["convergence_hint"].strip()
SEARCH_STRATEGIES: dict[str, str] = _PROMPTS["strategies"]

# Load apply_prompts.yaml (Fast Apply for OpenAI-compatible endpoints)
_APPLY_PROMPTS_PATH = Path(__file__).parent / "apply_prompts.yaml"
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
    # Prompts (for internal submodule use)
    "SEARCH_SYSTEM_PROMPT",
    "SEARCH_USER_PROMPT_TEMPLATE",
    "SEARCH_BUDGET_HINT_TEMPLATE",
    "SEARCH_CONVERGENCE_HINT",
    "SEARCH_STRATEGIES",
    "APPLY_SYSTEM_PROMPT",
]
