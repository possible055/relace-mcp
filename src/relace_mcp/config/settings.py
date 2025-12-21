import logging
import os
from dataclasses import dataclass
from pathlib import Path

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

# Strict mode: enforce safe settings
RELACE_STRICT_MODE = os.getenv("RELACE_STRICT_MODE", "0") == "1"

# EXPERIMENTAL: Post-check validation (validates merged_code semantic correctness, disabled by default)
EXPERIMENTAL_POST_CHECK = os.getenv("RELACE_EXPERIMENTAL_POST_CHECK", "").lower() in (
    "1",
    "true",
    "yes",
)

# EXPERIMENTAL: Local file logging (disabled by default)
EXPERIMENTAL_LOGGING = os.getenv("RELACE_EXPERIMENTAL_LOGGING", "").lower() in (
    "1",
    "true",
    "yes",
)

# Logging
LOG_DIR = Path(os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state"))) / "relace"
LOG_PATH = LOG_DIR / "relace_apply.log"
MAX_LOG_SIZE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class RelaceConfig:
    api_key: str
    base_dir: str

    @classmethod
    def from_env(cls) -> "RelaceConfig":
        api_key = os.getenv("RELACE_API_KEY")
        if not api_key:
            raise RuntimeError("RELACE_API_KEY is not set. Please export it in your environment.")

        base_dir = os.getenv("RELACE_BASE_DIR")
        if base_dir:
            base_dir = os.path.abspath(base_dir)
        elif RELACE_STRICT_MODE:
            raise RuntimeError(
                "RELACE_STRICT_MODE is enabled but RELACE_BASE_DIR is not set. "
                "Explicitly set RELACE_BASE_DIR to restrict file access."
            )
        else:
            base_dir = os.getcwd()
            logger.warning(
                "RELACE_BASE_DIR not set. Defaulting to current directory: %s. "
                "For production, explicitly set RELACE_BASE_DIR to restrict file access.",
                base_dir,
            )

        if not os.path.isdir(base_dir):
            raise RuntimeError(f"RELACE_BASE_DIR does not exist or is not a directory: {base_dir}")

        return cls(api_key=api_key, base_dir=base_dir)
