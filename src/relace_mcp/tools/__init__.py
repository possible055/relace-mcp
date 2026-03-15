# pyright: reportUnusedFunction=false
# Decorator-registered functions (@mcp.tool, @mcp.resource) are accessed by the framework
import asyncio
import json
import logging
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.server.context import Context
from pydantic import Field

from ..config import RelaceConfig, resolve_base_dir
from ..config import settings as _settings
from ..observability import get_trace_id, log_event, redact_value
from ._clients import ToolClients
from ._setup import EncodingState, ensure_encoding_detected

__all__ = ["register_tools"]

logger = logging.getLogger(__name__)


def _read_text_safe(path: Path) -> str | None:
    """Read text from *path*, returning ``None`` for symlinks, missing, or empty files."""
    try:
        if path.is_symlink():
            return None
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        return text or None
    except OSError:
        return None


def register_tools(mcp: FastMCP, config: RelaceConfig) -> None:
    """Register Relace tools to the FastMCP instance."""

    _clients = ToolClients(config)
    _encoding_state = EncodingState()

    async def _detect_encoding(ctx: Context | None, resolved_base_dir: str) -> None:
        await ensure_encoding_detected(config, ctx, resolved_base_dir, _encoding_state)

    # -- Tools --

    @mcp.tool(
        timeout=300.0,
        annotations={
            "readOnlyHint": False,  # Modifies files
            "destructiveHint": True,  # Can overwrite content
            "idempotentHint": False,  # Same edit twice = different results
            "openWorldHint": False,  # Only local filesystem
        },
    )
    async def fast_apply(
        path: Annotated[
            str,
            Field(
                description="File path (absolute or relative to MCP_BASE_DIR; if MCP_BASE_DIR is unset, "
                "relative paths resolve against MCP Roots)."
            ),
        ],
        edit_snippet: Annotated[
            str,
            Field(
                description="Code snippet representing the changes. Include only the lines being added or "
                "modified, plus placeholder comments for unchanged parts: "
                "`// ... existing code ...` (JS/TS), `# ... existing code ...` (Python/shell). "
                "Anchor the edit with 1-2 verbatim lines from the existing file."
            ),
        ],
        instruction: Annotated[
            str,
            Field(
                description="Optional natural language hint to disambiguate the target location "
                "(e.g., 'add after imports', 'inside the if block')."
            ),
        ] = "",
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Edit or create a file using intelligent merging.

        For new files: writes content directly.
        For existing files: merges edit_snippet with current content using anchor lines.
        Anchor lines are verbatim lines copied from the existing file that help locate
        the exact edit target. Include 1-2 unique lines adjacent to the change.

        On error, the response includes a code field:
        - NEEDS_MORE_CONTEXT or APPLY_NOOP: merge model could not locate the target -
          add 1-2 unique anchor lines from immediately around the edit location.
        - BLAST_RADIUS_EXCEEDED: edit scope too large - split into smaller edits.

        On success: {status: "ok", diff: str (rendered unified diff)}.

        Do NOT use this tool to delete files or clear file contents.
        Use a dedicated file management tool for those operations.
        """
        from .apply import apply_file_logic

        base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
        await _detect_encoding(ctx, base_dir)
        if ctx is not None:
            await ctx.info(f"Applying to {path}")

        async def _on_progress(progress: int, total: int, message: str) -> None:
            if ctx is not None:
                await ctx.report_progress(progress=progress, total=total, message=message)

        result = await apply_file_logic(
            backend=_clients.get_apply(),
            file_path=path,
            edit_snippet=edit_snippet,
            instruction=instruction or None,  # Convert empty string to None internally
            base_dir=base_dir,
            extra_paths=config.extra_paths,
            on_progress=_on_progress,
        )
        if ctx is not None and result and result.get("status") == "ok":
            diff_preview = (result.get("diff") or "")[:200]
            await ctx.debug(f"Edit applied: {diff_preview}...")
        return result

    # Register agentic_search (always enabled)
    @mcp.tool(
        timeout=600.0,
        annotations={
            "readOnlyHint": True,  # Does not modify environment
            "destructiveHint": False,  # Read-only = non-destructive
            "idempotentHint": True,  # Same query = same results
            "openWorldHint": False,  # Only local codebase
        },
    )
    async def agentic_search(
        query: Annotated[
            str,
            Field(
                description="What to find. Prefer specific identifiers over vague concepts.\n"
                "  ✅ 'UserService class'\n"
                "  ✅ 'where is JWT validation done'\n"
                "  ❌ 'error handling' (too vague — results will be poor)\n"
                "Natural language or exact symbol names both accepted."
            ),
        ],
        ctx: Context,
    ) -> dict[str, Any]:
        """Search codebase for code locations matching a query.

        Use when you know the name or structure you're looking for —
        function names, class names, modules, or how components connect.
        For conceptual/behavioral queries without known identifiers, use agentic_retrieval instead.

        Returns file paths with line ranges and an explanation of findings.
        Keys: explanation (str), files (dict[path → {lines, snippet}]), turns_used (int).
        """
        from .search import FastAgenticSearchHarness

        await ctx.info(f"Searching: {query[:100]}")

        # Resolve base_dir dynamically from MCP Roots if not configured
        base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
        await _detect_encoding(ctx, base_dir)

        # Get cached LSP languages (auto-detects on first call per base_dir)
        from ..lsp.languages import get_lsp_languages

        lsp_languages = get_lsp_languages(Path(base_dir))

        effective_config = replace(config, base_dir=base_dir)

        async def _on_progress(turn: int, total: int) -> None:
            await ctx.report_progress(
                progress=turn, total=total, message=f"agentic_search turn {turn}/{total}"
            )

        result = await FastAgenticSearchHarness(
            effective_config, _clients.get_search(), lsp_languages=lsp_languages
        ).run_async(query=query, trace_id=get_trace_id(), on_progress=_on_progress)
        files_found = len(result.get("files", {}))
        await ctx.debug(f"Search found {files_found} files")
        return result

    @mcp.tool(
        timeout=120.0,
        annotations={
            "readOnlyHint": False,  # Schedules background reindex tasks when stale
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,  # Pure local read + local CLI scheduling
        },
    )
    async def index_status(
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Inspect indexing services status. Call before retrieval when hints seem stale or missing,
        or after index errors to check backend health.

        Single status entry point for all backends (Relace cloud, Codanna, ChunkHound).
        Reports freshness, hints_usable, and recommended_action for each backend.

        Side-effect: for local backends (Codanna/ChunkHound), automatically schedules
        a background reindex if the index is stale or missing AND the CLI is available,
        setting background_refresh_scheduled=true in the response.

        Return structure (top-level keys):
          relace     → {freshness, hints_usable, status.recommended_action, ...}
          codanna    → {freshness, hints_usable, background_refresh_scheduled, ...}
          chunkhound → {freshness, hints_usable, background_refresh_scheduled, ...}

        For Relace cloud: read-only; if stale, call cloud_sync().
        """
        from ..repo.backends import schedule_bg_chunkhound_index, schedule_bg_codanna_full_index
        from ..repo.core import get_current_git_info, is_git_dirty
        from ..repo.core.state import load_sync_state
        from ..repo.freshness import classify_cloud_index_freshness, classify_local_index_freshness

        trace_id = get_trace_id()

        try:
            base_dir, base_dir_source = await resolve_base_dir(config.base_dir, ctx)
        except Exception as exc:
            log_event(
                {
                    "kind": "index_status_error",
                    "level": "error",
                    "trace_id": trace_id,
                    "error": redact_value(str(exc), 500),
                }
            )
            return {
                "trace_id": trace_id,
                "base_dir": None,
                "error": str(exc),
            }

        base_path = Path(base_dir)

        # --- Relace (cloud) ---
        current_branch, current_head = get_current_git_info(base_dir)
        git_dirty = is_git_dirty(base_dir)
        sync_state = load_sync_state(base_dir)

        relace_freshness = classify_cloud_index_freshness(base_dir)

        relace_status: dict[str, Any] = {
            "cloud_tools_enabled": _settings.RELACE_CLOUD_TOOLS,
            "local_git": {
                "git_branch": current_branch,
                "git_head": current_head[:8] if current_head else "",
                "git_dirty": git_dirty,
            },
            "freshness": relace_freshness.freshness,
            "hints_usable": relace_freshness.hints_usable,
            "sync_state": None,
            "status": None,
        }

        if sync_state is None:
            relace_status["status"] = {
                "ref_changed": False,
                "needs_sync": True,
                "recommended_action": "No sync state found. Run cloud_sync().",
            }
        else:
            relace_status["sync_state"] = {
                "repo_id": sync_state.repo_id,
                "repo_head": sync_state.repo_head[:8] if sync_state.repo_head else "",
                "git_branch": sync_state.git_branch,
                "git_head": sync_state.git_head_sha[:8] if sync_state.git_head_sha else "",
                "last_sync": sync_state.last_sync,
                "tracked_files": len(sync_state.files),
                "skipped_files": len(sync_state.skipped_files),
                "files_found": sync_state.files_found,
                "files_selected": sync_state.files_selected,
                "file_limit": sync_state.file_limit,
                "files_truncated": sync_state.files_truncated,
            }

            ref_changed = False
            needs_sync = False
            recommended_action = None

            if sync_state.git_head_sha and current_head and sync_state.git_head_sha != current_head:
                ref_changed = True
                needs_sync = True
                recommended_action = (
                    "Git HEAD changed since last sync. Run cloud_sync() "
                    "or cloud_sync(force=True, mirror=True)."
                )
            elif git_dirty:
                needs_sync = True
                recommended_action = (
                    "Local working tree is dirty. Run cloud_sync() if you want cloud_search "
                    "to reflect uncommitted changes."
                )

            relace_status["status"] = {
                "ref_changed": ref_changed,
                "needs_sync": needs_sync,
                "recommended_action": recommended_action,
            }

        # --- Local backends (Codanna / ChunkHound) ---
        codanna_cli_path = shutil.which("codanna")
        chunkhound_cli_path = shutil.which("chunkhound")

        codanna_head_path = base_path / ".codanna" / "last_indexed_head"
        chunkhound_head_path = base_path / ".chunkhound" / "last_indexed_head"

        codanna_freshness = classify_local_index_freshness(base_dir, "codanna")
        chunkhound_freshness = classify_local_index_freshness(base_dir, "chunkhound")

        codanna_status: dict[str, Any] = {
            "cli_found": bool(codanna_cli_path),
            "cli_path": codanna_cli_path,
            "index_dir_exists": (base_path / ".codanna").is_dir(),
            "last_indexed_head": _read_text_safe(codanna_head_path),
            "freshness": codanna_freshness.freshness,
            "hints_usable": codanna_freshness.hints_usable,
            "background_refresh_scheduled": False,
        }
        chunkhound_status: dict[str, Any] = {
            "cli_found": bool(chunkhound_cli_path),
            "cli_path": chunkhound_cli_path,
            "index_dir_exists": (base_path / ".chunkhound").is_dir(),
            "last_indexed_head": _read_text_safe(chunkhound_head_path),
            "freshness": chunkhound_freshness.freshness,
            "hints_usable": chunkhound_freshness.hints_usable,
            "background_refresh_scheduled": False,
        }

        # Auto-schedule background refresh for stale/missing local backends
        for backend_name, status_obj, freshness_obj in (
            ("codanna", codanna_status, codanna_freshness),
            ("chunkhound", chunkhound_status, chunkhound_freshness),
        ):
            if not status_obj["cli_found"]:
                status_obj["hints_usable"] = False
                continue
            if freshness_obj.refresh_recommended:
                if backend_name == "codanna":
                    schedule_bg_codanna_full_index(base_dir)
                else:
                    schedule_bg_chunkhound_index(base_dir)
                status_obj["background_refresh_scheduled"] = True

        payload = {
            "trace_id": trace_id,
            "base_dir": base_dir,
            "base_dir_source": base_dir_source,
            "retrieval_backend": _settings.RETRIEVAL_BACKEND,
            "relace": relace_status,
            "codanna": codanna_status,
            "chunkhound": chunkhound_status,
        }

        relace_needs_sync = None
        relace_recommended_action = None
        if isinstance(relace_status.get("status"), dict):
            relace_needs_sync = relace_status["status"].get("needs_sync")
            relace_recommended_action = relace_status["status"].get("recommended_action")

        log_event(
            {
                "kind": "index_status",
                "level": "info",
                "trace_id": trace_id,
                "base_dir": base_dir,
                "base_dir_source": base_dir_source,
                "retrieval_backend": _settings.RETRIEVAL_BACKEND,
                "relace_cloud_tools_enabled": bool(relace_status.get("cloud_tools_enabled")),
                "relace_freshness": relace_status.get("freshness"),
                "relace_hints_usable": relace_status.get("hints_usable"),
                "relace_needs_sync": relace_needs_sync,
                "relace_recommended_action": redact_value(
                    str(relace_recommended_action),
                    500,
                )
                if relace_recommended_action
                else None,
                "codanna_cli_found": bool(codanna_status.get("cli_found")),
                "codanna_index_dir_exists": bool(codanna_status.get("index_dir_exists")),
                "codanna_last_indexed_head": codanna_status.get("last_indexed_head"),
                "codanna_freshness": codanna_status.get("freshness"),
                "codanna_hints_usable": codanna_status.get("hints_usable"),
                "codanna_background_refresh_scheduled": codanna_status.get(
                    "background_refresh_scheduled"
                ),
                "chunkhound_cli_found": bool(chunkhound_status.get("cli_found")),
                "chunkhound_index_dir_exists": bool(chunkhound_status.get("index_dir_exists")),
                "chunkhound_last_indexed_head": chunkhound_status.get("last_indexed_head"),
                "chunkhound_freshness": chunkhound_status.get("freshness"),
                "chunkhound_hints_usable": chunkhound_status.get("hints_usable"),
                "chunkhound_background_refresh_scheduled": chunkhound_status.get(
                    "background_refresh_scheduled"
                ),
            }
        )

        return payload

    # Cloud Repos (Semantic Search & Sync) - registered always (visibility is session-scoped)

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

        base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
        return await asyncio.to_thread(
            cloud_sync_logic,
            _clients.get_repo(),
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

        # Fixed internal parameters (not exposed to LLM)
        score_threshold = 0.3
        token_limit = 30000

        # Resolve base_dir dynamically from MCP Roots if not configured
        base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
        return await asyncio.to_thread(
            cloud_search_logic,
            _clients.get_repo(),
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

        base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
        return await asyncio.to_thread(
            cloud_clear_logic,
            _clients.get_repo(),
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

        return cloud_list_logic(_clients.get_repo())

    if _settings.AGENTIC_RETRIEVAL_ENABLED:

        @mcp.tool(
            timeout=900.0,
            annotations={
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": _settings.RETRIEVAL_BACKEND in ("relace", "auto")
                and _settings.RELACE_CLOUD_TOOLS,
            },
        )
        async def agentic_retrieval(
            query: Annotated[
                str,
                Field(
                    description="Describe the behavior or concept to find. Be SPECIFIC — vague queries skip semantic hints.\n"
                    "  ❌ 'auth logic'\n"
                    "  ✅ 'function that validates JWT tokens and extracts user ID'\n"
                    "  ❌ 'error handling'\n"
                    "  ✅ 'where HTTP 4xx errors are caught and transformed to user messages'\n"
                    "Natural language only; do not use bare symbol names."
                ),
            ],
            ctx: Context | None = None,
        ) -> dict[str, Any]:
            """Find code by meaning using two-stage retrieval: semantic hints + agentic exploration.

            Use when the query is conceptual and you don't know exact names or keywords —
            searching for behaviors, patterns, or side-effects.

            Requires a semantic index (Codanna, ChunkHound, or Relace Cloud) for semantic hints;
            falls back to agentic exploration only if no index is available.

            Returns file paths with line ranges and relevance-ranked results.
            Keys: explanation (str), files (dict[path → {lines, snippet}]),
                  semantic_hints_used (int), retrieval_backend (str), warnings (list[str]).
            """
            from .retrieval import agentic_retrieval_logic

            if ctx is not None:
                await ctx.info(f"Retrieval: {query[:100]}")

            base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
            await _detect_encoding(ctx, base_dir)

            async def _on_progress(turn: int, total: int) -> None:
                if ctx is not None:
                    await ctx.report_progress(
                        progress=turn,
                        total=total,
                        message=f"agentic_retrieval turn {turn}/{total}",
                    )

            result = await agentic_retrieval_logic(
                _clients.get_repo(),
                _clients.get_search(),
                config,
                base_dir,
                query,
                on_progress=_on_progress,
            )
            if ctx is not None:
                files_found = len(result.get("files", {}))
                await ctx.debug(f"Retrieval found {files_found} files")
            return result

    # === MCP Resources ===

    @mcp.resource("relace://tools_list", mime_type="application/json")
    async def tools_list() -> str:
        """List all registered Relace MCP tools with their enabled status."""
        raw_tools = await mcp.local_provider.list_tools()
        cloud_enabled = bool(_settings.RELACE_CLOUD_TOOLS)
        result = []
        for t in raw_tools:
            is_cloud = "cloud" in t.tags
            enabled = cloud_enabled if is_cloud else True
            result.append(
                {
                    "id": t.name,
                    "name": t.name,
                    "description": (t.description or "").split("\n")[0].strip(),
                    "enabled": enabled,
                }
            )
        return json.dumps(result)

    @mcp.resource(
        "relace://cloud/status",
        mime_type="application/json",
        tags={"cloud"},
    )
    async def cloud_status(ctx: Context | None = None) -> str:
        """Current cloud sync status — lightweight, reads local state file only (no API calls).

        For dashboard/UI display. Agents should use the index_status tool instead,
        which covers Relace, Codanna, and ChunkHound backends with recommended_action.
        """
        try:
            base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
        except RuntimeError:
            return json.dumps(
                {
                    "synced": False,
                    "error": "base_dir not configured",
                    "message": "Set MCP_BASE_DIR or use MCP Roots to enable cloud status",
                }
            )

        from ..repo.core.state import get_repo_identity, load_sync_state

        local_repo_name, cloud_repo_name, _project_fingerprint = get_repo_identity(base_dir)
        if not local_repo_name or not cloud_repo_name:
            return json.dumps(
                {
                    "synced": False,
                    "error": "invalid base_dir",
                    "message": "Cannot derive repository identity from base_dir; ensure MCP_BASE_DIR or MCP Roots points to a project directory.",
                }
            )

        state = load_sync_state(base_dir)

        if state is None:
            return json.dumps(
                {
                    "synced": False,
                    "repo_name": local_repo_name,
                    "cloud_repo_name": cloud_repo_name,
                    "message": "No sync state found. Run cloud_sync to upload codebase.",
                }
            )

        return json.dumps(
            {
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
        )

    # Default: hide cloud components unless explicitly enabled for the session.
    mcp.disable(tags={"cloud"})
