"""Configuration module for relace-mcp."""

from pathlib import Path

import yaml

from .settings import (
    BACKUP_DIR,
    LOG_DIR,
    LOG_PATH,
    MAX_LOG_SIZE_BYTES,
    MAX_RETRIES,
    RELACE_BACKUP_ENABLED,
    RELACE_ENDPOINT,
    RELACE_MODEL,
    RELACE_SEARCH_ENDPOINT,
    RELACE_SEARCH_MODEL,
    RELACE_STRICT_MODE,
    RETRY_BASE_DELAY,
    SEARCH_MAX_TURNS,
    SEARCH_TIMEOUT_SECONDS,
    TIMEOUT_SECONDS,
    RelaceConfig,
)

# 載入 prompts.yaml
_PROMPTS_PATH = Path(__file__).parent / "prompts.yaml"
with _PROMPTS_PATH.open(encoding="utf-8") as f:
    _PROMPTS = yaml.safe_load(f)

# Prompt 相關常數
SYSTEM_PROMPT: str = _PROMPTS["system_prompt"].strip()
USER_PROMPT_TEMPLATE: str = _PROMPTS["user_prompt_template"].strip()
BUDGET_HINT_TEMPLATE: str = _PROMPTS["budget_hint_template"].strip()
CONVERGENCE_HINT: str = _PROMPTS["convergence_hint"].strip()
STRATEGIES: dict[str, str] = _PROMPTS["strategies"]

__all__ = [
    # Settings
    "BACKUP_DIR",
    "LOG_DIR",
    "LOG_PATH",
    "MAX_LOG_SIZE_BYTES",
    "MAX_RETRIES",
    "RELACE_BACKUP_ENABLED",
    "RELACE_ENDPOINT",
    "RELACE_MODEL",
    "RELACE_SEARCH_ENDPOINT",
    "RELACE_SEARCH_MODEL",
    "RELACE_STRICT_MODE",
    "RETRY_BASE_DELAY",
    "SEARCH_MAX_TURNS",
    "SEARCH_TIMEOUT_SECONDS",
    "TIMEOUT_SECONDS",
    "RelaceConfig",
    # Prompts
    "SYSTEM_PROMPT",
    "USER_PROMPT_TEMPLATE",
    "BUDGET_HINT_TEMPLATE",
    "CONVERGENCE_HINT",
    "STRATEGIES",
]
