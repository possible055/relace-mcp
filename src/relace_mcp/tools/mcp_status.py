# pyright: reportUnusedFunction=false
import shutil
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.server.context import Context
from pydantic import BaseModel, ConfigDict, Field

from ..config import resolve_base_dir
from ..config import settings as _settings
from ..observability import get_trace_id, log_event, redact_value
from ..repo.backends import is_backend_disabled
from ..repo.core import get_current_git_info, is_git_dirty
from ..repo.core.state import load_sync_state
from ..repo.freshness import (
    classify_cloud_index_freshness,
    classify_local_index_freshness,
    semantic_hints_usable_for_policy,
)
from ..repo.monitor import get_background_index_monitor_summary
from ._registry import ToolRegistryDeps


class _StatusModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BackgroundMonitorSummary(_StatusModel):
    state: str = Field(description="Current background monitor state.")
    reason: str | None = Field(description="Reason for the current monitor state, if any.")
    interval_seconds: float | None = Field(
        description="Configured monitor interval in seconds when the monitor is requested."
    )
    initial_delay_seconds: float | None = Field(
        description="Configured startup delay in seconds when the monitor is requested."
    )


class LocalGitStatus(_StatusModel):
    git_branch: str = Field(description="Current local git branch.")
    git_head: str = Field(description="Current local git HEAD, shortened to 8 characters.")
    git_dirty: bool = Field(description="Whether the local working tree has uncommitted changes.")


class RelaceSyncState(_StatusModel):
    repo_id: str = Field(description="Relace Cloud repository ID from the last successful sync.")
    repo_head: str = Field(description="Cloud repository HEAD, shortened to 8 characters.")
    git_branch: str = Field(description="Git branch recorded at the last sync.")
    git_head: str = Field(
        description="Git HEAD recorded at the last sync, shortened to 8 characters."
    )
    last_sync: str = Field(description="Timestamp of the last successful sync.")
    tracked_files: int = Field(description="Number of tracked files included in sync state.")
    skipped_files: int = Field(description="Number of files skipped during the last sync.")
    files_found: int = Field(description="Number of files discovered before sync filtering.")
    files_selected: int = Field(description="Number of files selected for sync.")
    file_limit: int = Field(description="Configured file selection limit for sync.")
    files_truncated: int = Field(
        description="Number of files omitted because sync hit the configured file limit."
    )


class RelaceSyncStatus(_StatusModel):
    ref_changed: bool = Field(description="Whether git HEAD changed since the last cloud sync.")
    needs_sync: bool = Field(description="Whether the cloud index should be refreshed.")
    recommended_action: str | None = Field(
        description="Suggested next action when the cloud index is stale or missing."
    )


class RelaceBackendStatus(_StatusModel):
    local_git: LocalGitStatus = Field(description="Current local git state for the workspace.")
    freshness: str = Field(description="Freshness classification for the Relace cloud index.")
    hints_usable: bool = Field(description="Whether semantic hints are safe to use right now.")
    sync_state: RelaceSyncState | None = Field(
        description="Last known cloud sync metadata, or null when no sync has been recorded."
    )
    status: RelaceSyncStatus | None = Field(
        description="Sync recommendation details, or null when no extra action is needed."
    )


class LocalBackendStatus(_StatusModel):
    cli_path: str | None = Field(
        description="Resolved CLI path for the active local backend, or null when not installed."
    )
    freshness: str = Field(description="Freshness classification for the active local index.")
    hints_usable: bool = Field(
        description="Whether semantic hints are usable for the active backend."
    )


ActiveBackend = Literal["relace", "codanna", "chunkhound"]


class IndexStatusToolOutput(_StatusModel):
    trace_id: str = Field(description="Trace ID for correlating logs for this tool call.")
    active_backend: ActiveBackend = Field(description="The configured active indexing backend.")
    base_dir: str | None = Field(
        default=None, description="Resolved repository base directory, if available."
    )
    base_dir_source: str | None = Field(
        default=None,
        description="How the base directory was resolved, when resolution succeeded.",
    )
    backend: RelaceBackendStatus | LocalBackendStatus | None = Field(
        default=None,
        description="Status summary for the active backend, when inspection succeeded.",
    )
    background_monitor: BackgroundMonitorSummary | None = Field(
        default=None,
        description="Background monitor state summary, when inspection succeeded.",
    )
    error: str | None = Field(
        default=None,
        description="Error message explaining why status inspection failed.",
    )


def _build_relace_status(base_dir: str) -> RelaceBackendStatus:
    current_branch, current_head = get_current_git_info(base_dir)
    git_dirty = is_git_dirty(base_dir)
    sync_state = load_sync_state(base_dir)

    relace_freshness = classify_cloud_index_freshness(base_dir)
    relace_status = RelaceBackendStatus(
        local_git=LocalGitStatus(
            git_branch=current_branch,
            git_head=current_head[:8] if current_head else "",
            git_dirty=git_dirty,
        ),
        freshness=relace_freshness.freshness,
        hints_usable=semantic_hints_usable_for_policy(
            relace_freshness.freshness,
            _settings.RETRIEVAL_HINT_POLICY,
        ),
        sync_state=None,
        status=None,
    )

    if sync_state is None:
        relace_status.status = RelaceSyncStatus(
            ref_changed=False,
            needs_sync=True,
            recommended_action="No sync state found. Run cloud_sync().",
        )
        return relace_status

    relace_status.sync_state = RelaceSyncState(
        repo_id=sync_state.repo_id,
        repo_head=sync_state.repo_head[:8] if sync_state.repo_head else "",
        git_branch=sync_state.git_branch,
        git_head=sync_state.git_head_sha[:8] if sync_state.git_head_sha else "",
        last_sync=sync_state.last_sync,
        tracked_files=len(sync_state.files),
        skipped_files=len(sync_state.skipped_files),
        files_found=sync_state.files_found,
        files_selected=sync_state.files_selected,
        file_limit=sync_state.file_limit,
        files_truncated=sync_state.files_truncated,
    )

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

    relace_status.status = RelaceSyncStatus(
        ref_changed=ref_changed,
        needs_sync=needs_sync,
        recommended_action=recommended_action,
    )
    return relace_status


def _build_local_backend_status(base_dir: str, backend_name: str) -> LocalBackendStatus:
    cli_path = shutil.which(backend_name)
    freshness = classify_local_index_freshness(base_dir, backend_name)
    hints_usable = bool(
        cli_path
        and not is_backend_disabled(backend_name)
        and semantic_hints_usable_for_policy(
            freshness.freshness,
            _settings.RETRIEVAL_HINT_POLICY,
        )
    )

    return LocalBackendStatus(
        cli_path=cli_path,
        freshness=freshness.freshness,
        hints_usable=hints_usable,
    )


def register_status_tools(mcp: FastMCP, deps: ToolRegistryDeps) -> None:
    @mcp.tool(
        output_schema=IndexStatusToolOutput.model_json_schema(),
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
        """Inspect the single active indexing backend in read-only mode.

        Use this before retrieval when you need to know whether the active backend is fresh and
        whether semantic hints are usable. Returns `active_backend`, a single `backend` status
        object with `freshness` and `hints_usable`, and `background_monitor` (`state`, `reason`).
        This tool never refreshes indexes; if `active_backend` is `relace` and
        `backend.status.needs_sync` is true, run cloud_sync().
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
        if active_backend == "none":
            raise RuntimeError("index_status is unavailable when MCP_RETRIEVAL_BACKEND=none")
        background_monitor = BackgroundMonitorSummary.model_validate(
            get_background_index_monitor_summary(mcp)
        )
        backend_status: RelaceBackendStatus | LocalBackendStatus
        if active_backend == "relace":
            backend_status = _build_relace_status(base_dir)
            payload = IndexStatusToolOutput(
                trace_id=trace_id,
                base_dir=base_dir,
                base_dir_source=base_dir_source,
                active_backend=active_backend,
                backend=backend_status,
                background_monitor=background_monitor,
            )
        else:
            local_backend = active_backend
            backend_status = _build_local_backend_status(base_dir, local_backend)
            payload = IndexStatusToolOutput(
                trace_id=trace_id,
                base_dir=base_dir,
                base_dir_source=base_dir_source,
                active_backend=local_backend,
                backend=backend_status,
                background_monitor=background_monitor,
            )

        log_event(
            {
                "kind": "index_status",
                "level": "info",
                "trace_id": trace_id,
                "active_backend": active_backend,
                "base_dir": base_dir,
                "base_dir_source": base_dir_source,
                "backend_freshness": backend_status.freshness,
                "backend_hints_usable": backend_status.hints_usable,
                "background_monitor_enabled": background_monitor.state == "active",
                "background_monitor_reason": background_monitor.reason,
            }
        )

        return payload.model_dump(mode="json", exclude={"error"})
