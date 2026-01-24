import logging
import uuid
from typing import Any

from ...clients import RelaceRepoClient, SearchLLMClient
from ...config import RETRIEVAL_USER_PROMPT_TEMPLATE, RelaceConfig
from ...config.settings import AGENTIC_AUTO_SYNC, RETRIEVAL_BACKEND
from ..search import FastAgenticSearchHarness
from ._local_backend import chunkhound_search, codanna_search
from .info import cloud_info_logic
from .search import cloud_search_logic
from .sync import cloud_sync_logic

logger = logging.getLogger(__name__)


def build_semantic_hints_section(cloud_results: list[dict[str, Any]], max_hints: int = 8) -> str:
    if not cloud_results:
        return ""

    hints = cloud_results[:max_hints]
    lines = [
        "<semantic_hints>",
        "Files identified by semantic retrieval (prioritize these):",
    ]
    for r in hints:
        file_path = r.get("filename") or r.get("file", "unknown")
        score = r.get("score", 0.0)
        lines.append(f"- {file_path} (score: {score:.2f})")
    lines.append("Validate with grep/view before reporting.")
    lines.append("</semantic_hints>")
    return "\n".join(lines)


async def agentic_retrieval_logic(
    repo_client: RelaceRepoClient | None,
    search_client: SearchLLMClient,
    config: RelaceConfig,
    base_dir: str,
    query: str,
) -> dict[str, Any]:
    """Two-stage retrieval: semantic hints + agentic exploration.

    Args:
        repo_client: Client for cloud semantic search (Relace backend only).
        search_client: Client for agentic search LLM.
        config: Relace configuration.
        base_dir: Repository base directory.
        query: Natural language query.

    Returns:
        Dict with explanation, files, and metadata (same format as fast_search).
    """
    # Fixed internal parameters
    branch = ""
    score_threshold = 0.3
    max_hints = 8
    token_limit = 10000

    trace_id = str(uuid.uuid4())[:8]
    logger.debug("[%s] Starting agentic retrieval", trace_id)

    warnings_list: list[str] = []
    cloud_results: list[dict[str, Any]] = []

    # Stage 0: Auto-sync if enabled and needed (Relace backend only)
    if AGENTIC_AUTO_SYNC and RETRIEVAL_BACKEND == "relace" and repo_client is not None:
        try:
            info = cloud_info_logic(repo_client, base_dir)
            if info.get("status", {}).get("needs_sync"):
                logger.debug("[%s] Auto-sync triggered (needs_sync=True)", trace_id)
                sync_result = cloud_sync_logic(repo_client, base_dir)
                if sync_result.get("error"):
                    warnings_list.append(f"Auto-sync failed: {sync_result['error']}")
                    logger.warning("[%s] Auto-sync failed, see warnings", trace_id)
                else:
                    logger.debug("[%s] Auto-sync completed successfully", trace_id)
        except Exception as exc:
            warnings_list.append(f"Auto-sync error: {exc}")
            logger.warning("[%s] Auto-sync exception occurred, see warnings", trace_id)

    # Stage 1: Semantic retrieval (Relace, Codanna, or ChunkHound)
    if RETRIEVAL_BACKEND == "none":
        warnings_list.append("Semantic retrieval disabled (MCP_RETRIEVAL_BACKEND=none).")
    elif RETRIEVAL_BACKEND == "codanna":
        try:
            cloud_results = codanna_search(
                query,
                base_dir=base_dir,
                limit=max_hints,
                threshold=score_threshold,
            )
            if not cloud_results:
                warnings_list.append("Codanna returned no results. Proceeding without hints.")
            else:
                logger.debug(
                    "[%s] Codanna returned %d results, using top %d as hints",
                    trace_id,
                    len(cloud_results),
                    min(len(cloud_results), max_hints),
                )
        except Exception as exc:
            warnings_list.append(f"Codanna search error: {exc}. Proceeding without hints.")
            logger.warning("[%s] Codanna search exception: %s", trace_id, exc)
    elif RETRIEVAL_BACKEND == "chunkhound":
        try:
            cloud_results = chunkhound_search(
                query,
                base_dir=base_dir,
                limit=max_hints,
                threshold=score_threshold,
            )
            if not cloud_results:
                warnings_list.append("ChunkHound returned no results. Proceeding without hints.")
            else:
                logger.debug(
                    "[%s] ChunkHound returned %d results, using top %d as hints",
                    trace_id,
                    len(cloud_results),
                    min(len(cloud_results), max_hints),
                )
        except Exception as exc:
            warnings_list.append(f"ChunkHound search error: {exc}. Proceeding without hints.")
            logger.warning("[%s] ChunkHound search exception: %s", trace_id, exc)
    else:
        if repo_client is None:
            warnings_list.append(
                "Relace semantic retrieval unavailable (RELACE_CLOUD_TOOLS=false). Proceeding without hints."
            )
        else:
            try:
                cloud_result = cloud_search_logic(
                    repo_client,
                    base_dir,
                    query,
                    branch=branch,
                    score_threshold=score_threshold,
                    token_limit=token_limit,
                )

                if cloud_result.get("error"):
                    warnings_list.append(
                        f"Cloud search failed: {cloud_result['error']}. Proceeding without hints."
                    )
                    logger.warning("[%s] Cloud search failed, see warnings", trace_id)
                else:
                    cloud_results = cloud_result.get("results", [])
                    if not cloud_results:
                        warnings_list.append(
                            "Cloud search returned no results. Proceeding without hints."
                        )
                    else:
                        logger.debug(
                            "[%s] Cloud search returned %d results, using top %d as hints",
                            trace_id,
                            len(cloud_results),
                            min(len(cloud_results), max_hints),
                        )
            except Exception as exc:
                warnings_list.append(f"Cloud search error: {exc}. Proceeding without hints.")
                logger.warning("[%s] Cloud search exception: %s", trace_id, exc)

    # Stage 2: Build augmented prompt
    hints_section = build_semantic_hints_section(cloud_results, max_hints)
    user_prompt = RETRIEVAL_USER_PROMPT_TEMPLATE.format(
        query=query,
        semantic_hints_section=hints_section,
    )

    # Stage 3: Run agentic search with custom prompt
    from dataclasses import replace
    from pathlib import Path

    from ...lsp.languages import get_lsp_languages

    effective_config = replace(config, base_dir=base_dir)
    lsp_languages = get_lsp_languages(Path(base_dir))

    harness = FastAgenticSearchHarness(
        effective_config,
        search_client,
        lsp_languages=lsp_languages,
        user_prompt_override=user_prompt,
    )
    result = await harness.run_async(query=query)

    # Add metadata
    result["trace_id"] = trace_id
    result["cloud_hints_used"] = len(cloud_results[:max_hints]) if cloud_results else 0
    if warnings_list:
        result["warnings"] = warnings_list

    return result
