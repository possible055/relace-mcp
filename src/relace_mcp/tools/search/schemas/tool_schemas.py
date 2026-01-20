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
                "Read file contents with line numbers.\n\n"
                "Output format: '1 first line\\n2 second line\\n...'"
            ),
            "parameters": {
                "type": "object",
                "required": ["path", "view_range"],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute file path, e.g., `/repo/src/main.py`.",
                    },
                    "view_range": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "default": [1, 100],
                        "description": (
                            "[start, end] lines (1-indexed). Use [start, -1] to read to end of file."
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
                "List directory contents recursively.\n\n"
                "Output: relative paths, directories end with '/'. Max 250 items."
            ),
            "parameters": {
                "type": "object",
                "required": ["path"],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute directory path, e.g., `/repo/src/`.",
                    },
                    "include_hidden": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include dotfiles and hidden directories (default: false).",
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
                "Search for text patterns in files using regex.\n\n"
                "Use for: finding exact text, symbol references, function calls, imports.\n"
                "Results capped at 50 matches."
            ),
            "parameters": {
                "type": "object",
                "required": ["query", "case_sensitive", "exclude_pattern", "include_pattern"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Rust regex pattern. For literal text, escape special chars: . * + ? | [ ] ( ) { } ^ $ \\"
                        ),
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "default": True,
                        "description": "Match case exactly (default: true).",
                    },
                    "exclude_pattern": {
                        "type": ["string", "null"],
                        "description": "Glob to skip files (e.g., '*.min.js'). Pass null to exclude nothing.",
                    },
                    "include_pattern": {
                        "type": ["string", "null"],
                        "description": "Glob to limit search (e.g., '*.py'). Pass null to search all files.",
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
                "Find files by glob pattern.\n\n"
                "Examples: '**/*.py' (all Python), 'src/**/*.ts' (TS under src), 'pyproject.toml' (exact name)."
            ),
            "parameters": {
                "type": "object",
                "required": ["pattern"],
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (no leading '/'). Use '**' to match across directories.",
                    },
                    "path": {
                        "type": "string",
                        "default": "/repo",
                        "description": "Directory to search, e.g., `/repo` or `/repo/src`.",
                    },
                    "include_hidden": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include dotfiles (default: false).",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 200,
                        "description": "Max matches to return (default: 200).",
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
            "description": "Report findings with file locations. Call this when exploration is complete.",
            "parameters": {
                "type": "object",
                "required": ["explanation", "files"],
                "properties": {
                    "explanation": {
                        "type": "string",
                        "description": "Why these files are relevant to the query.",
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
                            'Map of file path to line ranges. Example: {"/repo/main.py": [[10, 25], [100, 115]]}'
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
                "Execute read-only bash command.\n\n"
                "Allowed: find, ls, tree, head, tail, wc, file, git log.\n"
                "Forbidden: rm, mv, cp, curl, wget, sudo, pipes (|), redirects (>)."
            ),
            "parameters": {
                "type": "object",
                "required": ["command"],
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Bash command (read-only only). Timeout: 30s. Output capped at 50000 chars.",
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
            "description": "Go to symbol definition or find all references.",
            "parameters": {
                "type": "object",
                "required": ["action", "file", "line", "column"],
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["definition", "references"],
                        "description": "'definition' = jump to source, 'references' = find all usages.",
                    },
                    "file": {
                        "type": "string",
                        "description": "Absolute path to the file.",
                    },
                    "line": {
                        "type": "integer",
                        "description": "Line number (1-indexed).",
                    },
                    "column": {
                        "type": "integer",
                        "description": "Column where symbol appears (1-indexed). Cursor on any part of symbol works.",
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
            "description": "Search for symbol definitions by name across workspace. Finds functions, classes, variables.",
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Symbol name or prefix (e.g., 'Config', 'handle_request').",
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
            "description": "Get type info and docstring for a symbol at position.",
            "parameters": {
                "type": "object",
                "required": ["file", "line", "column"],
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Absolute path to the file.",
                    },
                    "line": {
                        "type": "integer",
                        "description": "Line number (1-indexed).",
                    },
                    "column": {
                        "type": "integer",
                        "description": "Column where symbol appears (1-indexed).",
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
            "description": "Get outline of all symbols in a file (classes, functions, variables with line ranges).",
            "parameters": {
                "type": "object",
                "required": ["file"],
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Absolute path to the file.",
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
            "description": "Trace function call relationships.",
            "parameters": {
                "type": "object",
                "required": ["file", "line", "column", "direction"],
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Absolute path to the file.",
                    },
                    "line": {
                        "type": "integer",
                        "description": "Line number of function (1-indexed).",
                    },
                    "column": {
                        "type": "integer",
                        "description": "Column where function name appears (1-indexed).",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["incoming", "outgoing"],
                        "description": "'incoming' = who calls this, 'outgoing' = what this calls.",
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
