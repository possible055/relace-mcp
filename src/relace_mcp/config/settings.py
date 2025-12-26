import logging
import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_state_dir

logger = logging.getLogger(__name__)

# Fast Apply (OpenAI-compatible base URL; SDK appends /chat/completions automatically)
RELACE_APPLY_BASE_URL = os.getenv(
    "RELACE_APPLY_ENDPOINT",
    "https://instantapply.endpoint.relace.run/v1/apply",
)
RELACE_APPLY_MODEL = os.getenv("RELACE_APPLY_MODEL", "auto")
TIMEOUT_SECONDS = float(os.getenv("RELACE_TIMEOUT_SECONDS", "60.0"))
MAX_RETRIES = int(os.getenv("RELACE_MAX_RETRIES", "3"))
RETRY_BASE_DELAY = float(os.getenv("RELACE_RETRY_BASE_DELAY", "1.0"))

# Fast Agentic Search (OpenAI-compatible base URL; SDK appends /chat/completions automatically)
RELACE_SEARCH_BASE_URL = os.getenv(
    "RELACE_SEARCH_ENDPOINT",
    "https://search.endpoint.relace.run/v1/search",
)
RELACE_SEARCH_MODEL = os.getenv("RELACE_SEARCH_MODEL", "relace-search")
SEARCH_TIMEOUT_SECONDS = float(os.getenv("RELACE_SEARCH_TIMEOUT_SECONDS", "120.0"))
SEARCH_MAX_TURNS = int(os.getenv("RELACE_SEARCH_MAX_TURNS", "6"))

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


# Encoding detection: explicitly set project default encoding (e.g., "gbk", "big5", "shift_jis")
# If not set, auto-detection will be attempted at startup
RELACE_DEFAULT_ENCODING = os.getenv("RELACE_DEFAULT_ENCODING", None)
# Maximum files to sample for encoding detection (higher = more accurate but slower startup)
ENCODING_DETECTION_SAMPLE_LIMIT = int(os.getenv("RELACE_ENCODING_SAMPLE_LIMIT", "30"))

# EXPERIMENTAL: Post-check validation (validates merged_code semantic correctness, disabled by default)
EXPERIMENTAL_POST_CHECK = os.getenv("RELACE_EXPERIMENTAL_POST_CHECK", "").lower() in (
    "1",
    "true",
    "yes",
)

# Local file logging (disabled by default)
# Use RELACE_LOGGING=1 to enable (RELACE_EXPERIMENTAL_LOGGING still works for backward compat)
_logging_env = os.getenv("RELACE_LOGGING", "").lower()
if not _logging_env:
    _logging_env = os.getenv("RELACE_EXPERIMENTAL_LOGGING", "").lower()
RELACE_LOGGING = _logging_env in ("1", "true", "yes")

# Logging - Cross-platform state directory:
# - Linux: ~/.local/state/relace
# - macOS: ~/Library/Application Support/relace
# - Windows: %LOCALAPPDATA%\relace
# Note: Directory is created lazily in logging.py when actually writing logs
LOG_DIR = Path(user_state_dir("relace", appauthor=False))
LOG_PATH = LOG_DIR / "relace.log"
MAX_LOG_SIZE_BYTES = 10 * 1024 * 1024


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

        base_dir = os.getenv("RELACE_BASE_DIR")
        if base_dir:
            base_dir = os.path.abspath(base_dir)
            if not os.path.isdir(base_dir):
                raise RuntimeError(
                    f"RELACE_BASE_DIR does not exist or is not a directory: {base_dir}"
                )
            logger.info("Using RELACE_BASE_DIR: %s", base_dir)
        else:
            logger.info("RELACE_BASE_DIR not set; will resolve from MCP Roots or cwd at runtime")

        # default_encoding from env (will be overridden by detection if None)
        default_encoding = RELACE_DEFAULT_ENCODING

        return cls(api_key=api_key, base_dir=base_dir, default_encoding=default_encoding)
