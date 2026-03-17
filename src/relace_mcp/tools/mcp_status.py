# pyright: reportUnusedFunction=false
import shutil
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.context import Context

from ..config import resolve_base_dir
from ..config import settings as _settings
from ..observability import get_trace_id, log_event, redact_value
from ..repo.backends import schedule_bg_chunkhound_index, schedule_bg_codanna_full_index
from ..repo.core import get_current_git_info, is_git_dirty
from ..repo.core.state import load_sync_state
from ..repo.freshness import classify_cloud_index_freshness, classify_local_index_freshness
from ._registry import ToolRegistryDeps, read_text_safe


def register_status_tools(mcp: FastMCP, deps: ToolRegistryDeps) -> None:
    @mcp.tool(
        timeout=120.0,
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
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
        trace_id = get_trace_id()

        try:
            base_dir, base_dir_source = await resolve_base_dir(deps.config.base_dir, ctx)
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
            "last_indexed_head": read_text_safe(codanna_head_path),
            "freshness": codanna_freshness.freshness,
            "hints_usable": codanna_freshness.hints_usable,
            "background_refresh_scheduled": False,
        }
        chunkhound_status: dict[str, Any] = {
            "cli_found": bool(chunkhound_cli_path),
            "cli_path": chunkhound_cli_path,
            "index_dir_exists": (base_path / ".chunkhound").is_dir(),
            "last_indexed_head": read_text_safe(chunkhound_head_path),
            "freshness": chunkhound_freshness.freshness,
            "hints_usable": chunkhound_freshness.hints_usable,
            "background_refresh_scheduled": False,
        }

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
