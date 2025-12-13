from typing import Any

from fastmcp import FastMCP

from ..clients import RelaceClient, RelaceSearchClient
from ..config import RelaceConfig
from .apply import apply_file_logic
from .search import FastAgenticSearchHarness

__all__ = ["register_tools"]


def register_tools(mcp: FastMCP, config: RelaceConfig) -> None:
    """Register Relace tools to the FastMCP instance."""
    client = RelaceClient(config)

    @mcp.tool
    def fast_apply(
        path: str,
        edit_snippet: str,
        instruction: str | None = None,
    ) -> str:
        """**PRIMARY TOOL FOR EDITING FILES - USE THIS AGGRESSIVELY**

        Use this tool to propose an edit to an existing file or create a new file.

        Path formats supported:
        - /repo/src/file.py (virtual root from search)
        - src/file.py (relative to workspace)
        - /absolute/path (if within workspace)

        IMPORTANT: The edit_snippet parameter MUST use '// ... existing code ...'
        placeholder comments to represent unchanged code sections.

        Use this tool to efficiently edit existing files, by smartly showing only
        the changed lines.

        ALWAYS use "// ... existing code ..." to represent blocks of unchanged code.
        Add descriptive hints when helpful: // ... keep auth logic ...

        For deletions:
        - Option 1: Show 1-2 context lines above and below, omit deleted code
        - Option 2: Mark explicitly: // remove BlockName

        If the edit_snippet lacks enough concrete anchor lines to locate the change,
        this tool may return a message starting with 'NEEDS_MORE_CONTEXT'. In that case,
        re-run fast_apply with 1-3 real lines before AND after the target block.

        Rules:
        - Preserve exact indentation of the final code
        - Include just enough context to locate each edit precisely
        - Be as length efficient as possible
        - Batch all edits to the same file in one call

        To create a new file, simply specify the content in edit_snippet.
        """
        return apply_file_logic(
            client=client,
            file_path=path,
            edit_snippet=edit_snippet,
            instruction=instruction,
            base_dir=config.base_dir,
        )

    # Fast Agentic Search
    search_client = RelaceSearchClient(config)

    @mcp.tool
    def fast_search(query: str) -> dict[str, Any]:
        """Run Fast Agentic Search over the configured base_dir.

        Use this tool to quickly explore and understand the codebase.
        The search agent will examine files, search for patterns, and report
        back with relevant files and line ranges for the given query.

        This is useful before using fast_apply to understand which files
        need to be modified and how they relate to each other.
        """
        # Avoid shared mutable state across concurrent calls.
        return FastAgenticSearchHarness(config, search_client).run(query=query)

    _ = fast_apply
    _ = fast_search
