import logging
import os
from pathlib import Path
from typing import Any

import yaml

from .base_dir import invalidate_roots_cache, resolve_base_dir
from .provider import ProviderConfig, create_provider_config

# Public API: RelaceConfig is the main configuration class
from .settings import RelaceConfig

logger = logging.getLogger(__name__)

# LLM prompts directory (relocated to prompts/)
_LLM_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt_file(default_path: Path, env_var: str) -> dict[str, Any]:
    """Load prompt file from custom path (env var) or default path."""
    custom_path = os.getenv(env_var, "").strip()
    if custom_path:
        custom_path_obj = Path(custom_path).expanduser()
        if custom_path_obj.exists():
            logger.debug("Loading custom prompt from %s (via %s)", custom_path_obj, env_var)
            with custom_path_obj.open(encoding="utf-8") as f:
                result = yaml.safe_load(f)
            if result is None:
                raise ValueError(
                    f"Prompt file is empty or contains only comments: {custom_path_obj}"
                )
            if not isinstance(result, dict):
                raise TypeError(
                    f"Prompt file must be a YAML mapping (dict), got {type(result).__name__}: {custom_path_obj}"
                )
            return result
        else:
            logger.warning("%s=%s does not exist, falling back to default", env_var, custom_path)

    with default_path.open(encoding="utf-8") as f:
        result = yaml.safe_load(f)
    if result is None:
        raise ValueError(f"Prompt file is empty or contains only comments: {default_path}")
    if not isinstance(result, dict):
        raise TypeError(
            f"Prompt file must be a YAML mapping (dict), got {type(result).__name__}: {default_path}"
        )
    return result


def _resolve_system_prompt(yaml_value: str, env_var: str) -> str:
    """Resolve system prompt: env var text override takes precedence over YAML value."""
    override = os.getenv(env_var, "").strip()
    if override:
        logger.debug("Using system prompt override from %s", env_var)
        return override
    return yaml_value.strip()


# Load search_relace.yaml (Relace native - shared by search & retrieval)
# File-level override: SEARCH_PROMPT_FILE_RELACE
_PROMPTS_PATH = _LLM_PROMPTS_DIR / "search_relace.yaml"
_PROMPTS = _load_prompt_file(_PROMPTS_PATH, "SEARCH_PROMPT_FILE_RELACE")

# Relace prompt constants (text-level override: SEARCH_SYSTEM_PROMPT_RELACE)
SEARCH_SYSTEM_PROMPT: str = _resolve_system_prompt(
    _PROMPTS["system_prompt"], "SEARCH_SYSTEM_PROMPT_RELACE"
)
SEARCH_USER_PROMPT_TEMPLATE: str = _PROMPTS["user_prompt_template"].strip()
SEARCH_TURN_HINT_TEMPLATE: str = _PROMPTS["turn_hint_template"].strip()
SEARCH_TURN_INSTRUCTIONS: dict[str, str] = _PROMPTS["turn_instructions"]

# Load search_openai.yaml (OpenAI-compatible - shared by search & retrieval)
# File-level override: SEARCH_PROMPT_FILE_OPENAI
_PROMPTS_OPENAI_PATH = _LLM_PROMPTS_DIR / "search_openai.yaml"
_PROMPTS_OPENAI = _load_prompt_file(_PROMPTS_OPENAI_PATH, "SEARCH_PROMPT_FILE_OPENAI")

# OpenAI-compatible prompt constants (text-level override: SEARCH_SYSTEM_PROMPT_OPENAI)
SEARCH_SYSTEM_PROMPT_OPENAI: str = _resolve_system_prompt(
    _PROMPTS_OPENAI["system_prompt"], "SEARCH_SYSTEM_PROMPT_OPENAI"
)
SEARCH_USER_PROMPT_TEMPLATE_OPENAI: str = _PROMPTS_OPENAI["user_prompt_template"].strip()
SEARCH_TURN_HINT_TEMPLATE_OPENAI: str = _PROMPTS_OPENAI["turn_hint_template"].strip()
SEARCH_TURN_INSTRUCTIONS_OPENAI: dict[str, str] = _PROMPTS_OPENAI["turn_instructions"]

# Load apply_openai.yaml (Fast Apply for OpenAI-compatible endpoints)
# Override with APPLY_PROMPT_FILE if set
_APPLY_PROMPTS_PATH = _LLM_PROMPTS_DIR / "apply_openai.yaml"
_APPLY_PROMPTS = _load_prompt_file(_APPLY_PROMPTS_PATH, "APPLY_PROMPT_FILE")

# Apply prompt constant (only injected for non-Relace endpoints)
APPLY_SYSTEM_PROMPT: str = _APPLY_PROMPTS["apply_system_prompt"].strip()

# Public API exports only
__all__ = [
    # Public API
    "RelaceConfig",
    "ProviderConfig",
    "create_provider_config",
    "resolve_base_dir",
    "invalidate_roots_cache",
    # Prompts - Relace native
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
