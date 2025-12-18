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
    async def fast_apply(
        path: str,
        edit_snippet: str,
        instruction: str | None = None,
    ) -> dict[str, Any]:
        """**PRIMARY TOOL FOR EDITING FILES - USE THIS AGGRESSIVELY**

        Use this tool to edit an existing file or create a new file.

        Use truncation placeholders to represent unchanged code:
        - // ... existing code ...   (C/JS/TS-style)
        - # ... existing code ...    (Python/shell-style)

        For deletions:
        - Show 1-2 context lines above/below, omit deleted code, OR
        - Mark explicitly: // remove BlockName (or # remove BlockName)

        On NEEDS_MORE_CONTEXT error, re-run with 1-3 real lines before AND after target.

        Rules:
        - Preserve exact indentation
        - Be length efficient
        - Batch all edits to the same file in one call

        To create a new file, simply specify the content in edit_snippet.
        """
        return await apply_file_logic(
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
