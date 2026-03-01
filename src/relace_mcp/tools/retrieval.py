import asyncio
import logging
import shutil
import time
import uuid
from typing import TYPE_CHECKING, Any

from ..config import RelaceConfig
from ..config.settings import AGENTIC_AUTO_SYNC, RETRIEVAL_BACKEND
from ..observability import get_trace_id, log_event, redact_value
from ..observability import tool_name as tool_name_ctx
from ..repo.backends import (
    ExternalCLIError,
    chunkhound_auto_reindex,
    chunkhound_search,
    codanna_auto_reindex,
    codanna_search,
    disable_backend,
    is_backend_disabled,
    schedule_bg_chunkhound_index,
    schedule_bg_codanna_full_index,
)
from ..repo.cloud.info import cloud_info_logic
from ..repo.cloud.search import cloud_search_logic
from ..repo.cloud.sync import cloud_sync_logic
from .search import FastAgenticSearchHarness

if TYPE_CHECKING:
    from ..clients.repo import RelaceRepoClient
    from ..clients.search import SearchLLMClient

logger = logging.getLogger(__name__)

_auto_backend_cache: dict[str, str] = {}
_reindex_locks: dict[tuple[str, str], asyncio.Lock] = {}


def _get_reindex_lock(base_dir: str, backend: str) -> asyncio.Lock:
    key = (base_dir, backend)
    lock = _reindex_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _reindex_locks[key] = lock
    return lock


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
    lines.append("Open these files FIRST (parallel view_file), then broaden exploration.")
    lines.append("</semantic_hints>")
    return "\n".join(lines)


async def agentic_retrieval_logic(
    repo_client: "RelaceRepoClient | None",
    search_client: "SearchLLMClient",
    config: RelaceConfig,
    base_dir: str,
    query: str,
    *,
    trace: bool = False,
) -> dict[str, Any]:
    """Two-stage retrieval: semantic hints + agentic exploration.

    Args:
        repo_client: Client for cloud semantic search (Relace backend only).
        search_client: Client for agentic search LLM.
        config: Relace configuration.
        base_dir: Repository base directory.
        query: Natural language query.
        trace: If True, collect per-turn trace data (turns_log) in the result.

    Returns:
        Dict with explanation, files, and metadata (same format as agentic_search).
    """
    # Fixed internal parameters
    branch = ""
    score_threshold = 0.3
    max_hints = 8
    token_limit = 10000

    trace_id = get_trace_id() if tool_name_ctx.get() else str(uuid.uuid4())[:8]
    logger.debug("[%s] Starting agentic retrieval", trace_id)

    # Resolve "auto" backend now that base_dir is known
    backend = _resolve_auto_backend(base_dir) if RETRIEVAL_BACKEND == "auto" else RETRIEVAL_BACKEND

    log_event(
        {
            "kind": "retrieval_backend_selected",
            "level": "info",
            "trace_id": trace_id,
            "base_dir": base_dir,
            "retrieval_backend": backend,
            "configured_backend": RETRIEVAL_BACKEND,
        }
    )

    warnings_list: list[str] = []
    cloud_results: list[dict[str, Any]] = []

    reindex_action: str | None = None
    reindex_t0 = time.perf_counter()

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
                    log_event(
                        {
                            "kind": "retrieval_auto_sync_error",
                            "level": "warning",
                            "trace_id": trace_id,
                            "backend": "relace",
                            "error": redact_value(str(sync_result.get("error")), 500),
                        }
                    )
                else:
                    logger.debug("[%s] Auto-sync completed successfully", trace_id)
                    log_event(
                        {
                            "kind": "retrieval_auto_sync_complete",
                            "level": "info",
                            "trace_id": trace_id,
                            "backend": "relace",
                        }
                    )
        except Exception as exc:
            warnings_list.append(f"Auto-sync error: {exc}")
            logger.warning("[%s] Auto-sync exception occurred, see warnings", trace_id)
            log_event(
                {
                    "kind": "retrieval_auto_sync_error",
                    "level": "warning",
                    "trace_id": trace_id,
                    "backend": "relace",
                    "error": redact_value(str(exc), 500),
                }
            )

    # Stage 0b: ChunkHound auto-reindex (HEAD + dirty-worktree staleness check).
    # Runs in a thread to avoid blocking the async event loop.
    if backend == "chunkhound" and not is_backend_disabled("chunkhound"):
        try:
            async with _get_reindex_lock(base_dir, "chunkhound"):
                reindex_result = await asyncio.to_thread(chunkhound_auto_reindex, base_dir)
            action = reindex_result.get("action", "unknown")
            reindex_action = action
            if action == "reindexed":
                logger.info(
                    "[%s] ChunkHound auto-reindex completed (%s)",
                    trace_id,
                    (reindex_result.get("old_head") or "?")[:8],
                )
                log_event(
                    {
                        "kind": "backend_auto_reindex_complete",
                        "level": "info",
                        "trace_id": trace_id,
                        "backend": "chunkhound",
                        "old_head": reindex_result.get("old_head"),
                        "new_head": reindex_result.get("new_head"),
                    }
                )
            elif action == "error":
                warnings_list.append(
                    f"ChunkHound auto-reindex failed: {reindex_result.get('message', 'unknown')}"
                )
                logger.warning(
                    "[%s] ChunkHound auto-reindex returned error: %s",
                    trace_id,
                    reindex_result.get("message"),
                )
                log_event(
                    {
                        "kind": "backend_auto_reindex_error",
                        "level": "warning",
                        "trace_id": trace_id,
                        "backend": "chunkhound",
                        "error": redact_value(str(reindex_result.get("message")), 500),
                    }
                )
            else:
                logger.debug("[%s] ChunkHound auto-reindex: %s", trace_id, action)
        except Exception as exc:
            warnings_list.append(f"ChunkHound auto-reindex failed: {exc}")
            logger.warning("[%s] ChunkHound auto-reindex failed: %s", trace_id, exc)
            log_event(
                {
                    "kind": "backend_auto_reindex_error",
                    "level": "warning",
                    "trace_id": trace_id,
                    "backend": "chunkhound",
                    "error": redact_value(str(exc), 500),
                }
            )

    # Stage 0c: Codanna auto-reindex (same staleness semantics as ChunkHound)
    if backend == "codanna" and not is_backend_disabled("codanna"):
        try:
            async with _get_reindex_lock(base_dir, "codanna"):
                reindex_result = await asyncio.to_thread(codanna_auto_reindex, base_dir)
            action = reindex_result.get("action", "unknown")
            reindex_action = action
            if action == "reindexed":
                logger.info(
                    "[%s] Codanna auto-reindex completed (%s)",
                    trace_id,
                    (reindex_result.get("old_head") or "?")[:8],
                )
                log_event(
                    {
                        "kind": "backend_auto_reindex_complete",
                        "level": "info",
                        "trace_id": trace_id,
                        "backend": "codanna",
                        "old_head": reindex_result.get("old_head"),
                        "new_head": reindex_result.get("new_head"),
                    }
                )
            elif action == "error":
                warnings_list.append(
                    f"Codanna auto-reindex failed: {reindex_result.get('message', 'unknown')}"
                )
                logger.warning(
                    "[%s] Codanna auto-reindex returned error: %s",
                    trace_id,
                    reindex_result.get("message"),
                )
                log_event(
                    {
                        "kind": "backend_auto_reindex_error",
                        "level": "warning",
                        "trace_id": trace_id,
                        "backend": "codanna",
                        "error": redact_value(str(reindex_result.get("message")), 500),
                    }
                )
            else:
                logger.debug("[%s] Codanna auto-reindex: %s", trace_id, action)
        except Exception as exc:
            warnings_list.append(f"Codanna auto-reindex failed: {exc}")
            logger.warning("[%s] Codanna auto-reindex failed: %s", trace_id, exc)
            log_event(
                {
                    "kind": "backend_auto_reindex_error",
                    "level": "warning",
                    "trace_id": trace_id,
                    "backend": "codanna",
                    "error": redact_value(str(exc), 500),
                }
            )

    reindex_latency_s = round(time.perf_counter() - reindex_t0, 3)

    # Stage 1: Semantic retrieval (Relace, Codanna, or ChunkHound)
    retrieval_t0 = time.perf_counter()
    if backend == "none":
        warnings_list.append("Semantic retrieval disabled (MCP_RETRIEVAL_BACKEND=none).")
    elif backend in ("codanna", "chunkhound"):
        if is_backend_disabled(backend):
            warnings_list.append(
                f"{backend} backend disabled for this session. Proceeding without hints."
            )
            log_event(
                {
                    "kind": "retrieval_hints_skipped",
                    "level": "warning",
                    "trace_id": trace_id,
                    "backend": backend,
                    "reason": "backend_disabled",
                }
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
                log_event(
                    {
                        "kind": "retrieval_hints_complete",
                        "level": "info",
                        "trace_id": trace_id,
                        "backend": backend,
                        "results_count": len(cloud_results) if cloud_results else 0,
                    }
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
                        schedule_bg_codanna_full_index(base_dir)
                warnings_list.append(f"{exc.backend} retrieval unavailable ({exc.kind}): {exc}")
                logger.warning(
                    "[%s] %s backend error (%s): %s", trace_id, exc.backend, exc.kind, exc
                )
                log_event(
                    {
                        "kind": "retrieval_hints_error",
                        "level": "warning",
                        "trace_id": trace_id,
                        "backend": exc.backend,
                        "error_kind": exc.kind,
                        "error": redact_value(str(exc), 500),
                        "command": exc.command,
                    }
                )
            except Exception as exc:
                warnings_list.append(f"{backend} search crashed: {exc}. Proceeding without hints.")
                logger.exception("[%s] %s unexpected exception", trace_id, backend)
                log_event(
                    {
                        "kind": "retrieval_hints_error",
                        "level": "warning",
                        "trace_id": trace_id,
                        "backend": backend,
                        "error_kind": type(exc).__name__,
                        "error": redact_value(str(exc), 500),
                    }
                )
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

    retrieval_latency_s = round(time.perf_counter() - retrieval_t0, 3)

    # Stage 2: Build semantic hints section
    hints_section = build_semantic_hints_section(cloud_results, max_hints)

    # Stage 3: Run agentic search in retrieval mode (retrieval prompt, hints injected)
    from dataclasses import replace
    from pathlib import Path

    from ..lsp.languages import get_lsp_languages

    effective_config = replace(config, base_dir=base_dir)
    lsp_languages = get_lsp_languages(Path(base_dir))

    harness = FastAgenticSearchHarness(
        effective_config,
        search_client,
        lsp_languages=lsp_languages,
        retrieval=True,
        trace=trace,
    )
    result = await harness.run_async(
        query=query,
        semantic_hints_section=hints_section,
        trace_id=trace_id,
    )

    # Add metadata
    result["trace_id"] = trace_id
    result["cloud_hints_used"] = len(cloud_results[:max_hints]) if cloud_results else 0
    result["retrieval_backend"] = backend
    result["reindex_action"] = reindex_action
    result["reindex_latency_s"] = reindex_latency_s
    result["retrieval_latency_s"] = retrieval_latency_s
    if warnings_list:
        result["warnings"] = warnings_list

    return result
