import logging
import shutil
import uuid
from typing import Any

from ..clients import RelaceRepoClient, SearchLLMClient
from ..config import RETRIEVAL_USER_PROMPT_TEMPLATE, RelaceConfig
from ..config.settings import AGENTIC_AUTO_SYNC, RETRIEVAL_BACKEND
from ..repo.cloud import cloud_info_logic, cloud_search_logic, cloud_sync_logic
from ..repo.local import (
    ExternalCLIError,
    chunkhound_search,
    codanna_search,
    disable_backend,
    is_backend_disabled,
    schedule_bg_chunkhound_index,
    schedule_bg_codanna_index,
)
from .search import FastAgenticSearchHarness

logger = logging.getLogger(__name__)

_auto_backend_cache: dict[str, str] = {}


def _resolve_auto_backend(base_dir: str) -> str:
    cached = _auto_backend_cache.get(base_dir)
    if cached and not is_backend_disabled(cached):
        return cached

    for name in ("codanna", "chunkhound"):
        if shutil.which(name) and not is_backend_disabled(name):
            logger.info("Auto-detected retrieval backend: %s", name)
            _auto_backend_cache[base_dir] = name
            return name

    logger.info("No usable local retrieval backend found, using relace")
    _auto_backend_cache[base_dir] = "relace"
    return "relace"


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
        raw_score = r.get("score", 0.0)
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = 0.0
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
        Dict with explanation, files, and metadata (same format as agentic_search).
    """
    # Fixed internal parameters
    branch = ""
    score_threshold = 0.3
    max_hints = 8
    token_limit = 10000

    trace_id = str(uuid.uuid4())[:8]
    logger.debug("[%s] Starting agentic retrieval", trace_id)

    # Resolve "auto" backend now that base_dir is known
    backend = _resolve_auto_backend(base_dir) if RETRIEVAL_BACKEND == "auto" else RETRIEVAL_BACKEND

    warnings_list: list[str] = []
    cloud_results: list[dict[str, Any]] = []

    # Stage 0a: Auto-sync if enabled and needed (Relace backend only)
    if AGENTIC_AUTO_SYNC and backend == "relace" and repo_client is not None:
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

    # Stage 0b: Schedule background ChunkHound incremental scan (fire-and-forget).
    # ChunkHound uses xxHash3-64 checksums; only modified files are re-processed.
    # Non-blocking: search proceeds immediately with the current index state.
    if backend == "chunkhound" and not is_backend_disabled("chunkhound"):
        schedule_bg_chunkhound_index(base_dir)
        logger.debug("[%s] ChunkHound background index scheduled", trace_id)

    # Stage 0c: Schedule background Codanna reindex (fire-and-forget).
    if backend == "codanna" and not is_backend_disabled("codanna"):
        schedule_bg_codanna_index(base_dir, base_dir)
        logger.debug("[%s] Codanna background index scheduled", trace_id)

    # Stage 1: Semantic retrieval (Relace, Codanna, or ChunkHound)
    if backend == "none":
        warnings_list.append("Semantic retrieval disabled (MCP_RETRIEVAL_BACKEND=none).")
    elif backend in ("codanna", "chunkhound"):
        if is_backend_disabled(backend):
            warnings_list.append(
                f"{backend} backend disabled for this session. Proceeding without hints."
            )
        else:
            search_fn = chunkhound_search if backend == "chunkhound" else codanna_search
            try:
                cloud_results = search_fn(
                    query,
                    base_dir=base_dir,
                    limit=max_hints,
                    threshold=score_threshold,
                    allow_auto_index=False,
                )
                if not cloud_results:
                    warnings_list.append(
                        f"{backend} returned no results. Proceeding without hints."
                    )
                else:
                    logger.debug(
                        "[%s] %s returned %d results, using top %d as hints",
                        trace_id,
                        backend,
                        len(cloud_results),
                        min(len(cloud_results), max_hints),
                    )
            except ExternalCLIError as exc:
                if exc.kind == "cli_not_found":
                    disable_backend(exc.backend, f"{exc.kind}: {exc}")
                elif exc.kind == "index_missing":
                    if backend == "chunkhound":
                        schedule_bg_chunkhound_index(base_dir)
                    else:
                        schedule_bg_codanna_index(base_dir, base_dir)
                warnings_list.append(f"{exc.backend} retrieval unavailable ({exc.kind}): {exc}")
                logger.warning(
                    "[%s] %s backend error (%s): %s", trace_id, exc.backend, exc.kind, exc
                )
            except Exception as exc:
                warnings_list.append(f"{backend} search crashed: {exc}. Proceeding without hints.")
                logger.exception("[%s] %s unexpected exception", trace_id, backend)
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

    from ..lsp.languages import get_lsp_languages

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
