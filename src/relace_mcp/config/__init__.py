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

# Env var mapping: yaml file stem -> (file-level override, system_prompt text override)
_PROMPT_ENV_VARS: dict[str, tuple[str, str]] = {
    "search_relace": ("SEARCH_PROMPT_FILE_RELACE", "SEARCH_SYSTEM_PROMPT_RELACE"),
    "search_openai": ("SEARCH_PROMPT_FILE_OPENAI", "SEARCH_SYSTEM_PROMPT_OPENAI"),
    "retrieval_relace": ("RETRIEVAL_PROMPT_FILE_RELACE", "RETRIEVAL_SYSTEM_PROMPT_RELACE"),
    "retrieval_openai": ("RETRIEVAL_PROMPT_FILE_OPENAI", "RETRIEVAL_SYSTEM_PROMPT_OPENAI"),
}


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


def load_prompt_file(name: str) -> dict[str, Any]:
    """Load a named prompt YAML file with env var overrides.

    Args:
        name: Prompt file stem, one of:
            'search_relace', 'search_openai',
            'retrieval_relace', 'retrieval_openai'.

    Returns:
        Dict with keys: system_prompt, user_prompt_template,
        turn_hint_template, turn_instructions, lsp_section.
    """
    env_vars = _PROMPT_ENV_VARS.get(name)
    if env_vars is None:
        raise ValueError(
            f"Unknown prompt name: {name!r}. Must be one of {sorted(_PROMPT_ENV_VARS)}"
        )

    file_env, prompt_env = env_vars
    path = _LLM_PROMPTS_DIR / f"{name}.yaml"
    data = _load_prompt_file(path, file_env)

    # Apply text-level system_prompt override
    if "system_prompt" in data:
        data["system_prompt"] = _resolve_system_prompt(data["system_prompt"], prompt_env)

    return data


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
    # Prompt loading
    "load_prompt_file",
    # Apply prompt
    "APPLY_SYSTEM_PROMPT",
]
