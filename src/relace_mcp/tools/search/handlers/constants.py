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
