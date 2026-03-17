from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.server.context import Context
from pydantic import Field

from ..apply import apply_file_logic
from ..config import resolve_base_dir
from ._registry import ToolRegistryDeps


def register_apply_tools(mcp: FastMCP, deps: ToolRegistryDeps) -> None:
    @mcp.tool(
        timeout=300.0,
        annotations={
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": False,
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
                "modified, plus placeholder comments for unchanged parts when useful for larger scoped edits: "
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
        Truncation markers are recommended for larger scoped edits but not required.
        Markdown files keep fenced code blocks verbatim; outer fence stripping is skipped
        for .md/.mdx targets.

        On error, the response includes a code field:
        - NEEDS_MORE_CONTEXT: merge model could not locate the target -
          add 1-2 unique anchor lines from immediately around the edit location.
        - APPLY_NOOP: merge returned an identical file even though the snippet contained
          explicit remove directives or concrete new lines not present in the original.
        - BLAST_RADIUS_EXCEEDED: edit scope too large - split into smaller edits.
        - MARKER_LEAKAGE: placeholder marker text leaked into merged output (treated as literal text).
        - TRUNCATION_DETECTED: merged output shrank drastically and no explicit remove
          directive was provided.

        On success: {status: "ok", diff: str | None (unified diff, None for new files or no-op)}.

        Do NOT use this tool to delete files or clear file contents.
        Use a dedicated file management tool for those operations.
        """
        base_dir, _ = await resolve_base_dir(deps.config.base_dir, ctx)
        await deps.ensure_encoding(ctx, base_dir)
        if ctx is not None:
            await ctx.info(f"Applying to {path}")

        async def _on_progress(progress: int, total: int, message: str) -> None:
            if ctx is not None:
                await ctx.report_progress(progress=progress, total=total, message=message)

        result = await apply_file_logic(
            backend=deps.clients.get_apply(),
            file_path=path,
            edit_snippet=edit_snippet,
            instruction=instruction or None,
            base_dir=base_dir,
            extra_paths=deps.config.extra_paths,
            on_progress=_on_progress,
        )
        if ctx is not None and result and result.get("status") == "ok":
            diff_preview = (result.get("diff") or "")[:200]
            await ctx.debug(f"Edit applied: {diff_preview}...")
        return result
