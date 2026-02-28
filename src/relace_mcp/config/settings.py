import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_state_dir

from .compat import env_bool

logger = logging.getLogger(__name__)

__all__ = [
    "RELACE_CLOUD_TOOLS",
    "RETRIEVAL_BACKEND",
    "SEARCH_BASH_TOOLS",
    "SEARCH_LSP_TOOLS",
    "RelaceConfig",
]

# Fast Apply defaults
APPLY_DEFAULT_ENDPOINT = "https://instantapply.endpoint.relace.run/v1/apply"
APPLY_DEFAULT_MODEL = "auto"
APPLY_TIMEOUT_SECONDS = float(os.getenv("APPLY_TIMEOUT_SECONDS", "") or "60.0")
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0

# Temperature settings for each tool
SEARCH_TEMPERATURE = float(os.getenv("SEARCH_TEMPERATURE", "1.0"))
APPLY_TEMPERATURE = float(os.getenv("APPLY_TEMPERATURE", "0.0"))

# Provider identifier
RELACE_PROVIDER = "relace"

# Fast Agentic Search defaults
SEARCH_DEFAULT_ENDPOINT = "https://search.endpoint.relace.run/v1/search"
SEARCH_DEFAULT_MODEL = "relace-search"
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
if _MCP_LOGGING_RAW == "full":
    MCP_LOGGING_MODE = "full"
elif _MCP_LOGGING_RAW in ("safe", "1", "true", "yes"):
    MCP_LOGGING_MODE = "safe"
else:
    MCP_LOGGING_MODE = "off"

MCP_LOGGING = MCP_LOGGING_MODE in ("safe", "full")
MCP_LOG_REDACT = MCP_LOGGING_MODE != "full"
# NOTE: Trace log contains full tool/LLM/CLI I/O and is only enabled in MCP_LOGGING=full.
# Use MCP_TRACE=0 to disable trace writing even in full mode.
MCP_TRACE_LOGGING = (MCP_LOGGING_MODE == "full") and env_bool("MCP_TRACE", default=True)

# JSONL file log filtering
MCP_LOG_FILE_LEVEL = os.getenv("MCP_LOG_FILE_LEVEL", "DEBUG").strip().upper()


def _parse_csv_env_set(name: str) -> frozenset[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return frozenset()
    items = [item.strip() for item in raw.split(",") if item.strip()]
    return frozenset(items)


MCP_LOG_INCLUDE_KINDS = _parse_csv_env_set("MCP_LOG_INCLUDE_KINDS")
MCP_LOG_EXCLUDE_KINDS = _parse_csv_env_set("MCP_LOG_EXCLUDE_KINDS")
MCP_TRACE_INCLUDE_KINDS = _parse_csv_env_set("MCP_TRACE_INCLUDE_KINDS")
MCP_TRACE_EXCLUDE_KINDS = _parse_csv_env_set("MCP_TRACE_EXCLUDE_KINDS")

# Cloud tools (disabled by default)
RELACE_CLOUD_TOOLS = env_bool("RELACE_CLOUD_TOOLS", default=False)

_ALLOWED_RETRIEVAL_BACKENDS = {"relace", "codanna", "chunkhound", "none", "auto"}


def _parse_retrieval_backend() -> str:
    raw = os.getenv("MCP_RETRIEVAL_BACKEND", "relace").strip().lower()
    if raw not in _ALLOWED_RETRIEVAL_BACKENDS:
        raise RuntimeError(
            f"Invalid MCP_RETRIEVAL_BACKEND={raw!r}. "
            f"Expected one of: {sorted(_ALLOWED_RETRIEVAL_BACKENDS)}"
        )
    if raw == "auto":
        return "auto"
    return raw


RETRIEVAL_BACKEND = _parse_retrieval_backend()


# Enable agentic_retrieval tool (requires cloud sync or local backend)
AGENTIC_RETRIEVAL_ENABLED = env_bool("MCP_SEARCH_RETRIEVAL", default=False)

# Search tool toggles (both disabled by default)
SEARCH_BASH_TOOLS = env_bool("SEARCH_BASH_TOOLS", default=False)
SEARCH_LSP_TOOLS = env_bool("SEARCH_LSP_TOOLS", default=False)

# Agentic retrieval auto-sync (enabled by default when cloud tools are enabled)
AGENTIC_AUTO_SYNC = env_bool("RELACE_AGENTIC_AUTO_SYNC", default=True)

# Logging - Cross-platform state directory:
# - Linux: ~/.local/state/relace
# - macOS: ~/Library/Application Support/relace
# - Windows: %LOCALAPPDATA%\relace
# Note: Directory is created lazily in logging.py when actually writing logs
_MCP_LOG_DIR_RAW = os.getenv("MCP_LOG_DIR", "").strip()
LOG_DIR = (
    Path(_MCP_LOG_DIR_RAW).expanduser()
    if _MCP_LOG_DIR_RAW
    else Path(user_state_dir("relace", appauthor=False))
)

_MCP_LOG_PATH_RAW = os.getenv("MCP_LOG_PATH", "").strip()
LOG_PATH = Path(_MCP_LOG_PATH_RAW).expanduser() if _MCP_LOG_PATH_RAW else (LOG_DIR / "relace.log")

MAX_LOG_SIZE_BYTES = 10 * 1024 * 1024

_MCP_TRACE_DIR_RAW = os.getenv("MCP_TRACE_DIR", "").strip()
TRACE_DIR = Path(_MCP_TRACE_DIR_RAW).expanduser() if _MCP_TRACE_DIR_RAW else (LOG_DIR / "traces")

_MCP_TRACE_PATH_RAW = os.getenv("MCP_TRACE_PATH", "").strip()
TRACE_PATH = (
    Path(_MCP_TRACE_PATH_RAW).expanduser()
    if _MCP_TRACE_PATH_RAW
    else (TRACE_DIR / "relace.trace.jsonl")
)

MAX_TRACE_LOG_SIZE_BYTES = 50 * 1024 * 1024


def reload_logging_settings() -> None:
    """Re-read logging/trace environment variables and update module globals.

    The module-level assignments run at import time — before ``load_dotenv()``
    has been called.  Invoke this function once after dotenv loading so that
    values defined in ``.env`` take effect.
    """
    global MCP_LOGGING_MODE, MCP_LOGGING, MCP_LOG_REDACT, MCP_TRACE_LOGGING
    global MCP_LOG_FILE_LEVEL
    global MCP_LOG_INCLUDE_KINDS, MCP_LOG_EXCLUDE_KINDS
    global MCP_TRACE_INCLUDE_KINDS, MCP_TRACE_EXCLUDE_KINDS
    global LOG_DIR, LOG_PATH, TRACE_DIR, TRACE_PATH

    raw = os.getenv("MCP_LOGGING", "off").strip().lower()
    if raw == "full":
        MCP_LOGGING_MODE = "full"
    elif raw in ("safe", "1", "true", "yes"):
        MCP_LOGGING_MODE = "safe"
    else:
        MCP_LOGGING_MODE = "off"

    MCP_LOGGING = MCP_LOGGING_MODE in ("safe", "full")
    MCP_LOG_REDACT = MCP_LOGGING_MODE != "full"
    MCP_TRACE_LOGGING = (MCP_LOGGING_MODE == "full") and env_bool("MCP_TRACE", default=True)

    MCP_LOG_FILE_LEVEL = os.getenv("MCP_LOG_FILE_LEVEL", "DEBUG").strip().upper()

    MCP_LOG_INCLUDE_KINDS = _parse_csv_env_set("MCP_LOG_INCLUDE_KINDS")
    MCP_LOG_EXCLUDE_KINDS = _parse_csv_env_set("MCP_LOG_EXCLUDE_KINDS")
    MCP_TRACE_INCLUDE_KINDS = _parse_csv_env_set("MCP_TRACE_INCLUDE_KINDS")
    MCP_TRACE_EXCLUDE_KINDS = _parse_csv_env_set("MCP_TRACE_EXCLUDE_KINDS")

    raw_dir = os.getenv("MCP_LOG_DIR", "").strip()
    LOG_DIR = (
        Path(raw_dir).expanduser() if raw_dir else Path(user_state_dir("relace", appauthor=False))
    )

    raw_path = os.getenv("MCP_LOG_PATH", "").strip()
    LOG_PATH = Path(raw_path).expanduser() if raw_path else (LOG_DIR / "relace.log")

    raw_trace_dir = os.getenv("MCP_TRACE_DIR", "").strip()
    TRACE_DIR = Path(raw_trace_dir).expanduser() if raw_trace_dir else (LOG_DIR / "traces")

    raw_trace_path = os.getenv("MCP_TRACE_PATH", "").strip()
    TRACE_PATH = (
        Path(raw_trace_path).expanduser() if raw_trace_path else (TRACE_DIR / "relace.trace.jsonl")
    )


# File size limit (10MB) to prevent memory exhaustion on file read/write operations
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

_LINUX_DEFAULT_EXTRA_PATHS: tuple[str, ...] = (
    "~/.cursor/plans",
    "~/.windsurf/plans",
    "~/.gemini/antigravity/brain",
    "~/.kiro/steering",
)


def _parse_extra_paths() -> tuple[str, ...]:
    raw = os.getenv("MCP_EXTRA_PATHS", "").strip()
    user_paths: list[str] = []
    if raw:
        for item in raw.split(","):
            item = item.strip()
            if not item:
                continue
            expanded = str(Path(item).expanduser().resolve())
            if expanded in ("/", "/home", "/tmp", "/etc", "/var", "/usr"):  # nosec B108
                logger.warning("MCP_EXTRA_PATHS: ignoring unsafe path: %s", item)
                continue
            user_paths.append(expanded)

    # Merge Linux defaults (only existing directories)
    if sys.platform == "linux":
        for p in _LINUX_DEFAULT_EXTRA_PATHS:
            expanded = str(Path(p).expanduser().resolve())
            if expanded not in user_paths and Path(expanded).is_dir():
                user_paths.append(expanded)

    if user_paths:
        logger.debug("Extra allowed paths: %s", user_paths)
    return tuple(user_paths)


@dataclass(frozen=True)
class RelaceConfig:
    api_key: str | None = None  # Optional; required only when using Relace services
    base_dir: str | None = None  # Optional; resolved dynamically from MCP Roots if not set
    default_encoding: str | None = None  # Project-level encoding (detected or env-specified)
    extra_paths: tuple[str, ...] = ()  # Additional allowed paths for file operations

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

        extra_paths = _parse_extra_paths()

        return cls(
            api_key=api_key,
            base_dir=base_dir,
            default_encoding=default_encoding,
            extra_paths=extra_paths,
        )
