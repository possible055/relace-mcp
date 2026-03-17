# pyright: reportUnusedFunction=false
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.server.context import Context
from pydantic import Field

from ..config import resolve_base_dir
from ..config import settings as _settings
from ..lsp.languages import get_lsp_languages
from ..observability import get_trace_id
from ..search import FastAgenticSearchHarness
from ..search.retrieval import agentic_retrieval_logic
from ._registry import ToolRegistryDeps


def register_search_tools(mcp: FastMCP, deps: ToolRegistryDeps) -> None:
    @mcp.tool(
        timeout=600.0,
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
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
        await ctx.info(f"Searching: {query[:100]}")

        base_dir, _ = await resolve_base_dir(deps.config.base_dir, ctx)
        await deps.ensure_encoding(ctx, base_dir)

        lsp_languages = get_lsp_languages(Path(base_dir))
        effective_config = replace(deps.config, base_dir=base_dir)

        async def _on_progress(turn: int, total: int) -> None:
            await ctx.report_progress(
                progress=turn, total=total, message=f"agentic_search turn {turn}/{total}"
            )

        result = await FastAgenticSearchHarness(
            effective_config, deps.clients.get_search(), lsp_languages=lsp_languages
        ).run_async(query=query, trace_id=get_trace_id(), on_progress=_on_progress)
        files_found = len(result.get("files", {}))
        await ctx.debug(f"Search found {files_found} files")
        return result

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
            if ctx is not None:
                await ctx.info(f"Retrieval: {query[:100]}")

            base_dir, _ = await resolve_base_dir(deps.config.base_dir, ctx)
            await deps.ensure_encoding(ctx, base_dir)

            async def _on_progress(turn: int, total: int) -> None:
                if ctx is not None:
                    await ctx.report_progress(
                        progress=turn,
                        total=total,
                        message=f"agentic_retrieval turn {turn}/{total}",
                    )

            result = await agentic_retrieval_logic(
                deps.clients.get_repo(),
                deps.clients.get_search(),
                deps.config,
                base_dir,
                query,
                on_progress=_on_progress,
            )
            if ctx is not None:
                files_found = len(result.get("files", {}))
                await ctx.debug(f"Retrieval found {files_found} files")
            return result
