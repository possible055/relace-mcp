import os
from typing import Any

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
                "This is a tool to use when you feel like you have finished exploring the codebase "
                "and understanding the problem, and now would like to report back to the user."
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
                            "A dictionary where the keys are file paths and the values are lists of tuples "
                            "representing the line ranges in each file that are relevant to solving the issue."
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
                "- Inspect git history (git log, git show, git diff)\n\n"
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
]


def _split_tool_list(raw: str) -> list[str]:
    # Accept comma/space/semicolon separated lists.
    return [t for t in raw.replace(",", " ").replace(";", " ").split() if t]


def get_tool_schemas() -> list[dict[str, Any]]:
    """Get enabled tool schemas for Fast Agentic Search.

    Environment variables:
        - RELACE_SEARCH_ENABLED_TOOLS: Comma/space-separated allowlist, e.g.
          "view_file,view_directory,grep_search,glob,bash". `report_back` is always enabled.
          If not set, all tools are enabled by default.
    """
    raw_allowlist = os.getenv("RELACE_SEARCH_ENABLED_TOOLS", "").strip()

    if raw_allowlist:
        enabled = {t.strip().lower() for t in _split_tool_list(raw_allowlist)}
    else:
        enabled = {"view_file", "view_directory", "grep_search", "glob", "report_back", "bash"}

    # Always keep report_back so the harness can terminate deterministically.
    enabled.add("report_back")

    return [
        schema for schema in _ALL_TOOL_SCHEMAS if schema.get("function", {}).get("name") in enabled
    ]


# Default export for backward compatibility (computed at import time)
TOOL_SCHEMAS: list[dict[str, Any]] = get_tool_schemas()
