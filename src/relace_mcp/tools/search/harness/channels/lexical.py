from .base import BaseChannelHarness

LEXICAL_SYSTEM_PROMPT = """You are a lexical code search agent focused on text pattern matching.

Your tools:
- grep_search: Find exact text/regex patterns across the codebase
- glob: Find files by name pattern
- view_directory: List directory structure
- view_file: Read file contents

Strategy:
1. Turn 1: Use grep_search to find direct pattern matches
2. Turn 2: Use glob/view_directory to explore related files
3. Turn 3: Use view_file to verify and get precise line ranges

You have 3 turns. Be efficient. Focus on finding ALL relevant files."""


class LexicalChannel(BaseChannelHarness):
    """Lexical search channel using text pattern matching."""

    CHANNEL_NAME = "lexical"
    ALLOWED_TOOLS = frozenset(
        {
            "view_file",
            "view_directory",
            "grep_search",
            "glob",
        }
    )
    CHANNEL_SYSTEM_PROMPT = LEXICAL_SYSTEM_PROMPT
