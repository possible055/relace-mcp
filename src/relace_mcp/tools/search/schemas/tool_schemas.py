import os
import shutil
from typing import Any

_TRUTHY = {"1", "true", "yes", "y", "on"}
_FALSY = {"0", "false", "no", "n", "off"}


def _env_toggle(name: str) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return False
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    return False


_ALL_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "view_file",
            "strict": True,
            "description": (
                "Read file contents with line numbers.\n\n"
                "Output: '1 first line\\n2 second line\\n...'\n"
                "If file not found, returns error message.\n"
                "Out-of-range lines are clamped to file bounds."
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
                "Output: relative paths (alphabetical), dirs end with '/'. Max 250 items.\n"
                "Respects .gitignore rules and returns error if path is not a valid directory."
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
                        "description": (
                            "Include dot-prefixed files/directories (default: false). "
                            ".gitignore rules still apply."
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
                "Examples: '**/*.py' (all Python), 'src/**/*.ts' (TS under src).\n"
                "Returns empty list if no matches."
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
                        "description": (
                            "Base directory for search. '/repo' is substituted with actual repo root at runtime. "
                            "Use absolute paths like '/repo/src' to scope search."
                        ),
                    },
                    "include_hidden": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Include dot-prefixed files/directories (default: false). "
                            "Performance prune directories (for example node_modules/dist/target) "
                            "may still be skipped."
                        ),
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
            "description": (
                "TERMINAL TOOL — ends the search run.\n\n"
                "Report findings with file locations. MUST be the ONLY tool call in its turn.\n"
                "If you still need to explore, do NOT call report_back yet.\n"
                "When called, no further turns will execute."
            ),
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
                            "Map of absolute file path to line ranges (1-indexed, inclusive).\n"
                            "Example:\n"
                            "{\n"
                            '  "/repo/main.py": [[10, 25], [100, 115]],\n'
                            '  "/repo/utils.py": [[1, 50]]\n'
                            "}"
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
            "description": (
                "Navigate to symbol definition or find all references using LSP.\n\n"
                "Use 'definition' to jump to where a symbol is declared.\n"
                "Use 'references' to find all usages of a symbol.\n"
                "Returns empty if LSP server unavailable or symbol not found."
            ),
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
            "description": (
                "Search for symbol definitions by name across workspace.\n\n"
                "Supports prefix matching. Returns functions, classes, variables.\n"
                "Example: query='Config' matches 'ConfigManager', 'Configuration', etc."
            ),
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
            "description": (
                "Get type info and docstring for a symbol at position.\n\n"
                "Output: type signature and docstring (if available).\n"
                "Returns empty if no type info found."
            ),
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
            "description": (
                "Get outline of all symbols in a file.\n\n"
                "Returns: list of {name, kind, line_start, line_end} for classes, functions, variables."
            ),
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
            "description": (
                "Trace function call relationships using LSP.\n\n"
                "Use 'incoming' to find callers of a function (who calls this?).\n"
                "Use 'outgoing' to find callees (what does this function call?).\n"
                "Useful for understanding dependencies and impact analysis."
            ),
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


def _include_tool_strict() -> bool:
    raw = os.getenv("SEARCH_TOOL_STRICT", "1").strip().lower()
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
            If None, relies only on environment toggles.
            If empty frozenset, LSP tools are hidden.

    Environment variables:
        - SEARCH_BASH_TOOLS: Set to 1/true to enable bash tool (disabled by default).
        - SEARCH_LSP_TOOLS: Set to 1/true to enable LSP tools (disabled by default).
        - SEARCH_TOOL_STRICT: Set to 0/false to omit the non-standard `strict` field from tool schemas.
    """
    # LSP tool names for easy reference
    lsp_tool_names = {"find_symbol", "search_symbol", "get_type", "list_symbols", "call_graph"}

    # Default: basic exploration tools only.
    enabled = {
        "view_file",
        "view_directory",
        "grep_search",
        "glob",
        "report_back",
    }

    if _env_toggle("SEARCH_BASH_TOOLS"):
        enabled.add("bash")

    if _env_toggle("SEARCH_LSP_TOOLS"):
        enabled.update(lsp_tool_names)

    # Always keep report_back so the harness can terminate deterministically.
    enabled.add("report_back")

    # Platform/tool availability: only expose bash when it's actually runnable.
    if "bash" in enabled and shutil.which("bash") is None:
        enabled.discard("bash")

    # Hide LSP tools if no LSP languages are available for this project
    if lsp_languages is not None and not lsp_languages:
        enabled -= lsp_tool_names

    selected = [
        schema for schema in _ALL_TOOL_SCHEMAS if schema.get("function", {}).get("name") in enabled
    ]
    return normalize_tool_schemas(selected, include_strict=_include_tool_strict())


_DEFAULT_TOOL_NAMES = {
    "view_file",
    "view_directory",
    "grep_search",
    "glob",
    "report_back",
}

TOOL_SCHEMAS: list[dict[str, Any]] = normalize_tool_schemas(
    [
        schema
        for schema in _ALL_TOOL_SCHEMAS
        if schema.get("function", {}).get("name") in _DEFAULT_TOOL_NAMES
    ],
    include_strict=_include_tool_strict(),
)
