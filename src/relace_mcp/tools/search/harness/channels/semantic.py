from .base import BaseChannelHarness

SEMANTIC_SYSTEM_PROMPT = """You are a semantic code search agent focused on code structure analysis.

Your tools:
- search_symbol: Find symbol definitions by name (no file position needed)
- list_symbols: Get file outline showing classes, functions, variables
- find_symbol: Go to definition or find all references (requires file:line:col)
- call_graph: Trace call hierarchy (incoming callers or outgoing callees)
- get_type: Get type information for a symbol
- view_file: Read file contents to get line/column positions

Strategy:
1. Turn 1: Use search_symbol to find entry points matching the query
2. Turn 2: Use find_symbol/call_graph to trace dependencies
3. Turn 3: Use view_file to verify and get precise line ranges

You have 3 turns. Focus on semantic relationships like call chains and type hierarchies.
DO NOT use grep for text matching - that's handled by another agent."""


class SemanticChannel(BaseChannelHarness):
    """Semantic search channel using LSP-based code analysis."""

    CHANNEL_NAME = "semantic"
    ALLOWED_TOOLS = frozenset(
        {
            "view_file",
            "search_symbol",
            "find_symbol",
            "list_symbols",
            "call_graph",
            "get_type",
        }
    )
    CHANNEL_SYSTEM_PROMPT = SEMANTIC_SYSTEM_PROMPT
