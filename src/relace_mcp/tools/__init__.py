# pyright: reportUnusedFunction=false
# Decorator-registered functions (@mcp.tool, @mcp.resource) are accessed by the framework
import asyncio
import inspect
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.context import Context

from ..clients import RelaceRepoClient, SearchLLMClient
from ..clients.apply import ApplyLLMClient
from ..config import RelaceConfig, resolve_base_dir
from ..config.settings import MCP_SEARCH_MODE, RELACE_CLOUD_TOOLS, RETRIEVAL_BACKEND
from .apply import apply_file_logic
from .repo import (
    agentic_retrieval_logic,
    cloud_info_logic,
    cloud_list_logic,
    cloud_search_logic,
    cloud_sync_logic,
)
from .repo.state import load_sync_state
from .search import FastAgenticSearchHarness

__all__ = ["register_tools"]


def register_tools(mcp: FastMCP, config: RelaceConfig) -> None:
    """Register Relace tools to the FastMCP instance."""
    apply_backend = ApplyLLMClient(config)

    async def _progress_heartbeat(ctx: Context, *, message: str) -> None:
        while True:
            try:
                maybe = ctx.report_progress(progress=0, total=1.0, message=message)
                if inspect.isawaitable(maybe):
                    await maybe
            except Exception:
                return
            await asyncio.sleep(5)

    # Agentic Search client (used by both agentic_search and agentic_retrieval)
    search_client = SearchLLMClient(config)

    @mcp.tool(
        annotations={
            "readOnlyHint": False,  # Modifies files
            "destructiveHint": True,  # Can overwrite content
            "idempotentHint": False,  # Same edit twice = different results
            "openWorldHint": False,  # Only local filesystem
        }
    )
    async def fast_apply(
        path: str,
        edit_snippet: str,
        instruction: str = "",
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Edit or create a file.

        Args:
            path: File path (absolute or relative to MCP_BASE_DIR).
            edit_snippet: New content. Use placeholders for unchanged parts:
                - `// ... existing code ...` (C/JS/TS)
                - `# ... existing code ...` (Python/shell)
            instruction: Optional hint when edit is ambiguous (e.g., "add after imports").

        Returns: {status: "ok", path, diff} on success, {status: "error", message} on failure.
        On NEEDS_MORE_CONTEXT error: add 1-3 real lines before/after target.
        """
        # Resolve base_dir dynamically (aligns with other tools).
        # This allows relative paths when MCP_BASE_DIR is not set but MCP Roots are available,
        # and provides a consistent security boundary for absolute paths.
        progress_task = None
        if ctx is not None:
            progress_task = asyncio.create_task(
                _progress_heartbeat(ctx, message="fast_apply in progress")
            )
        try:
            base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
            return await apply_file_logic(
                backend=apply_backend,
                file_path=path,
                edit_snippet=edit_snippet,
                instruction=instruction or None,  # Convert empty string to None internally
                base_dir=base_dir,
            )
        finally:
            if progress_task is not None:
                progress_task.cancel()
                with suppress(asyncio.CancelledError):
                    await progress_task

    # Register agentic_search (primary) and fast_search (deprecated alias)
    # Only when MCP_SEARCH_MODE is 'agentic' or 'both'
    if MCP_SEARCH_MODE in ("agentic", "both"):

        async def _agentic_search_impl(query: str, ctx: Context) -> dict[str, Any]:
            """Internal implementation for agentic search."""
            progress_task = asyncio.create_task(
                _progress_heartbeat(ctx, message="agentic_search in progress")
            )
            try:
                # Resolve base_dir dynamically from MCP Roots if not configured
                base_dir, _ = await resolve_base_dir(config.base_dir, ctx)

                # Get cached LSP languages (auto-detects on first call per base_dir)
                from ..lsp.languages import get_lsp_languages

                lsp_languages = get_lsp_languages(Path(base_dir))

                effective_config = replace(config, base_dir=base_dir)
                return await FastAgenticSearchHarness(
                    effective_config, search_client, lsp_languages=lsp_languages
                ).run_async(query=query)
            finally:
                progress_task.cancel()
                with suppress(asyncio.CancelledError):
                    await progress_task

        @mcp.tool(
            annotations={
                "readOnlyHint": True,  # Does not modify environment
                "destructiveHint": False,  # Read-only = non-destructive
                "idempotentHint": True,  # Same query = same results
                "openWorldHint": False,  # Only local codebase
            }
        )
        async def agentic_search(query: str, ctx: Context) -> dict[str, Any]:
            """Search codebase and return relevant file locations.

            Args:
                query: What to find. Natural language (e.g., "where is auth handled")
                       or specific patterns (e.g., "UserService class").

            Returns: {files: {path: [[start, end], ...]}, explanation: str, partial: bool}
            """
            return await _agentic_search_impl(query, ctx)

        @mcp.tool(
            annotations={
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            }
        )
        async def fast_search(query: str, ctx: Context) -> dict[str, Any]:
            """[DEPRECATED] Use `agentic_search` instead.

            Search codebase and return relevant file locations.

            Args:
                query: What to find. Natural language or specific patterns.

            Returns: {files: {path: [[start, end], ...]}, explanation: str, partial: bool, _deprecated: str}
            """
            result = await _agentic_search_impl(query, ctx)
            result["_deprecated"] = (
                "Tool 'fast_search' is deprecated and will be removed in v0.2.5. "
                "Use 'agentic_search' instead."
            )
            return result

    repo_client: RelaceRepoClient | None = None

    # Cloud Repos (Semantic Search & Sync) - only register if enabled
    if RELACE_CLOUD_TOOLS:
        repo_client = RelaceRepoClient(config)

        @mcp.tool
        async def cloud_sync(
            force: bool = False, mirror: bool = False, ctx: Context | None = None
        ) -> dict[str, Any]:
            """Upload codebase to Relace Cloud for semantic search.

            Args:
                force: Ignore cache, upload all files (default: false).
                mirror: With force=True, delete cloud files not in local (default: false).

            Run once per session before cloud_search. Incremental by default.
            Returns: {status, files_uploaded, files_skipped} on success.
            Fails if: not a git repo, no API key, network error.
            """
            base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
            return cloud_sync_logic(repo_client, base_dir, force=force, mirror=mirror)

        @mcp.tool
        async def cloud_search(
            query: str,
            branch: str = "",
            ctx: Context | None = None,
        ) -> dict[str, Any]:
            """Semantic code search using AI embeddings. Requires cloud_sync first.

            Use when: local fast_search insufficient, need semantic understanding.

            Args:
                query: Natural language search query.
                branch: Branch to search (empty = default branch).

            Returns: {results: [{path, score, snippet}, ...], total_matches}.
            """
            # Fixed internal parameters (not exposed to LLM)
            score_threshold = 0.3
            token_limit = 30000

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
        async def cloud_clear(
            confirm: bool = False,
            repo_id: str | None = None,
            ctx: Context | None = None,
        ) -> dict[str, Any]:
            """Delete cloud repository and local sync state. IRREVERSIBLE.

            Args:
                confirm: Must be True to proceed.
                repo_id: Optional repo ID to delete directly (use cloud_list to find).
                         If not provided, deletes the repo associated with current directory.

            Returns: {status: "deleted"} on success, {status: "cancelled"} if confirm=false.
            """
            from .repo.clear import cloud_clear_logic

            base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
            return cloud_clear_logic(repo_client, base_dir, confirm=confirm, repo_id=repo_id)

        @mcp.tool
        def cloud_list(reason: str = "") -> dict[str, Any]:
            """List all repositories in your Relace Cloud account.

            Args:
                reason: Brief explanation of why you are calling this tool.

            Returns: [{repo_id, name, auto_index}, ...]. Max 10000 repos.
            Returns empty list if no repositories exist.
            """
            del reason  # LLM chain-of-thought only
            return cloud_list_logic(repo_client)

        @mcp.tool
        async def cloud_info(reason: str = "", ctx: Context | None = None) -> dict[str, Any]:
            """Get detailed sync status for the current repository.

            Use before cloud_sync to understand what action is needed.

            Args:
                reason: Brief explanation of why you are calling this tool.

            Returns:
            - local: Current git branch and HEAD commit
            - synced: Last sync state (git ref, tracked files count)
            - cloud: Cloud repo info (if exists)
            - status: Whether sync is needed and recommended action
            """
            del reason  # LLM chain-of-thought only
            base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
            return cloud_info_logic(repo_client, base_dir)

    if MCP_SEARCH_MODE in ("indexed", "both") and RETRIEVAL_BACKEND != "none":

        @mcp.tool(
            annotations={
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": RETRIEVAL_BACKEND == "relace",
            }
        )
        async def agentic_retrieval(
            query: str,
            ctx: Context | None = None,
        ) -> dict[str, Any]:
            """Find code by semantic query. Returns {files: {path: [[start, end], ...]}, explanation}.

            Args:
                query: Be SPECIFIC. Examples:
                    ❌ "auth logic"
                    ✅ "function that validates JWT tokens and extracts user ID"
                    ❌ "error handling"
                    ✅ "where HTTP 4xx errors are caught and transformed to user messages"
            """
            progress_task = None
            if ctx is not None:
                progress_task = asyncio.create_task(
                    _progress_heartbeat(ctx, message="agentic_retrieval in progress")
                )
            try:
                base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
                return await agentic_retrieval_logic(
                    repo_client,
                    search_client,
                    config,
                    base_dir,
                    query,
                )
            finally:
                if progress_task is not None:
                    progress_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await progress_task

    # === MCP Resources ===

    @mcp.resource("relace://tools_list", mime_type="application/json")
    def tools_list() -> list[dict[str, Any]]:
        """List all registered Relace MCP tools with their enabled status.

        Returns: [{id, name, description, enabled}, ...] for each tool.
        Use this to discover available capabilities before calling tools.
        """
        tools = [
            {
                "id": "fast_apply",
                "name": "Fast Apply",
                "description": "Edit or create files using fuzzy matching",
                "enabled": True,
            },
        ]
        if MCP_SEARCH_MODE in ("agentic", "both"):
            tools.append(
                {
                    "id": "agentic_search",
                    "name": "Agentic Search",
                    "description": "Agentic search over local codebase",
                    "enabled": True,
                }
            )
            tools.append(
                {
                    "id": "fast_search",
                    "name": "Fast Search",
                    "description": "[DEPRECATED] Alias for agentic_search. Will be removed in v0.2.5.",
                    "enabled": True,
                    "deprecated": True,
                }
            )
        if RELACE_CLOUD_TOOLS:
            tools.extend(
                [
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
            )
        if MCP_SEARCH_MODE in ("indexed", "both") and RETRIEVAL_BACKEND != "none":
            tools.append(
                {
                    "id": "agentic_retrieval",
                    "name": "Agentic Retrieval",
                    "description": "Two-stage semantic + agentic code retrieval",
                    "enabled": True,
                }
            )
        return tools

    if RELACE_CLOUD_TOOLS:

        @mcp.resource("relace://cloud/status", mime_type="application/json")
        async def cloud_status(ctx: Context | None = None) -> dict[str, Any]:
            """Current cloud sync status - lightweight read from local state file.

            Returns sync state without making API calls. Use this to quickly check
            if cloud_sync has been run and what the current sync status is.
            """
            try:
                base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
            except RuntimeError:
                return {
                    "synced": False,
                    "error": "base_dir not configured",
                    "message": "Set MCP_BASE_DIR or use MCP Roots to enable cloud status",
                }

            from .repo.state import get_repo_identity

            local_repo_name, cloud_repo_name, _project_fingerprint = get_repo_identity(base_dir)
            if not local_repo_name or not cloud_repo_name:
                return {
                    "synced": False,
                    "error": "invalid base_dir",
                    "message": "Cannot derive repository identity from base_dir; ensure MCP_BASE_DIR or MCP Roots points to a project directory.",
                }

            state = load_sync_state(base_dir)

            if state is None:
                return {
                    "synced": False,
                    "repo_name": local_repo_name,
                    "cloud_repo_name": cloud_repo_name,
                    "message": "No sync state found. Run cloud_sync to upload codebase.",
                }

            return {
                "synced": True,
                "repo_id": state.repo_id,
                "repo_name": state.repo_name or local_repo_name,
                "cloud_repo_name": state.cloud_repo_name or cloud_repo_name,
                "git_ref": (
                    f"{state.git_branch}@{state.git_head_sha[:8]}"
                    if state.git_branch and state.git_head_sha
                    else state.git_head_sha[:8]
                    if state.git_head_sha
                    else ""
                ),
                "files_count": len(state.files),
                "skipped_files_count": len(state.skipped_files),
                "files_found": state.files_found,
                "files_selected": state.files_selected,
                "file_limit": state.file_limit,
                "files_truncated": state.files_truncated,
                "last_sync": state.last_sync,
            }
