# pyright: reportUnusedFunction=false
# Decorator-registered functions (@mcp.tool, @mcp.resource) are accessed by the framework
import asyncio
import inspect
import json
import logging
import shutil
import threading
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from fastmcp import FastMCP
from fastmcp.server.context import Context
from pydantic import Field

from ..config import RelaceConfig, resolve_base_dir
from ..config.settings import AGENTIC_RETRIEVAL_ENABLED, RELACE_CLOUD_TOOLS, RETRIEVAL_BACKEND
from ..observability import get_trace_id, log_event, redact_value

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

    # -- Lazy client factories (thread-safe, constructed on first tool call) --

    _apply_lock = threading.Lock()
    _apply_inst = None

    def _get_apply_client() -> "ApplyLLMClient":
        nonlocal _apply_inst
        if _apply_inst is None:
            with _apply_lock:
                if _apply_inst is None:
                    from ..clients.apply import ApplyLLMClient

                    _apply_inst = ApplyLLMClient(config)
        return _apply_inst

    _search_lock = threading.Lock()
    _search_inst = None

    def _get_search_client() -> "SearchLLMClient":
        nonlocal _search_inst
        if _search_inst is None:
            with _search_lock:
                if _search_inst is None:
                    from ..clients.search import SearchLLMClient

                    _search_inst = SearchLLMClient(config)
        return _search_inst

    _repo_lock = threading.Lock()
    _repo_inst = None

    def _get_repo_client() -> "RelaceRepoClient":
        nonlocal _repo_inst
        if _repo_inst is None:
            with _repo_lock:
                if _repo_inst is None:
                    from ..clients.repo import RelaceRepoClient

                    _repo_inst = RelaceRepoClient(config)
        return _repo_inst

    # -- Lazy encoding detection (runs once on first tool call that needs it) --

    _encoding_lock = threading.Lock()
    _encoding_done = False

    def _ensure_encoding_detected(resolved_base_dir: str | None = None) -> None:
        nonlocal _encoding_done
        if _encoding_done:
            return
        with _encoding_lock:
            if _encoding_done:
                return
            from ..config.settings import ENCODING_DETECTION_SAMPLE_LIMIT
            from ..encoding import set_project_encoding
            from .apply.encoding import detect_project_encoding

            if config.default_encoding:
                logger.debug("Using configured project encoding: %s", config.default_encoding)
                set_project_encoding(config.default_encoding)
                _encoding_done = True
            else:
                base = resolved_base_dir or config.base_dir
                if base:
                    detected = detect_project_encoding(
                        Path(base),
                        sample_limit=ENCODING_DETECTION_SAMPLE_LIMIT,
                    )
                    if detected:
                        logger.debug("Auto-detected project encoding: %s", detected)
                        set_project_encoding(detected)
                    else:
                        logger.debug("No regional encoding detected, using UTF-8 as default")
                    _encoding_done = True
                else:
                    logger.debug("Skipping encoding detection: base_dir not yet resolved")

    # -- Helpers --

    async def _progress_heartbeat(ctx: Context, *, message: str) -> None:
        while True:
            try:
                maybe = ctx.report_progress(progress=0, total=1.0, message=message)
                if inspect.isawaitable(maybe):
                    await maybe
            except Exception:
                return
            await asyncio.sleep(5)

    # -- Tools --

    @mcp.tool(
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
                description="New content. Use placeholders for unchanged parts: "
                "`// ... existing code ...` (C/JS/TS), `# ... existing code ...` (Python/shell)."
            ),
        ],
        instruction: Annotated[
            str,
            Field(description="Optional hint when edit is ambiguous (e.g., 'add after imports')."),
        ] = "",
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Edit or create a file using intelligent merging.

        For new files: writes content directly.
        For existing files: merges edit_snippet with current content using anchor lines.
        If anchors cannot be located, returns NEEDS_MORE_CONTEXT error—provide complete
        file content to fully overwrite, or add context lines to help locate the edit point.
        """
        from .apply import apply_file_logic

        progress_task = None
        if ctx is not None:
            progress_task = asyncio.create_task(
                _progress_heartbeat(ctx, message="fast_apply in progress")
            )
        try:
            base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
            _ensure_encoding_detected(base_dir)
            if ctx is not None:
                await ctx.info(f"Applying edit to {path}")
            result = await apply_file_logic(
                backend=_get_apply_client(),
                file_path=path,
                edit_snippet=edit_snippet,
                instruction=instruction or None,  # Convert empty string to None internally
                base_dir=base_dir,
                extra_paths=config.extra_paths,
            )
            if ctx is not None and result and result.get("status") == "ok":
                diff_preview = (result.get("diff") or "")[:200]
                await ctx.debug(f"Edit applied: {diff_preview}...")
            if result and result.get("status") == "ok":
                import shutil as _shutil

                from ..repo.backends import (
                    is_backend_disabled,
                    schedule_bg_chunkhound_index,
                    schedule_bg_codanna_index,
                )

                if _shutil.which("chunkhound") and not is_backend_disabled("chunkhound"):
                    schedule_bg_chunkhound_index(base_dir)
                if _shutil.which("codanna") and not is_backend_disabled("codanna"):
                    schedule_bg_codanna_index(result.get("path", path), base_dir)
            return result
        finally:
            if progress_task is not None:
                progress_task.cancel()
                with suppress(asyncio.CancelledError):
                    await progress_task

    # Register agentic_search (always enabled)
    @mcp.tool(
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
                description="What to find. Natural language (e.g., 'where is auth handled') "
                "or specific patterns (e.g., 'UserService class')."
            ),
        ],
        ctx: Context,
    ) -> dict[str, Any]:
        """Search codebase for code locations matching a query.

        Finds functions, classes, modules, and traces how components connect.
        Accepts natural language or specific patterns like class/function names.

        Returns file paths with line ranges and an explanation of findings.
        """
        from .search import FastAgenticSearchHarness

        await ctx.info(f"Searching: {query[:100]}")
        progress_task = asyncio.create_task(
            _progress_heartbeat(ctx, message="agentic_search in progress")
        )
        try:
            # Resolve base_dir dynamically from MCP Roots if not configured
            base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
            _ensure_encoding_detected(base_dir)

            # Get cached LSP languages (auto-detects on first call per base_dir)
            from ..lsp.languages import get_lsp_languages

            lsp_languages = get_lsp_languages(Path(base_dir))

            effective_config = replace(config, base_dir=base_dir)
            result = await FastAgenticSearchHarness(
                effective_config, _get_search_client(), lsp_languages=lsp_languages
            ).run_async(query=query, trace_id=get_trace_id())
            files_found = len(result.get("files", {}))
            await ctx.debug(f"Search found {files_found} files")
            return result
        finally:
            progress_task.cancel()
            with suppress(asyncio.CancelledError):
                await progress_task

    @mcp.tool(
        annotations={
            "readOnlyHint": False,  # probe=True may auto-index via external CLIs
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": RELACE_CLOUD_TOOLS,  # probe may call cloud_info
        }
    )
    async def indexing_status(
        probe: Annotated[
            bool,
            Field(
                description=(
                    "If True, run active health probes for local backends (may auto-index) "
                    "and run cloud_info when RELACE_CLOUD_TOOLS=1."
                )
            ),
        ] = False,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Inspect indexing services status.

        This reports:
        - Relace cloud repo sync/index status (passive by default; probe can call cloud_info)
        - Codanna local index status (markers + optional health probe)
        - ChunkHound local index status (markers + optional health probe)
        """
        from ..repo.core import get_current_git_info, is_git_dirty
        from ..repo.core.state import load_sync_state

        trace_id = get_trace_id()

        try:
            base_dir, base_dir_source = await resolve_base_dir(config.base_dir, ctx)
        except Exception as exc:
            log_event(
                {
                    "kind": "indexing_status_error",
                    "level": "error",
                    "trace_id": trace_id,
                    "probe": probe,
                    "error": redact_value(str(exc), 500),
                }
            )
            return {
                "trace_id": trace_id,
                "probe": probe,
                "base_dir": None,
                "error": str(exc),
            }

        base_path = Path(base_dir)

        # --- Relace (cloud) ---
        current_branch, current_head = get_current_git_info(base_dir)
        git_dirty = is_git_dirty(base_dir)
        sync_state = load_sync_state(base_dir)

        relace_status: dict[str, Any] = {
            "cloud_tools_enabled": RELACE_CLOUD_TOOLS,
            "local_git": {
                "git_branch": current_branch,
                "git_head": current_head[:8] if current_head else "",
                "git_dirty": git_dirty,
            },
            "sync_state": None,
            "status": None,
            "probe": None,
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

        if probe:
            if not RELACE_CLOUD_TOOLS:
                relace_status["probe"] = {
                    "status": "skipped",
                    "reason": "RELACE_CLOUD_TOOLS is disabled",
                }
            else:
                from ..repo.cloud.info import cloud_info_logic

                relace_status["probe"] = await asyncio.to_thread(
                    cloud_info_logic,
                    _get_repo_client(),
                    base_dir,
                )

        # --- Local backends (Codanna / ChunkHound) ---
        codanna_cli_path = shutil.which("codanna")
        chunkhound_cli_path = shutil.which("chunkhound")

        codanna_head_path = base_path / ".codanna" / "last_indexed_head"
        chunkhound_head_path = base_path / ".chunkhound" / "last_indexed_head"

        codanna_status: dict[str, Any] = {
            "cli_found": bool(codanna_cli_path),
            "cli_path": codanna_cli_path,
            "index_dir_exists": (base_path / ".codanna").is_dir(),
            "last_indexed_head": _read_text_safe(codanna_head_path),
            "probe": None,
        }
        chunkhound_status: dict[str, Any] = {
            "cli_found": bool(chunkhound_cli_path),
            "cli_path": chunkhound_cli_path,
            "index_dir_exists": (base_path / ".chunkhound").is_dir(),
            "last_indexed_head": _read_text_safe(chunkhound_head_path),
            "probe": None,
        }

        if probe:
            from ..repo.backends import ExternalCLIError, check_backend_health

            for backend_name, status_obj in (
                ("codanna", codanna_status),
                ("chunkhound", chunkhound_status),
            ):
                if not status_obj.get("cli_found"):
                    status_obj["probe"] = {
                        "status": "error",
                        "kind": "cli_not_found",
                        "message": f"{backend_name} CLI not found in PATH",
                    }
                    continue

                try:
                    probe_status = await asyncio.to_thread(
                        check_backend_health,
                        backend_name,
                        base_dir,
                    )
                    status_obj["probe"] = {"status": probe_status}
                except ExternalCLIError as exc:
                    status_obj["probe"] = {
                        "status": "error",
                        "backend": exc.backend,
                        "kind": exc.kind,
                        "message": str(exc),
                        "command": exc.command,
                    }
                except Exception as exc:
                    status_obj["probe"] = {
                        "status": "error",
                        "kind": type(exc).__name__,
                        "message": str(exc),
                    }

        payload = {
            "trace_id": trace_id,
            "probe": probe,
            "base_dir": base_dir,
            "base_dir_source": base_dir_source,
            "retrieval_backend": RETRIEVAL_BACKEND,
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
                "kind": "indexing_status",
                "level": "info",
                "trace_id": trace_id,
                "probe": probe,
                "base_dir": base_dir,
                "base_dir_source": base_dir_source,
                "retrieval_backend": RETRIEVAL_BACKEND,
                "relace_cloud_tools_enabled": bool(relace_status.get("cloud_tools_enabled")),
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
                "codanna_probe": codanna_status.get("probe"),
                "chunkhound_cli_found": bool(chunkhound_status.get("cli_found")),
                "chunkhound_index_dir_exists": bool(chunkhound_status.get("index_dir_exists")),
                "chunkhound_last_indexed_head": chunkhound_status.get("last_indexed_head"),
                "chunkhound_probe": chunkhound_status.get("probe"),
            }
        )

        return payload

    # Cloud Repos (Semantic Search & Sync) - registered always (visibility is session-scoped)

    @mcp.tool(
        tags={"cloud"},
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
        """Upload codebase to Relace Cloud for semantic search.

        Syncs git-tracked files to enable cloud_search. Incremental by default—only
        uploads changed files. Run once per session before using cloud_search.

        Fails if not in a git repository or RELACE_API_KEY is not set.
        """
        from ..repo.cloud.sync import cloud_sync_logic

        base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
        return await asyncio.to_thread(
            cloud_sync_logic,
            _get_repo_client(),
            base_dir,
            force=force,
            mirror=mirror,
        )

    @mcp.tool(
        tags={"cloud"},
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def cloud_search(
        query: Annotated[str, Field(description="Natural language search query.")],
        branch: Annotated[
            str, Field(description="Branch to search (empty = default branch).")
        ] = "",
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Semantic code search using AI embeddings. Requires cloud_sync first.

        Finds code by meaning, not just keywords. Returns ranked results with relevance scores.
        """
        from ..repo.cloud.search import cloud_search_logic

        # Fixed internal parameters (not exposed to LLM)
        score_threshold = 0.3
        token_limit = 30000

        # Resolve base_dir dynamically from MCP Roots if not configured
        base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
        return await asyncio.to_thread(
            cloud_search_logic,
            _get_repo_client(),
            base_dir,
            query,
            branch=branch,
            score_threshold=score_threshold,
            token_limit=token_limit,
        )

    @mcp.tool(
        tags={"cloud"},
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
            _get_repo_client(),
            base_dir,
            confirm=confirm,
            repo_id=repo_id,
        )

    @mcp.tool(
        tags={"cloud"},
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    def cloud_list(
        reason: Annotated[
            str, Field(description="Why you need this list (helps with debugging).")
        ] = "",
    ) -> dict[str, Any]:
        """List all repositories in your Relace Cloud account.

        Returns repository IDs, names, and indexing status. Use to find repo_id for cloud_clear.
        """
        from ..repo.cloud.list import cloud_list_logic

        del reason  # LLM chain-of-thought only
        return cloud_list_logic(_get_repo_client())

    @mcp.tool(
        tags={"cloud"},
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def cloud_info(
        reason: Annotated[
            str, Field(description="Why you need sync status (helps with debugging).")
        ] = "",
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Check sync status before running cloud_sync.

        Shows local git state, last sync info, and whether re-sync is needed.
        Helps decide if cloud_sync should be called.
        """
        from ..repo.cloud.info import cloud_info_logic

        del reason  # LLM chain-of-thought only
        base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
        return await asyncio.to_thread(cloud_info_logic, _get_repo_client(), base_dir)

    if AGENTIC_RETRIEVAL_ENABLED and RETRIEVAL_BACKEND != "none":

        @mcp.tool(
            annotations={
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": RETRIEVAL_BACKEND == "relace",
            },
        )
        async def agentic_retrieval(
            query: Annotated[
                str,
                Field(
                    description="Be SPECIFIC. Examples: "
                    "❌ 'auth logic' "
                    "✅ 'function that validates JWT tokens and extracts user ID' "
                    "❌ 'error handling' "
                    "✅ 'where HTTP 4xx errors are caught and transformed to user messages'"
                ),
            ],
            ctx: Context | None = None,
        ) -> dict[str, Any]:
            """Find code by semantic similarity. Best for conceptual queries.

            When you know what behavior you're looking for but not the exact names or keywords.
            Returns file paths with line ranges and relevance-ranked results.
            """
            from .retrieval import agentic_retrieval_logic

            progress_task = None
            if ctx is not None:
                await ctx.info(f"Retrieval: {query[:100]}")
                progress_task = asyncio.create_task(
                    _progress_heartbeat(ctx, message="agentic_retrieval in progress")
                )
            try:
                base_dir, _ = await resolve_base_dir(config.base_dir, ctx)
                _ensure_encoding_detected(base_dir)
                result = await agentic_retrieval_logic(
                    _get_repo_client(),
                    _get_search_client(),
                    config,
                    base_dir,
                    query,
                )
                if ctx is not None:
                    files_found = len(result.get("files", {}))
                    await ctx.debug(f"Retrieval found {files_found} files")
                return result
            finally:
                if progress_task is not None:
                    progress_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await progress_task

    # === MCP Resources ===

    @mcp.resource("relace://tools_list", mime_type="application/json")
    def tools_list() -> str:
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
        # agentic_search is always enabled
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
                "id": "indexing_status",
                "name": "Indexing Status",
                "description": "Inspect indexing services status (relace/codanna/chunkhound)",
                "enabled": True,
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
        if AGENTIC_RETRIEVAL_ENABLED and RETRIEVAL_BACKEND != "none":
            tools.append(
                {
                    "id": "agentic_retrieval",
                    "name": "Agentic Retrieval",
                    "description": "Two-stage semantic + agentic code retrieval",
                    "enabled": True,
                }
            )
        return json.dumps(tools)

    @mcp.resource(
        "relace://cloud/status",
        mime_type="application/json",
        tags={"cloud"},
    )
    async def cloud_status(ctx: Context | None = None) -> str:
        """Current cloud sync status - lightweight read from local state file.

        Returns sync state without making API calls. Use this to quickly check
        if cloud_sync has been run and what the current sync status is.
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


if TYPE_CHECKING:
    from ..clients.apply import ApplyLLMClient
    from ..clients.repo import RelaceRepoClient
    from ..clients.search import SearchLLMClient
