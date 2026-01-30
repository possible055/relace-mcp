from typing import Any

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
                "Returns error if path is not a valid directory."
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
            "description": (
                "Report findings with file locations. MUST be called when exploration is complete.\n\n"
                "Use this to terminate search and return results to the caller."
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
