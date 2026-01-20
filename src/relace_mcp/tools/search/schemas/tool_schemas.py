import shutil
from typing import Any

from ....config.compat import getenv_with_fallback
from ....config.settings import SEARCH_LSP_TOOLS_MODE
from ....lsp.languages import detect_available_lsp_servers

_TRUTHY = {"1", "true", "yes", "y", "on"}
_FALSY = {"0", "false", "no", "n", "off"}

_ALL_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "view_file",
            "strict": True,
            "description": (
                "Tool for viewing/exploring the contents of existing files\n\n"
                "Line numbers are included in the output, indexing at 1. "
                "If the output does not include the end of the file, it will be noted after the final output line.\n\n"
                "Example (viewing the first 2 lines of a file):\n"
                "1 def my_function():\n"
                '2     print("Hello, World!")\n'
                "... rest of file truncated ..."
            ),
            "parameters": {
                "type": "object",
                "required": ["path", "view_range"],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to a file, e.g. `/repo/file.py`.",
                    },
                    "view_range": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "default": [1, 100],
                        "description": (
                            "Range of file lines to view. If not specified, the first 100 lines of the file are shown. "
                            "If provided, the file will be shown in the indicated line number range, e.g. [11, 12] will show lines 11 and 12. "
                            "Indexing at 1 to start. Setting `[start_line, -1]` shows all lines from `start_line` to the end of the file."
                        ),
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_directory",
            "strict": True,
            "description": (
                "Tool for viewing the contents of a directory.\n\n"
                "* Lists contents recursively, relative to the input directory\n"
                "* Directories are suffixed with a trailing slash '/'\n"
                "* Depth might be limited by the tool implementation\n"
                "* Output is limited to the first 250 items\n\n"
                "Example output:\n"
                "file1.txt\n"
                "file2.txt\n"
                "subdir1/\n"
                "subdir1/file3.txt"
            ),
            "parameters": {
                "type": "object",
                "required": ["path", "include_hidden"],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to a directory, e.g. `/repo/`.",
                    },
                    "include_hidden": {
                        "type": "boolean",
                        "default": False,
                        "description": "If true, include hidden files in the output (false by default).",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_search",
            "strict": True,
            "description": (
                "Fast text-based regex search that finds exact pattern matches within files or directories, "
                "utilizing the ripgrep command for efficient searching. Results will be formatted in the style of ripgrep "
                "and can be configured to include line numbers and content. To avoid overwhelming output, the results are "
                "capped at 50 matches. Use the include or exclude patterns to filter the search scope by file type or specific paths. "
                "This is best for finding exact text matches or regex patterns."
            ),
            "parameters": {
                "type": "object",
                "required": ["query", "case_sensitive", "exclude_pattern", "include_pattern"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The regex pattern to search for",
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "default": True,
                        "description": "Whether the search should be case sensitive (default: true)",
                    },
                    "exclude_pattern": {
                        "type": ["string", "null"],
                        "description": "Glob pattern for files to exclude",
                    },
                    "include_pattern": {
                        "type": ["string", "null"],
                        "description": "Glob pattern for files to include (e.g. '*.ts' for TypeScript files)",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "strict": True,
            "description": (
                "Find files in a directory tree using a glob pattern.\n\n"
                "Notes:\n"
                "- Matches are returned as paths relative to the input directory\n"
                "- Set `include_hidden=true` to match hidden files/directories (e.g. .git)\n"
                "- For directories only, end the pattern with a trailing slash (e.g. `src/`)\n"
                "- Output is capped to avoid overwhelming context\n\n"
                "Examples:\n"
                "- `**/*.py` (all Python files)\n"
                "- `src/**/*.ts` (all TS files under src)\n"
                "- `pyproject.toml` (any file named pyproject.toml)\n"
            ),
            "parameters": {
                "type": "object",
                "required": ["pattern"],
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": (
                            "Glob pattern to match (relative; no leading '/'; no '..'). "
                            "Use `**` to match across directories."
                        ),
                    },
                    "path": {
                        "type": "string",
                        "default": "/repo",
                        "description": "Directory to search under, e.g. `/repo` or `/repo/src`.",
                    },
                    "include_hidden": {
                        "type": "boolean",
                        "default": False,
                        "description": "If true, include hidden files/directories (false by default).",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 200,
                        "description": "Maximum number of matches to return (capped for safety).",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_back",
            "strict": True,
            "description": (
                "Report your findings back to the user after exploring the codebase. "
                "IMPORTANT: Include PRECISE line ranges for relevant code, not entire files."
            ),
            "parameters": {
                "type": "object",
                "required": ["explanation", "files"],
                "properties": {
                    "explanation": {
                        "type": "string",
                        "description": "Details your reasoning for deeming the files relevant for solving the issue.",
                    },
                    "files": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "minItems": 2,
                                "maxItems": 2,
                                "prefixItems": [{"type": "integer"}, {"type": "integer"}],
                            },
                        },
                        "description": (
                            "A dictionary mapping file paths to lists of [start_line, end_line] tuples. "
                            "Use PRECISE ranges for relevant code sections only (e.g., [[54, 67], [100, 115]]), "
                            "NOT entire file ranges like [[1, 500]]. Multiple ranges per file are encouraged."
                        ),
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "strict": True,
            "description": (
                "Execute a read-only bash command for code exploration.\n\n"
                "Platform: Unix/Linux/macOS only (requires bash shell).\n\n"
                "Use cases:\n"
                "- Find files with specific patterns (find, locate)\n"
                "- List directory trees (tree, ls -la)\n"
                "- Check file types and encodings (file, head, tail, wc)\n"
                "- Run static analysis tools (read-only)\n"
                "- Inspect git history (git log)\n\n"
                "Restrictions:\n"
                "- Commands run in the repository root (/repo)\n"
                "- Timeout: 30 seconds\n"
                "- No file modifications allowed (rm, mv, cp, etc.)\n"
                "- No network access (curl, wget, ssh, etc.)\n"
                "- No privilege escalation (sudo, su)\n"
                "- No pipes or redirections (|, >, >>)\n"
                "- Output capped at 50000 characters"
            ),
            "parameters": {
                "type": "object",
                "required": ["command"],
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute (read-only operations only).",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_symbol",
            "strict": True,
            "description": (
                "Navigate to a symbol's definition or find all references to it.\n\n"
                "Actions:\n"
                "- 'definition': Jump to where the symbol is defined (imports, classes, functions)\n"
                "- 'references': Find every location where the symbol is used\n\n"
                "When to use:\n"
                "- Tracing where a function/class comes from\n"
                "- Understanding how widely a symbol is used before refactoring\n"
                "- Following import chains across files\n\n"
                "Position format: line/column are 1-indexed, matching view_file output.\n"
                "First call has 2-5s startup delay."
            ),
            "parameters": {
                "type": "object",
                "required": ["action", "file", "line", "column"],
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["definition", "references"],
                        "description": "'definition' to jump to source, 'references' to find all usages.",
                    },
                    "file": {
                        "type": "string",
                        "description": "Absolute path to the source file containing the symbol.",
                    },
                    "line": {
                        "type": "integer",
                        "description": "Line number (1-indexed) where the symbol appears.",
                    },
                    "column": {
                        "type": "integer",
                        "description": "Column number (1-indexed) where the symbol name starts.",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_symbol",
            "strict": True,
            "description": (
                "Search for symbol definitions by name across the entire workspace.\n\n"
                "What it finds:\n"
                "- Function and method definitions\n"
                "- Class definitions\n"
                "- Variable and constant declarations\n\n"
                "What it ignores: string literals, comments, usages (only definitions).\n\n"
                "When to use:\n"
                "- Finding where a class/function is defined without knowing the file\n"
                "- Exploring codebase structure by searching partial names\n"
                "- Faster than grep when you only need definitions\n\n"
                "Returns: List of matching symbols with file paths and line numbers.\n"
                "First call has 2-5s startup delay."
            ),
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Symbol name or prefix to search (e.g., 'Config', 'handle_request').",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_type",
            "strict": True,
            "description": (
                "Get type information and documentation for a symbol at a position.\n\n"
                "Returns:\n"
                "- Inferred or declared type signature\n"
                "- Docstring if available\n"
                "- Function parameters and return type\n\n"
                "When to use:\n"
                "- Understanding what type a variable holds\n"
                "- Checking function signatures without navigating to definition\n"
                "- Reading docstrings inline\n\n"
                "Position format: line/column are 1-indexed, matching view_file output.\n"
                "First call has 2-5s startup delay."
            ),
            "parameters": {
                "type": "object",
                "required": ["file", "line", "column"],
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Absolute path to the source file.",
                    },
                    "line": {
                        "type": "integer",
                        "description": "Line number (1-indexed) where the symbol appears.",
                    },
                    "column": {
                        "type": "integer",
                        "description": "Column number (1-indexed) where the symbol name starts.",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_symbols",
            "strict": True,
            "description": (
                "Get a structured outline of all symbols defined in a file.\n\n"
                "Returns hierarchical list of:\n"
                "- Classes (with nested methods and attributes)\n"
                "- Functions\n"
                "- Top-level variables and constants\n"
                "Each symbol includes: name, kind, and line range.\n\n"
                "When to use:\n"
                "- Getting file structure overview before diving into code\n"
                "- Finding specific function/class locations quickly\n"
                "- Understanding module organization\n\n"
                "Faster than grep for structural exploration.\n"
                "First call has 2-5s startup delay."
            ),
            "parameters": {
                "type": "object",
                "required": ["file"],
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Absolute path to the source file to analyze.",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_graph",
            "strict": True,
            "description": (
                "Trace function call relationships in either direction.\n\n"
                "Directions:\n"
                "- 'incoming': Who calls this function? (callers)\n"
                "- 'outgoing': What does this function call? (callees)\n\n"
                "When to use:\n"
                "- Understanding impact before modifying a function\n"
                "- Tracing execution flow through the codebase\n"
                "- Finding entry points that lead to a function\n\n"
                "Position format: line/column are 1-indexed, pointing to the function name.\n"
                "First call has 2-5s startup delay."
            ),
            "parameters": {
                "type": "object",
                "required": ["file", "line", "column", "direction"],
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Absolute path to the source file containing the function.",
                    },
                    "line": {
                        "type": "integer",
                        "description": "Line number (1-indexed) of the function definition or call.",
                    },
                    "column": {
                        "type": "integer",
                        "description": "Column number (1-indexed) where the function name starts.",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["incoming", "outgoing"],
                        "description": "'incoming' for callers, 'outgoing' for callees.",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
]


def _split_tool_list(raw: str) -> list[str]:
    # Accept comma/space/semicolon separated lists.
    return [t for t in raw.replace(",", " ").replace(";", " ").split() if t]


def _include_tool_strict() -> bool:
    raw = getenv_with_fallback("SEARCH_TOOL_STRICT", "RELACE_SEARCH_TOOL_STRICT") or "1"
    raw = raw.strip().lower()
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    return True


def normalize_tool_schemas(
    schemas: list[dict[str, Any]], *, include_strict: bool
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for schema in schemas:
        schema_copy = dict(schema)
        func = schema_copy.get("function")
        if isinstance(func, dict):
            func_copy = dict(func)
            if not include_strict:
                func_copy.pop("strict", None)
            schema_copy["function"] = func_copy
        normalized.append(schema_copy)
    return normalized


def get_tool_schemas(lsp_languages: frozenset[str] | None = None) -> list[dict[str, Any]]:
    """Get enabled tool schemas for Fast Agentic Search.

    Args:
        lsp_languages: Set of available LSP language IDs for the current project.
            If None, uses default tool set (LSP tools require explicit opt-in via SEARCH_LSP_TOOLS).
            If empty frozenset, LSP tools are hidden.

    Environment variables:
        - SEARCH_LSP_TOOLS: Controls LSP tool availability.
          - 'false'/unset (default): LSP tools are disabled.
          - 'true': All LSP tools are enabled.
          - 'auto': Enable LSP tools only for languages with installed servers.
        - SEARCH_ENABLED_TOOLS: Comma/space-separated allowlist, e.g.
          "view_file,view_directory,grep_search,glob,find_symbol". `report_back` is always enabled.
          If not set, only basic tools (view_file, view_directory, grep_search, glob) are enabled.
          When SEARCH_LSP_TOOLS=true/auto and this is set, it also filters which LSP tools are enabled.
          bash requires explicit opt-in for security reasons.
        - SEARCH_TOOL_STRICT: Set to 0/false to omit the non-standard `strict` field from tool schemas.

    Deprecated (still supported with warning):
        RELACE_SEARCH_ENABLED_TOOLS, RELACE_SEARCH_TOOL_STRICT
    """
    raw_allowlist = getenv_with_fallback(
        "SEARCH_ENABLED_TOOLS", "RELACE_SEARCH_ENABLED_TOOLS"
    ).strip()

    # LSP tool names for easy reference
    lsp_tool_names = {"find_symbol", "search_symbol", "get_type", "list_symbols", "call_graph"}

    # Determine which LSP tools should be available based on mode
    lsp_enabled = False
    lsp_available_languages: frozenset[str] | None = None

    if SEARCH_LSP_TOOLS_MODE == "true":
        lsp_enabled = True
    elif SEARCH_LSP_TOOLS_MODE == "auto":
        # Auto-detect: check which LSP servers are installed
        available_servers = detect_available_lsp_servers()
        if available_servers:
            lsp_enabled = True
            lsp_available_languages = available_servers

    if raw_allowlist:
        enabled = {t.strip().lower() for t in _split_tool_list(raw_allowlist)}
        # Backward compatibility: lsp_query is now find_symbol
        if "lsp_query" in enabled:
            enabled.discard("lsp_query")
            enabled.add("find_symbol")
    else:
        # Default: basic exploration tools only
        # bash requires opt-in for security (Unix shell, higher risk)
        enabled = {
            "view_file",
            "view_directory",
            "grep_search",
            "glob",
            "report_back",
        }
        # When LSP is enabled and no allowlist, enable all LSP tools
        if lsp_enabled:
            enabled.update(lsp_tool_names)

    # LSP gatekeeper: when disabled, remove all LSP tools
    if not lsp_enabled:
        enabled -= lsp_tool_names

    # Always keep report_back so the harness can terminate deterministically.
    enabled.add("report_back")

    # Platform/tool availability: only expose bash when it's actually runnable.
    if "bash" in enabled and shutil.which("bash") is None:
        enabled.discard("bash")

    # Hide LSP tools if no LSP languages are available for this project
    if lsp_languages is not None and not lsp_languages:
        enabled -= lsp_tool_names

    # In auto mode, also consider the lsp_languages parameter for filtering
    # (intersection of installed servers and project languages)
    if lsp_available_languages is not None and lsp_languages is not None:
        # Only keep LSP tools if there's overlap between installed servers and project languages
        if not (lsp_available_languages & lsp_languages):
            enabled -= lsp_tool_names

    selected = [
        schema for schema in _ALL_TOOL_SCHEMAS if schema.get("function", {}).get("name") in enabled
    ]
    return normalize_tool_schemas(selected, include_strict=_include_tool_strict())


# Default export for backward compatibility (computed at import time)
TOOL_SCHEMAS: list[dict[str, Any]] = get_tool_schemas()
