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
    "reload_settings_from_env",
    "reload_logging_settings",
    "reload_tool_settings",
]

RELACE_PROVIDER = "relace"

# Fast Apply defaults
APPLY_DEFAULT_ENDPOINT = "https://instantapply.endpoint.relace.run/v1/apply"
APPLY_DEFAULT_MODEL = "auto"

# Fast Agentic Search defaults
SEARCH_DEFAULT_ENDPOINT = "https://search.endpoint.relace.run/v1/search"
SEARCH_DEFAULT_MODEL = "relace-search"

MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0

# Encoding detection: explicitly set project default encoding (e.g., "gbk", "big5", "shift_jis")
# If not set, auto-detection will be attempted at startup
ENCODING_DETECTION_SAMPLE_LIMIT = 30

# File size limit (10MB) to prevent memory exhaustion on file read/write operations
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

# Logging - Cross-platform state directory:
# - Linux: ~/.local/state/relace
# - macOS: ~/Library/Application Support/relace
# - Windows: %LOCALAPPDATA%\relace
# Note: Directory is created lazily in logging.py when actually writing logs
LOG_DIR = Path(user_state_dir("relace", appauthor=False))
LOG_PATH = LOG_DIR / "relace.log"
MAX_LOG_SIZE_BYTES = 10 * 1024 * 1024

TRACE_DIR = LOG_DIR / "traces"
TRACE_PATH = TRACE_DIR / "relace.trace.jsonl"
MAX_TRACE_LOG_SIZE_BYTES = 50 * 1024 * 1024

_ALLOWED_RETRIEVAL_BACKENDS = {"relace", "codanna", "chunkhound", "none", "auto"}
_ALLOWED_RETRIEVAL_HINT_POLICIES = {"prefer-stale", "strict"}
_ALLOWED_SEARCH_TURN_STATUS_MODES = {"always", "final-only", "off"}

_LINUX_DEFAULT_EXTRA_PATHS: tuple[str, ...] = (
    "~/.cursor/plans",
    "~/.windsurf/plans",
    "~/.gemini/antigravity/brain",
    "~/.kiro/steering",
)


def _parse_positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _parse_nonnegative_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def _parse_positive_float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if not (value > 0):
        return default
    return value


def _parse_float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _parse_optional_float_env(name: str) -> float | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_optional_stripped_env(name: str) -> str | None:
    raw = os.getenv(name, "").strip()
    return raw or None


def _parse_logging_mode() -> str:
    raw = os.getenv("MCP_LOGGING", "off").strip().lower()
    if raw == "full":
        return "full"
    if raw in ("safe", "1", "true", "yes"):
        return "safe"
    return "off"


def _parse_log_level() -> str:
    return (os.getenv("MCP_LOG_LEVEL", "WARNING").strip() or "WARNING").upper()


def _parse_retrieval_backend() -> str:
    raw = os.getenv("MCP_RETRIEVAL_BACKEND", "relace").strip().lower()
    if raw not in _ALLOWED_RETRIEVAL_BACKENDS:
        raise RuntimeError(
            f"Invalid MCP_RETRIEVAL_BACKEND={raw!r}. "
            f"Expected one of: {sorted(_ALLOWED_RETRIEVAL_BACKENDS)}"
        )
    return raw


def _parse_retrieval_hint_policy() -> str:
    raw = os.getenv("MCP_RETRIEVAL_HINT_POLICY", "prefer-stale").strip().lower()
    if raw not in _ALLOWED_RETRIEVAL_HINT_POLICIES:
        raise RuntimeError(
            f"Invalid MCP_RETRIEVAL_HINT_POLICY={raw!r}. "
            f"Expected one of: {sorted(_ALLOWED_RETRIEVAL_HINT_POLICIES)}"
        )
    return raw


def _parse_search_turn_status_mode() -> str:
    raw = os.getenv("MCP_SEARCH_TURN_STATUS_MODE", "always").strip().lower()
    if raw not in _ALLOWED_SEARCH_TURN_STATUS_MODES:
        raise RuntimeError(
            f"Invalid MCP_SEARCH_TURN_STATUS_MODE={raw!r}. "
            f"Expected one of: {sorted(_ALLOWED_SEARCH_TURN_STATUS_MODES)}"
        )
    return raw


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

    if sys.platform == "linux":
        for p in _LINUX_DEFAULT_EXTRA_PATHS:
            expanded = str(Path(p).expanduser().resolve())
            if expanded not in user_paths and Path(expanded).is_dir():
                user_paths.append(expanded)

    if user_paths:
        logger.debug("Extra allowed paths: %s", user_paths)
    return tuple(user_paths)


APPLY_TIMEOUT_SECONDS: float
APPLY_TEMPERATURE: float
APPLY_PROVIDER: str
APPLY_API_KEY: str
APPLY_ENDPOINT: str
APPLY_MODEL: str
APPLY_PROMPT_FILE: str | None
SEARCH_TEMPERATURE: float
SEARCH_TIMEOUT_SECONDS: float
SEARCH_MAX_TURNS: int
SEARCH_PARALLEL_TOOL_CALLS: bool
SEARCH_TOP_P: float | None
SEARCH_PROVIDER: str
SEARCH_API_KEY: str
SEARCH_ENDPOINT: str
SEARCH_MODEL: str
SEARCH_PROMPT_FILE: str | None
RETRIEVAL_PROMPT_FILE: str | None
RELACE_API_ENDPOINT: str
RELACE_REPO_ID: str | None
REPO_SYNC_TIMEOUT_SECONDS: float
REPO_SYNC_MAX_FILES: int
REPO_LIST_MAX: int
RELACE_DEFAULT_ENCODING: str | None
APPLY_SEMANTIC_CHECK: bool
MCP_LOG_LEVEL: str
MCP_LOGGING_MODE: str
MCP_LOGGING: bool
MCP_LOG_REDACT: bool
MCP_TRACE_LOGGING: bool
RELACE_CLOUD_TOOLS: bool
RETRIEVAL_BACKEND: str
RETRIEVAL_HINT_POLICY: str
AGENTIC_RETRIEVAL_ENABLED: bool
SEARCH_TOOL_STRICT: bool
SEARCH_BASH_TOOLS: bool
SEARCH_LSP_TOOLS: bool
SEARCH_LSP_TIMEOUT_SECONDS: float
SEARCH_LSP_MAX_CLIENTS: int
SEARCH_TURN_STATUS_MODE: str
MCP_BACKGROUND_INDEX_MONITOR: bool
MCP_BACKGROUND_INDEX_INTERVAL_SECONDS: int
MCP_BACKGROUND_INDEX_INITIAL_DELAY_SECONDS: int
RELACE_UPLOAD_MAX_WORKERS: int
RELACE_API_KEY: str | None
MCP_BASE_DIR: str | None
MCP_EXTRA_PATHS: tuple[str, ...]

RELACE_CLOUD_TOOLS = False
RELACE_API_KEY = None
MCP_BASE_DIR = None
RELACE_DEFAULT_ENCODING = None
MCP_EXTRA_PATHS = ()


def reload_settings_from_env() -> None:
    """Re-read all env-backed runtime settings from ``os.environ``."""
    updated_settings = {
        "APPLY_TIMEOUT_SECONDS": _parse_positive_float_env("APPLY_TIMEOUT_SECONDS", 60.0),
        "APPLY_TEMPERATURE": _parse_float_env("APPLY_TEMPERATURE", 0.0),
        "APPLY_PROVIDER": os.getenv("APPLY_PROVIDER", "").strip(),
        "APPLY_API_KEY": os.getenv("APPLY_API_KEY", "").strip(),
        "APPLY_ENDPOINT": os.getenv("APPLY_ENDPOINT", "").strip(),
        "APPLY_MODEL": os.getenv("APPLY_MODEL", "").strip(),
        "APPLY_PROMPT_FILE": _parse_optional_stripped_env("APPLY_PROMPT_FILE"),
        "SEARCH_TEMPERATURE": _parse_float_env("SEARCH_TEMPERATURE", 1.0),
        "SEARCH_TIMEOUT_SECONDS": _parse_positive_float_env("SEARCH_TIMEOUT_SECONDS", 120.0),
        "SEARCH_MAX_TURNS": _parse_positive_int_env("SEARCH_MAX_TURNS", 6),
        "SEARCH_PARALLEL_TOOL_CALLS": env_bool("SEARCH_PARALLEL_TOOL_CALLS", default=True),
        "SEARCH_TOP_P": _parse_optional_float_env("SEARCH_TOP_P"),
        "SEARCH_PROVIDER": os.getenv("SEARCH_PROVIDER", "").strip(),
        "SEARCH_API_KEY": os.getenv("SEARCH_API_KEY", "").strip(),
        "SEARCH_ENDPOINT": os.getenv("SEARCH_ENDPOINT", "").strip(),
        "SEARCH_MODEL": os.getenv("SEARCH_MODEL", "").strip(),
        "SEARCH_PROMPT_FILE": _parse_optional_stripped_env("SEARCH_PROMPT_FILE"),
        "RETRIEVAL_PROMPT_FILE": _parse_optional_stripped_env("RETRIEVAL_PROMPT_FILE"),
        "RELACE_API_ENDPOINT": (
            os.getenv("RELACE_API_ENDPOINT", "https://api.relace.run/v1").strip()
            or "https://api.relace.run/v1"
        ),
        "RELACE_REPO_ID": _parse_optional_stripped_env("RELACE_REPO_ID"),
        "REPO_SYNC_TIMEOUT_SECONDS": _parse_positive_float_env("RELACE_REPO_SYNC_TIMEOUT", 300.0),
        "REPO_SYNC_MAX_FILES": _parse_positive_int_env("RELACE_REPO_SYNC_MAX_FILES", 5000),
        "REPO_LIST_MAX": _parse_positive_int_env("RELACE_REPO_LIST_MAX", 10000),
        "RELACE_DEFAULT_ENCODING": _parse_optional_stripped_env("RELACE_DEFAULT_ENCODING"),
        "APPLY_SEMANTIC_CHECK": env_bool("APPLY_SEMANTIC_CHECK", default=False),
        "MCP_LOG_LEVEL": _parse_log_level(),
        "MCP_LOGGING_MODE": _parse_logging_mode(),
        "RELACE_CLOUD_TOOLS": env_bool("RELACE_CLOUD_TOOLS", default=False),
        "RETRIEVAL_BACKEND": _parse_retrieval_backend(),
        "RETRIEVAL_HINT_POLICY": _parse_retrieval_hint_policy(),
        "AGENTIC_RETRIEVAL_ENABLED": env_bool("MCP_SEARCH_RETRIEVAL", default=False),
        "SEARCH_TOOL_STRICT": env_bool("SEARCH_TOOL_STRICT", default=True),
        "SEARCH_BASH_TOOLS": env_bool("SEARCH_BASH_TOOLS", default=False),
        "SEARCH_LSP_TOOLS": env_bool("SEARCH_LSP_TOOLS", default=False),
        "SEARCH_LSP_TIMEOUT_SECONDS": _parse_positive_float_env("SEARCH_LSP_TIMEOUT_SECONDS", 15.0),
        "SEARCH_LSP_MAX_CLIENTS": _parse_nonnegative_int_env("SEARCH_LSP_MAX_CLIENTS", 2),
        "SEARCH_TURN_STATUS_MODE": _parse_search_turn_status_mode(),
        "MCP_BACKGROUND_INDEX_MONITOR": env_bool(
            "MCP_BACKGROUND_INDEX_MONITOR",
            default=False,
        ),
        "MCP_BACKGROUND_INDEX_INTERVAL_SECONDS": _parse_positive_int_env(
            "MCP_BACKGROUND_INDEX_INTERVAL_SECONDS",
            300,
        ),
        "MCP_BACKGROUND_INDEX_INITIAL_DELAY_SECONDS": _parse_positive_int_env(
            "MCP_BACKGROUND_INDEX_INITIAL_DELAY_SECONDS",
            30,
        ),
        "RELACE_UPLOAD_MAX_WORKERS": _parse_positive_int_env("RELACE_UPLOAD_MAX_WORKERS", 8),
        "RELACE_API_KEY": _parse_optional_stripped_env("RELACE_API_KEY"),
        "MCP_BASE_DIR": _parse_optional_stripped_env("MCP_BASE_DIR"),
        "MCP_EXTRA_PATHS": _parse_extra_paths(),
    }
    logging_mode = updated_settings["MCP_LOGGING_MODE"]
    updated_settings["MCP_LOGGING"] = logging_mode in ("safe", "full")
    updated_settings["MCP_LOG_REDACT"] = logging_mode != "full"
    updated_settings["MCP_TRACE_LOGGING"] = logging_mode == "full"
    globals().update(updated_settings)


# Wrapper for existing call sites.
def reload_logging_settings() -> None:
    reload_settings_from_env()


# Wrapper for existing call sites.
def reload_tool_settings() -> None:
    reload_settings_from_env()


@dataclass(frozen=True)
class RelaceConfig:
    api_key: str | None = None  # Optional; required only when using Relace services
    base_dir: str | None = None  # Optional; resolved dynamically from MCP Roots if not set
    default_encoding: str | None = None  # Project-level encoding (detected or env-specified)
    extra_paths: tuple[str, ...] = ()  # Additional allowed paths for file operations

    @classmethod
    def from_env(cls) -> "RelaceConfig":
        reload_settings_from_env()
        api_key = RELACE_API_KEY

        if RELACE_CLOUD_TOOLS and not api_key:
            raise RuntimeError(
                "RELACE_API_KEY is required when RELACE_CLOUD_TOOLS=true. "
                "Set RELACE_CLOUD_TOOLS=false or provide RELACE_API_KEY."
            )

        base_dir = MCP_BASE_DIR
        if base_dir:
            if not os.path.isdir(base_dir):
                raise RuntimeError(f"MCP_BASE_DIR does not exist or is not a directory: {base_dir}")
            logger.debug("Using MCP_BASE_DIR: %s", base_dir)

        return cls(
            api_key=api_key,
            base_dir=base_dir,
            default_encoding=RELACE_DEFAULT_ENCODING,
            extra_paths=MCP_EXTRA_PATHS,
        )


reload_settings_from_env()
