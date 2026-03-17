import logging
from pathlib import Path
from typing import Any

import yaml

from . import settings as _settings
from .base_dir import invalidate_roots_cache, resolve_base_dir
from .provider import ProviderConfig, create_provider_config
from .settings import RelaceConfig

logger = logging.getLogger(__name__)

_LLM_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

_PROMPT_ENV_VARS: dict[str, str] = {
    "search_relace": "SEARCH_PROMPT_FILE",
    "search_openai": "SEARCH_PROMPT_FILE",
    "retrieval_relace": "RETRIEVAL_PROMPT_FILE",
    "retrieval_openai": "RETRIEVAL_PROMPT_FILE",
}


def _load_prompt_file(default_path: Path, env_var: str) -> dict[str, Any]:
    """Load prompt file from centralized settings override or default path."""
    custom_path = getattr(_settings, env_var, None) or ""
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


def load_prompt_file(name: str) -> dict[str, Any]:
    """Load a named prompt YAML file with env var overrides."""
    file_env = _PROMPT_ENV_VARS.get(name)
    if file_env is None:
        raise ValueError(
            f"Unknown prompt name: {name!r}. Must be one of {sorted(_PROMPT_ENV_VARS)}"
        )

    path = _LLM_PROMPTS_DIR / f"{name}.yaml"
    return _load_prompt_file(path, file_env)


def load_apply_system_prompt() -> str:
    """Load the apply system prompt, honoring APPLY_PROMPT_FILE overrides at runtime."""
    prompts = _load_prompt_file(_LLM_PROMPTS_DIR / "apply_openai.yaml", "APPLY_PROMPT_FILE")
    prompt = prompts.get("apply_system_prompt")
    if not isinstance(prompt, str):
        raise TypeError("apply_system_prompt must be a string")
    return prompt.strip()


__all__ = [
    "RelaceConfig",
    "ProviderConfig",
    "create_provider_config",
    "resolve_base_dir",
    "invalidate_roots_cache",
    "load_prompt_file",
    "load_apply_system_prompt",
]
