from typing import Any

from fastmcp import FastMCP

from ..clients import RelaceClient, RelaceRepoClient, RelaceSearchClient
from ..config import RelaceConfig
from .apply import apply_file_logic
from .repo import cloud_search_logic, cloud_sync_logic
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

    # Cloud Repos (Semantic Search & Sync)
    repo_client = RelaceRepoClient(config)

    @mcp.tool
    def cloud_sync() -> dict[str, Any]:
        """Synchronize local codebase to Relace Cloud for semantic search.

        This uploads files from base_dir to Relace Repos, enabling cloud-based
        semantic search via cloud_search. Respects .gitignore patterns.

        Use this when:
        - First time setup for cloud semantic search
        - After significant code changes to refresh the index

        Note: This is a cloud operation, not local file manipulation.
        """
        return cloud_sync_logic(repo_client, config.base_dir)

    @mcp.tool
    def cloud_search(
        query: str,
        score_threshold: float = 0.3,
        token_limit: int = 30000,
    ) -> dict[str, Any]:
        """Perform semantic search over the codebase using Relace Cloud.

        Unlike fast_search (local grep-based), this uses AI embeddings to find
        semantically related code, even when exact keywords don't match.

        Best for:
        - Conceptual queries: "Where is user authentication handled?"
        - Finding related code: "Show me error handling patterns"
        - Understanding architecture: "How does the payment flow work?"

        For exact pattern matching, use fast_search instead.

        Args:
            query: Natural language search query.
            score_threshold: Minimum relevance score (0.0-1.0, default 0.3).
            token_limit: Maximum tokens to return (default 30000).
        """
        return cloud_search_logic(
            repo_client,
            query,
            score_threshold=score_threshold,
            token_limit=token_limit,
        )

    _ = fast_apply
    _ = fast_search
    _ = cloud_sync
    _ = cloud_search
