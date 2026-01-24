import logging
import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_state_dir

from .compat import env_bool

logger = logging.getLogger(__name__)

__all__ = [
    "RELACE_CLOUD_TOOLS",
    "RETRIEVAL_BACKEND",
    "SEARCH_LSP_TOOLS_MODE",
    "RelaceConfig",
]

# Fast Apply (OpenAI-compatible base URL; SDK appends /chat/completions automatically)
APPLY_BASE_URL = (
    os.getenv("APPLY_ENDPOINT", "") or "https://instantapply.endpoint.relace.run/v1/apply"
)
APPLY_MODEL = os.getenv("APPLY_MODEL", "") or "auto"
TIMEOUT_SECONDS = float(os.getenv("APPLY_TIMEOUT_SECONDS", "") or "60.0")
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
SEARCH_BASE_URL = os.getenv("SEARCH_ENDPOINT", "") or "https://search.endpoint.relace.run/v1/search"
SEARCH_MODEL = os.getenv("SEARCH_MODEL", "") or "relace-search"
SEARCH_TIMEOUT_SECONDS = float(os.getenv("SEARCH_TIMEOUT_SECONDS", "") or "120.0")
SEARCH_MAX_TURNS = int(os.getenv("SEARCH_MAX_TURNS", "") or "6")
# Search parallel tool calls (default: true)
SEARCH_PARALLEL_TOOL_CALLS = env_bool("SEARCH_PARALLEL_TOOL_CALLS", default=True)
# Search top_p (optional, only set if explicitly configured)
# Some providers (e.g., Mistral) require top_p=1 for greedy sampling (temperature=0)
_search_top_p_raw = os.getenv("SEARCH_TOP_P", "").strip()
SEARCH_TOP_P: float | None = float(_search_top_p_raw) if _search_top_p_raw else None


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


# Semantic check (validates new/delete intent correctness, disabled by default)
APPLY_SEMANTIC_CHECK = env_bool("APPLY_SEMANTIC_CHECK", default=False)

# Local file logging mode (default: off)
# Options: off (disabled), safe (enabled with redaction), full (enabled without redaction)
_MCP_LOGGING_RAW = os.getenv("MCP_LOGGING", "off").strip().lower()
MCP_LOGGING = _MCP_LOGGING_RAW in ("safe", "full", "1", "true", "yes")
MCP_LOG_REDACT = _MCP_LOGGING_RAW != "full"

# Cloud tools (disabled by default)
RELACE_CLOUD_TOOLS = env_bool("RELACE_CLOUD_TOOLS", default=False)
RETRIEVAL_BACKEND = os.getenv("MCP_RETRIEVAL_BACKEND", "relace").strip().lower()


# Enable agentic_retrieval tool (requires cloud sync or local backend)
AGENTIC_RETRIEVAL_ENABLED = env_bool("MCP_SEARCH_RETRIEVAL", default=False)


# LSP tools mode: 'false' (disabled), 'true' (all enabled), or 'auto' (detect installed servers)
def _get_lsp_tools_mode() -> str:
    raw = os.environ.get("SEARCH_LSP_TOOLS", "").strip().lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return "true"
    if raw == "auto":
        return "auto"
    return "false"


SEARCH_LSP_TOOLS_MODE = _get_lsp_tools_mode()

# Agentic retrieval auto-sync (enabled by default when cloud tools are enabled)
AGENTIC_AUTO_SYNC = env_bool("RELACE_AGENTIC_AUTO_SYNC", default=True)

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
    api_key: str | None = None  # Optional; required only when using Relace services
    base_dir: str | None = None  # Optional; resolved dynamically from MCP Roots if not set
    default_encoding: str | None = None  # Project-level encoding (detected or env-specified)

    @classmethod
    def from_env(cls) -> "RelaceConfig":
        api_key = os.getenv("RELACE_API_KEY") or None

        # Cloud tools require Relace API key (Repo API is Relace-only)
        if RELACE_CLOUD_TOOLS and not api_key:
            raise RuntimeError(
                "RELACE_API_KEY is required when RELACE_CLOUD_TOOLS=true. "
                "Set RELACE_CLOUD_TOOLS=false or provide RELACE_API_KEY."
            )

        base_dir = os.getenv("MCP_BASE_DIR", "").strip() or None
        if base_dir:
            if not os.path.isdir(base_dir):
                raise RuntimeError(f"MCP_BASE_DIR does not exist or is not a directory: {base_dir}")
            logger.debug("Using MCP_BASE_DIR: %s", base_dir)

        # default_encoding from env (will be overridden by detection if None)
        default_encoding = RELACE_DEFAULT_ENCODING

        return cls(api_key=api_key, base_dir=base_dir, default_encoding=default_encoding)
