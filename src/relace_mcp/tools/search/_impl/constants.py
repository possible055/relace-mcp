from ....config.compat import getenv_with_fallback

# Directory listing limit
MAX_DIR_ITEMS = 250
# glob result limit
MAX_GLOB_MATCHES = 250
# glob max traversal depth
MAX_GLOB_DEPTH = 25
# grep result limit
MAX_GREP_MATCHES = 50
# grep timeout (seconds)
GREP_TIMEOUT_SECONDS = 30
# Python fallback grep max depth
MAX_GREP_DEPTH = 10
# Context truncation: max chars per tool result (by tool type)
MAX_TOOL_RESULT_CHARS = 50000  # default limit for truncate_for_context
MAX_VIEW_FILE_CHARS = 20000
MAX_GREP_SEARCH_CHARS = 12000
MAX_BASH_CHARS = 15000
MAX_VIEW_DIRECTORY_CHARS = 8000
MAX_GLOB_CHARS = 8000


# === Bash Tool ===
# NOTE: Unix-only (requires bash shell, not available on Windows)

BASH_TIMEOUT_SECONDS = 30
BASH_MAX_OUTPUT_CHARS = 50000


# === LSP Tool ===
# Maximum number of results returned from LSP queries (definition/references)
MAX_LSP_RESULTS = 50


def _parse_positive_float_env_with_fallback(new_name: str, old_name: str, default: float) -> float:
    """Parse positive float from env var with deprecation fallback."""
    raw = getenv_with_fallback(new_name, old_name)
    if not raw:
        return default
    raw = raw.strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    # Use `not (value > 0)` to correctly reject NaN (comparisons with NaN always return False)
    if not (value > 0):
        return default
    return value


# Hard upper bound for LSP startup/shutdown/requests (seconds).
# Use SEARCH_LSP_TIMEOUT_SECONDS to override (RELACE_LSP_TIMEOUT_SECONDS is deprecated).
LSP_TIMEOUT_SECONDS = _parse_positive_float_env_with_fallback(
    "SEARCH_LSP_TIMEOUT_SECONDS", "RELACE_LSP_TIMEOUT_SECONDS", 15.0
)
