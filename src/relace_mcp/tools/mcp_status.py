# pyright: reportUnusedFunction=false
import shutil
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.context import Context

from ..config import resolve_base_dir
from ..observability import get_trace_id, log_event, redact_value
from ..repo.core import get_current_git_info, is_git_dirty
from ..repo.core.state import load_sync_state
from ..repo.freshness import classify_cloud_index_freshness, classify_local_index_freshness
from ..repo.monitor import get_background_index_monitor_summary
from ._registry import ToolRegistryDeps


def _build_relace_status(base_dir: str) -> dict[str, Any]:
    current_branch, current_head = get_current_git_info(base_dir)
    git_dirty = is_git_dirty(base_dir)
    sync_state = load_sync_state(base_dir)

    relace_freshness = classify_cloud_index_freshness(base_dir)
    relace_status: dict[str, Any] = {
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
        return relace_status

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
    return relace_status


def _build_local_backend_status(base_dir: str, backend_name: str) -> dict[str, Any]:
    cli_path = shutil.which(backend_name)
    freshness = classify_local_index_freshness(base_dir, backend_name)

    status_obj: dict[str, Any] = {
        "cli_path": cli_path,
        "freshness": freshness.freshness,
        "hints_usable": freshness.hints_usable if cli_path else False,
    }
    return status_obj


def register_status_tools(mcp: FastMCP, deps: ToolRegistryDeps) -> None:
    @mcp.tool(
        timeout=120.0,
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def index_status(
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Inspect the active indexing backend status without mutating index state.

        Returns a single active backend summary plus background monitor state when applicable.
        For Relace cloud, use cloud_sync() to refresh the index when stale.
        """
        trace_id = get_trace_id()

        try:
            base_dir, base_dir_source = await resolve_base_dir(deps.config.base_dir, ctx)
        except Exception as exc:
            log_event(
                {
                    "kind": "index_status_error",
                    "level": "error",
                    "trace_id": trace_id,
                    "active_backend": deps.index_runtime.active_backend,
                    "error": redact_value(str(exc), 500),
                }
            )
            return {
                "trace_id": trace_id,
                "active_backend": deps.index_runtime.active_backend,
                "base_dir": None,
                "error": str(exc),
            }

        active_backend = deps.index_runtime.active_backend
        if active_backend == "relace":
            backend_status = _build_relace_status(base_dir)
        else:
            backend_status = _build_local_backend_status(base_dir, active_backend)

        payload: dict[str, Any] = {
            "trace_id": trace_id,
            "base_dir": base_dir,
            "base_dir_source": base_dir_source,
            "active_backend": active_backend,
            "backend": backend_status,
            "background_monitor": get_background_index_monitor_summary(mcp),
        }

        log_event(
            {
                "kind": "index_status",
                "level": "info",
                "trace_id": trace_id,
                "active_backend": active_backend,
                "base_dir": base_dir,
                "base_dir_source": base_dir_source,
                "backend_freshness": backend_status.get("freshness"),
                "backend_hints_usable": backend_status.get("hints_usable"),
                "background_monitor_enabled": payload["background_monitor"].get("enabled"),
                "background_monitor_reason": payload["background_monitor"].get("reason"),
            }
        )

        return payload
