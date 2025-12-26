from dataclasses import replace
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.context import Context

from ..clients import RelaceRepoClient, SearchLLMClient
from ..clients.apply import ApplyLLMClient
from ..config import RelaceConfig, resolve_base_dir
from .apply import apply_file_logic
from .repo import cloud_info_logic, cloud_list_logic, cloud_search_logic, cloud_sync_logic
from .search import FastAgenticSearchHarness

__all__ = ["register_tools"]


def register_tools(mcp: FastMCP, config: RelaceConfig) -> None:
    """Register Relace tools to the FastMCP instance."""
    apply_backend = ApplyLLMClient(config)

    @mcp.tool
    async def fast_apply(
        path: str,
        edit_snippet: str,
        instruction: str = "",
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """**PRIMARY TOOL FOR EDITING FILES - USE THIS AGGRESSIVELY**

        Use this tool to edit an existing file or create a new file.

        Use truncation placeholders to represent unchanged code:
        - // ... existing code ...   (C/JS/TS-style)
        - # ... existing code ...    (Python/shell-style)

        For deletions:
        - ALWAYS include 1-2 context lines above/below, omit deleted code, OR
        - Mark explicitly: // remove BlockName (or # remove BlockName)

        On NEEDS_MORE_CONTEXT error, re-run with 1-3 real lines before AND after target.

        Rules:
        - Preserve exact indentation
        - Be length efficient
        - ONE contiguous region per call (for non-adjacent edits, make separate calls)

        To create a new file, simply specify the content in edit_snippet.
        """
        # Resolve base_dir dynamically (aligns with other tools).
        # This allows relative paths when RELACE_BASE_DIR is not set but MCP Roots are available,
        # and provides a consistent security boundary for absolute paths.
        base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
        return await apply_file_logic(
            backend=apply_backend,
            file_path=path,
            edit_snippet=edit_snippet,
            instruction=instruction or None,  # Convert empty string to None internally
            base_dir=base_dir,
        )

    # Fast Agentic Search
    search_client = SearchLLMClient(config)

    @mcp.tool
    async def fast_search(query: str, ctx: Context) -> dict[str, Any]:
        """Run Fast Agentic Search over the configured base_dir.

        Use this tool to quickly explore and understand the codebase.
        The search agent will examine files, search for patterns, and report
        back with relevant files and line ranges for the given query.

        Queries can be natural language (e.g., "find where auth is handled")
        or precise patterns. The agent will autonomously use grep, ls, and
        file_view tools to investigate.

        This is useful before using fast_apply to understand which files
        need to be modified and how they relate to each other.
        """
        # Resolve base_dir dynamically from MCP Roots if not configured
        base_dir, source = await resolve_base_dir(config.base_dir, ctx)
        effective_config = replace(config, base_dir=base_dir)
        # Avoid shared mutable state across concurrent calls.
        return FastAgenticSearchHarness(effective_config, search_client).run(query=query)

    # Cloud Repos (Semantic Search & Sync)
    repo_client = RelaceRepoClient(config)

    @mcp.tool
    async def cloud_sync(
        force: bool = False, mirror: bool = False, ctx: Context | None = None
    ) -> dict[str, Any]:
        """Upload codebase to Relace Repos for cloud_search semantic indexing.

        Call this ONCE per session before using cloud_search, or after
        significant code changes. Incremental sync is fast (only changed files).

        Sync Modes:
        - Incremental (default): only uploads new/modified files, deletes removed files
        - Safe Full: triggered by force=True OR first sync (no cached state) OR
          git HEAD changed (e.g., branch switch, rebase, commit amend).
          Uploads all files; suppresses delete operations UNLESS HEAD changed,
          in which case zombie files from the old ref are deleted to prevent stale results.
        - Mirror Full (force=True, mirror=True): completely overwrites cloud to match local

        Args:
            force: If True, force full sync (ignore cached state).
            mirror: If True (with force=True), use Mirror Full mode to completely
                    overwrite cloud repo (removes files not in local).
        """
        base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
        return cloud_sync_logic(repo_client, base_dir, force=force, mirror=mirror)

    @mcp.tool
    async def cloud_search(
        query: str,
        branch: str = "",
        score_threshold: float = 0.3,
        token_limit: int = 30000,
        ctx: Context | None = None,
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
            branch: Branch to search (empty string uses API default branch).
            score_threshold: Minimum relevance score (0.0-1.0, default 0.3).
            token_limit: Maximum tokens to return (default 30000).
        """
        # Resolve base_dir dynamically from MCP Roots if not configured
        base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
        return cloud_search_logic(
            repo_client,
            base_dir,
            query,
            branch=branch,
            score_threshold=score_threshold,
            token_limit=token_limit,
        )

    @mcp.tool
    async def cloud_clear(confirm: bool = False, ctx: Context | None = None) -> dict[str, Any]:
        """Delete the cloud repository and local sync state.

        Use when: switching to a different project, resetting after major
        codebase restructuring, or cleaning up unused cloud repositories.

        WARNING: This action is IRREVERSIBLE. It permanently deletes the
        remote repository and removes the local sync state file.

        Args:
            confirm: Must be True to proceed. Acts as a safety guard.
        """
        from .repo.clear import cloud_clear_logic

        base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
        return cloud_clear_logic(repo_client, base_dir, confirm=confirm)

    @mcp.tool
    def cloud_list() -> dict[str, Any]:
        """List all repositories in your Relace Cloud account.

        Use to: discover synced repositories, verify cloud_sync results,
        or identify repository IDs for debugging.

        Returns a list of repos with: repo_id, name, auto_index status.
        Auto-paginates up to 10,000 repos (safety limit); `has_more=True` indicates the limit was reached.
        """
        return cloud_list_logic(repo_client)

    @mcp.tool
    async def cloud_info(ctx: Context | None = None) -> dict[str, Any]:
        """Get detailed sync status for the current repository.

        Use before cloud_sync to understand what action is needed.

        Returns:
        - local: Current git branch and HEAD commit
        - synced: Last sync state (git ref, tracked files count)
        - cloud: Cloud repo info (if exists)
        - status: Whether sync is needed and recommended action
        """
        base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
        return cloud_info_logic(repo_client, base_dir)

    # === MCP Resources ===

    @mcp.resource("relace://tool_list", mime_type="application/json")
    def tool_list() -> list[dict[str, Any]]:
        """List all available tools with their status."""
        return [
            {
                "id": "fast_apply",
                "name": "Fast Apply",
                "description": "Edit or create files using fuzzy matching",
                "enabled": True,
            },
            {
                "id": "fast_search",
                "name": "Fast Search",
                "description": "Agentic search over local codebase",
                "enabled": True,
            },
            {
                "id": "cloud_sync",
                "name": "Cloud Sync",
                "description": "Upload codebase for semantic indexing",
                "enabled": True,
            },
            {
                "id": "cloud_search",
                "name": "Cloud Search",
                "description": "Semantic code search using AI embeddings",
                "enabled": True,
            },
            {
                "id": "cloud_clear",
                "name": "Cloud Clear",
                "description": "Delete cloud repository and sync state",
                "enabled": True,
            },
            {
                "id": "cloud_list",
                "name": "Cloud List",
                "description": "List all repositories in Relace Cloud",
                "enabled": True,
            },
            {
                "id": "cloud_info",
                "name": "Cloud Info",
                "description": "Get sync status for current repository",
                "enabled": True,
            },
        ]
