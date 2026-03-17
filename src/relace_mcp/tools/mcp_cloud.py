# pyright: reportUnusedFunction=false
import asyncio
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.server.context import Context
from pydantic import Field

from ..config import resolve_base_dir
from ._registry import ToolRegistryDeps


def register_cloud_tools(mcp: FastMCP, deps: ToolRegistryDeps) -> None:
    @mcp.tool(
        tags={"cloud"},
        timeout=900.0,
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def cloud_sync(
        force: Annotated[
            bool, Field(description="Ignore cache, upload all files (default: false).")
        ] = False,
        mirror: Annotated[
            bool,
            Field(description="With force=True, delete cloud files not in local (default: false)."),
        ] = False,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Upload or refresh codebase to Relace Cloud for semantic search.

        Check index_status() first—skip this if cloud freshness is already 'fresh'.
        Syncs git-tracked files to enable cloud_search. Incremental by default.

        Advanced (Relace-specific):
          force=True              Re-upload all files; use after large refactors.
          force=True+mirror=True  Delete cloud files absent locally; use after branch switch.

        Returns: {sync_mode (str), files_created (int), files_updated (int),
                  files_deleted (int), files_unchanged (int), warnings (list[str]),
                  repo_id (str), repo_head (str)}.
        Check warnings[] for truncation or suppressed deletes.
        Fails if not in a git repo or RELACE_API_KEY is not set.
        """
        from ..repo.cloud.sync import cloud_sync_logic

        base_dir, _ = await resolve_base_dir(deps.config.base_dir, ctx)
        return await asyncio.to_thread(
            cloud_sync_logic,
            deps.clients.get_repo(),
            base_dir,
            force=force,
            mirror=mirror,
        )

    @mcp.tool(
        tags={"cloud"},
        timeout=300.0,
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def cloud_search(
        query: Annotated[
            str,
            Field(
                description="Natural language description of the code to find.\n"
                "  ✅ 'function that validates JWT and returns user ID'\n"
                "  ✅ 'rate limiting middleware for HTTP requests'\n"
                "  ❌ 'auth' (too vague — low-relevance results)\n"
                "Be specific about behavior, not just topic.",
            ),
        ],
        branch: Annotated[
            str | None, Field(description="Branch to search (null = API default branch).")
        ] = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Search for code by meaning using AI embeddings. Requires cloud_sync first.

        Use for conceptual queries where you don't know the exact file, class, or function name.
        Prefer agentic_search when you know the exact identifier or symbol name.

        Prerequisite: cloud_sync must have been run at least once.
        Fails if RELACE_API_KEY is not set or no sync state exists.

        Returns: {results (list), result_count (int), warnings (list[str]),
                  query (str), branch (str), repo_id (str)}.
        Check warnings[] for stale index alerts (e.g., uncommitted local changes).
        """
        from ..repo.cloud.search import cloud_search_logic

        score_threshold = 0.3
        token_limit = 30000

        base_dir, _ = await resolve_base_dir(deps.config.base_dir, ctx)
        return await asyncio.to_thread(
            cloud_search_logic,
            deps.clients.get_repo(),
            base_dir,
            query,
            branch=branch or "",
            score_threshold=score_threshold,
            token_limit=token_limit,
        )

    @mcp.tool(
        tags={"cloud"},
        timeout=300.0,
        annotations={
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def cloud_clear(
        confirm: Annotated[bool, Field(description="Must be True to proceed.")] = False,
        repo_id: Annotated[
            str | None,
            Field(
                description="Optional repo ID to delete directly (use cloud_list to find). "
                "If not provided, deletes the repo associated with current directory."
            ),
        ] = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Delete cloud repository and local sync state. IRREVERSIBLE.

        Removes all indexed data from Relace Cloud. Use cloud_list to find repo IDs.
        """
        from ..repo.cloud.clear import cloud_clear_logic

        base_dir, _ = await resolve_base_dir(deps.config.base_dir, ctx)
        return await asyncio.to_thread(
            cloud_clear_logic,
            deps.clients.get_repo(),
            base_dir,
            confirm=confirm,
            repo_id=repo_id,
        )

    @mcp.tool(
        tags={"cloud", "admin"},
        timeout=120.0,
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    def cloud_list() -> dict[str, Any]:
        """[ADMIN] List all repositories in your Relace Cloud account.

        Use to find repo_id for cloud_clear. Not needed for normal search/sync workflow.
        Returns repository IDs, names, and indexing status.
        """
        from ..repo.cloud.list import cloud_list_logic

        return cloud_list_logic(deps.clients.get_repo())
