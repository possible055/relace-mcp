from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GrepSearchParams:
    """封裝 grep_search 工具參數。"""

    query: str
    case_sensitive: bool
    include_pattern: str | None
    exclude_pattern: str | None
    base_dir: str


SYSTEM_PROMPT = """You are an AI agent whose job is to explore a code base with the provided tools and thoroughly understand the problem. You should use the tools provided to explore the codebase, read files, search for specific terms, and execute bash commands as needed. Once you have a good understanding of the problem, use the `report_back` tool share your findings. Make sure to only use the `report_back` tool when you are confident that you have gathered enough information to make an informed decision. Your objective is speed and efficiency so call multiple tools at once where applicable to reduce latency and reduce the number of turns. You are given a limited number of turns so aim to call 4-12 tools in parallel. You are suggested to explain your reasoning for the tools you choose to call before calling them."""

USER_PROMPT_TEMPLATE = """I have uploaded a code repository in the /repo directory. Now consider the following user query:

<user_query>
{query}
</user_query>

You need to resolve the <user_query>. To do this, follow the workflow below:

---

Your job is purely to understand the codebase.

### 1. Explore and Understand the Codebase

You **must first build a deep understanding of the relevant code**. Use the available tools to:

- Locate and examine all relevant parts of the codebase.
- Understand how the current code works, including expected behaviors, control flow, and edge cases.
- Identify the potential root cause(s) of the issue or the entry points for the requested feature.
- Review any related unit tests to understand expected behavior.

---

### 2. Report Back Your Understanding

Once you believe you have a solid understanding of the issue and the relevant code:

- Use the `report_back` tool to report you findings.
- File paths should be relative to the project root excluding the base `/repo/` failure to comply will result in deductions.
- Only report the relevant files within the repository. You may speculate that a file or folder may be added in your explaination, but it must not be put within you reported files.

---

### Success Criteria

A successful resolution means:

- The specific issue in the <user_query> is well understood.
- Your explain clearly the reasoning behind marking code as relavent.
- The files comprehensively covers all the key files needed to address the query.
- Relevant files can be any of three types:
  - Files needing edits
  - Files providing needed provide the required edits

<use_parallel_tool_calls>
If you intend to call multiple tools and there are no dependencies between the tool calls, make all of the independent tool calls in parallel. Prioritize calling tools simultaneously whenever the actions can be done in parallel rather than sequentially. For example, when reading 3 files, run 3 tool calls in parallel to read all 3 files into context at the same time. Maximize use of parallel tool calls where possible to increase speed and efficiency. However, if some tool calls depend on previous calls to inform dependent values like the parameters, do NOT call these tools in parallel and instead call them sequentially. Never use placeholders or guess missing parameters in tool calls.

Parallel tool calls can be made using the following schema:
<tool_call>
<function=example_function_name_1>
<parameter=example_parameter_1>
value_1
</parameter>
<parameter=example_parameter_2>
</parameter>
</function>
<function=example_function_name_2>
<parameter=example_parameter_1>
value_1
</parameter>
<parameter=example_parameter_2>
</parameter>
</function>
</tool_call>
Where you can place as many <function=...>...</function> tags as you want within the <tool_call>...</tool_call> tags for parallel tool calls.
</use_parallel_tool_calls>"""

TOOL_SCHEMAS: list[dict[str, Any]] = [
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
