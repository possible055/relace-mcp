import json

from fastmcp import FastMCP
from fastmcp.server.context import Context

from ..config import resolve_base_dir
from ..config import settings as _settings
from ..repo.core.state import get_repo_identity, load_sync_state
from ._registry import ToolRegistryDeps


def register_resources(mcp: FastMCP, deps: ToolRegistryDeps) -> None:
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
            base_dir, _ = await resolve_base_dir(deps.config.base_dir, ctx)
        except RuntimeError:
            return json.dumps(
                {
                    "synced": False,
                    "error": "base_dir not configured",
                    "message": "Set MCP_BASE_DIR or use MCP Roots to enable cloud status",
                }
            )

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
