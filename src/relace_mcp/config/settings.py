import logging
import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_state_dir

from .compat import env_bool, getenv_with_fallback

logger = logging.getLogger(__name__)

__all__ = [
    "RELACE_CLOUD_TOOLS",
    "RelaceConfig",
]

# Fast Apply (OpenAI-compatible base URL; SDK appends /chat/completions automatically)
APPLY_BASE_URL = (
    getenv_with_fallback("APPLY_ENDPOINT", "RELACE_APPLY_ENDPOINT")
    or "https://instantapply.endpoint.relace.run/v1/apply"
)
APPLY_MODEL = getenv_with_fallback("APPLY_MODEL", "RELACE_APPLY_MODEL") or "auto"
TIMEOUT_SECONDS = float(
    getenv_with_fallback("APPLY_TIMEOUT_SECONDS", "RELACE_TIMEOUT_SECONDS") or "60.0"
)
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0

# Temperature settings for each tool
SEARCH_TEMPERATURE = float(os.getenv("SEARCH_TEMPERATURE", "1.0"))
APPLY_TEMPERATURE = float(os.getenv("APPLY_TEMPERATURE", "0.0"))

# Provider identifiers (used for API compatibility detection)
OPENAI_PROVIDER = "openai"
RELACE_PROVIDER = "relace"

# Default base URLs for known providers (fallback when env var not set)
DEFAULT_PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "cerebras": "https://api.cerebras.ai/v1",
}

# Fast Agentic Search (OpenAI-compatible base URL; SDK appends /chat/completions automatically)
SEARCH_BASE_URL = (
    getenv_with_fallback("SEARCH_ENDPOINT", "RELACE_SEARCH_ENDPOINT")
    or "https://search.endpoint.relace.run/v1/search"
)
SEARCH_MODEL = getenv_with_fallback("SEARCH_MODEL", "RELACE_SEARCH_MODEL") or "relace-search"
SEARCH_TIMEOUT_SECONDS = float(
    getenv_with_fallback("SEARCH_TIMEOUT_SECONDS", "RELACE_SEARCH_TIMEOUT_SECONDS") or "120.0"
)
SEARCH_MAX_TURNS = int(getenv_with_fallback("SEARCH_MAX_TURNS", "RELACE_SEARCH_MAX_TURNS") or "6")
# Search parallel tool calls (default: true)
SEARCH_PARALLEL_TOOL_CALLS = env_bool(
    "SEARCH_PARALLEL_TOOL_CALLS",
    default=True,
    deprecated_name="RELACE_SEARCH_PARALLEL_TOOL_CALLS",
)

# Relace Repos API (Infrastructure Endpoint for cloud sync/search)
RELACE_API_ENDPOINT = os.getenv(
    "RELACE_API_ENDPOINT",
    "https://api.relace.run/v1",
)
# Optional: Pre-configured Repo ID (skip list/create if set)
RELACE_REPO_ID = os.getenv("RELACE_REPO_ID", None)
# Repo sync settings
REPO_SYNC_TIMEOUT_SECONDS = float(os.getenv("RELACE_REPO_SYNC_TIMEOUT", "300.0"))
REPO_SYNC_MAX_FILES = int(os.getenv("RELACE_REPO_SYNC_MAX_FILES", "5000"))
# Maximum repos to fetch (100 pages * 100 per page)
REPO_LIST_MAX = int(os.getenv("RELACE_REPO_LIST_MAX", "10000"))


# Encoding detection: explicitly set project default encoding (e.g., "gbk", "big5", "shift_jis")
# If not set, auto-detection will be attempted at startup
RELACE_DEFAULT_ENCODING = os.getenv("RELACE_DEFAULT_ENCODING", None)
# Maximum files to sample for encoding detection (higher = more accurate but slower startup)
ENCODING_DETECTION_SAMPLE_LIMIT = 30

# EXPERIMENTAL: Post-check validation (validates merged_code semantic correctness, disabled by default)
# Use APPLY_POST_CHECK=1 to enable (RELACE_EXPERIMENTAL_POST_CHECK still works for backward compat)
_post_check_env = getenv_with_fallback("APPLY_POST_CHECK", "RELACE_EXPERIMENTAL_POST_CHECK")
EXPERIMENTAL_POST_CHECK = _post_check_env.lower() in ("1", "true", "yes")

# Local file logging (disabled by default)
# Use MCP_LOGGING=1 to enable (RELACE_LOGGING still works for backward compat)
_logging_env = getenv_with_fallback("MCP_LOGGING", "RELACE_LOGGING").lower()
if not _logging_env:
    _logging_env = os.getenv("RELACE_EXPERIMENTAL_LOGGING", "").lower()
MCP_LOGGING = _logging_env in ("1", "true", "yes")

# Cloud tools (disabled by default)
# Use RELACE_CLOUD_TOOLS=1 to enable cloud_sync, cloud_search, cloud_list, cloud_info, cloud_clear
RELACE_CLOUD_TOOLS = os.getenv("RELACE_CLOUD_TOOLS", "").lower() in ("1", "true", "yes")

# Logging - Cross-platform state directory:
# - Linux: ~/.local/state/relace
# - macOS: ~/Library/Application Support/relace
# - Windows: %LOCALAPPDATA%\relace
# Note: Directory is created lazily in logging.py when actually writing logs
LOG_DIR = Path(user_state_dir("relace", appauthor=False))
LOG_PATH = LOG_DIR / "relace.log"
MAX_LOG_SIZE_BYTES = 10 * 1024 * 1024

# File size limit (10MB) to prevent memory exhaustion on file read/write operations
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class RelaceConfig:
    api_key: str
    base_dir: str | None = None  # Optional; resolved dynamically from MCP Roots if not set
    default_encoding: str | None = None  # Project-level encoding (detected or env-specified)

    @classmethod
    def from_env(cls) -> "RelaceConfig":
        api_key = os.getenv("RELACE_API_KEY")
        if not api_key:
            raise RuntimeError("RELACE_API_KEY is not set. Please export it in your environment.")

        base_dir = getenv_with_fallback("MCP_BASE_DIR", "RELACE_BASE_DIR") or None
        if base_dir:
            if not os.path.isdir(base_dir):
                raise RuntimeError(f"MCP_BASE_DIR does not exist or is not a directory: {base_dir}")
            logger.info("Using MCP_BASE_DIR: %s", base_dir)
        else:
            logger.info("MCP_BASE_DIR not set; will resolve from MCP Roots or cwd at runtime")

        # default_encoding from env (will be overridden by detection if None)
        default_encoding = RELACE_DEFAULT_ENCODING

        return cls(api_key=api_key, base_dir=base_dir, default_encoding=default_encoding)
