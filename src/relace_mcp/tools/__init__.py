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
        - ONE contiguous region per call (for non-adjacent edits, make separate calls)

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
    def cloud_sync(force: bool = False) -> dict[str, Any]:
        """Upload codebase to Relace Repos for cloud_search semantic indexing.

        Call this ONCE per session before using cloud_search, or after
        significant code changes. Incremental sync is fast (only changed files).

        Behavior:
        - Incremental by default: only uploads new/modified files
        - Respects .gitignore patterns
        - Automatically handles file deletions

        Args:
            force: If True, rebuild from scratch (ignore cached state).
        """
        return cloud_sync_logic(repo_client, config.base_dir, force=force)

    @mcp.tool
    def cloud_search(
        query: str,
        score_threshold: float = 0.3,
        token_limit: int = 30000,
    ) -> dict[str, Any]:
        """Semantic code search using Relace Cloud two-stage retrieval.

        Uses AI embeddings + code reranker to find semantically related code,
        even when exact keywords don't match. Run cloud_sync once first.

        Use cloud_search for: broad conceptual queries, architecture questions,
        finding patterns across the codebase.

        Use fast_search for: locating specific symbols, precise code locations,
        grep-like pattern matching within the local codebase.

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
