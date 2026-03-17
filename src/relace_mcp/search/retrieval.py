import asyncio
import logging
import shutil
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from ..config import RelaceConfig
from ..config import settings as _settings
from ..observability import get_trace_id, log_event, redact_value
from ..observability import tool_name as tool_name_ctx
from ..repo.backends import (
    ExternalCLIError,
    chunkhound_search,
    codanna_search,
    disable_backend,
    is_backend_disabled,
    schedule_bg_chunkhound_index,
    schedule_bg_codanna_full_index,
)
from ..repo.cloud.search import cloud_search_logic
from ..repo.freshness import classify_cloud_index_freshness, classify_local_index_freshness
from .harness import FastAgenticSearchHarness

if TYPE_CHECKING:
    from ..clients.repo import RelaceRepoClient
    from ..clients.search import SearchLLMClient

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


def _backend_display_name(backend: str) -> str:
    if backend == "chunkhound":
        return "ChunkHound"
    if backend == "codanna":
        return "Codanna"
    if backend == "relace":
        return "Relace"
    return backend


def _append_warning(warnings_list: list[str], message: str) -> None:
    if message not in warnings_list:
        warnings_list.append(message)


def _should_use_semantic_hints(policy: str, freshness: str) -> bool:
    if freshness == "missing":
        return False
    if policy == "strict":
        return freshness == "fresh"
    return freshness in {"fresh", "stale", "unknown"}


def _schedule_local_refresh(base_dir: str, backend: str) -> bool:
    if backend == "chunkhound":
        schedule_bg_chunkhound_index(base_dir)
        return True
    if backend == "codanna":
        schedule_bg_codanna_full_index(base_dir)
        return True
    return False


def _compact_semantic_hints(
    semantic_results: list[dict[str, Any]], max_hints: int
) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for result in semantic_results[:max_hints]:
        filename = result.get("filename") or result.get("file") or ""
        if not isinstance(filename, str) or not filename.strip():
            continue
        raw_score = result.get("score", 0.0)
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = 0.0
        hints.append({"filename": filename, "score": score})
    return hints


def build_semantic_hints_section(semantic_results: list[dict[str, Any]], max_hints: int = 8) -> str:
    if not semantic_results:
        return ""

    hints = _compact_semantic_hints(semantic_results, max_hints)
    lines = [
        "<semantic_hints>",
        "Files identified by semantic retrieval (prioritize these):",
    ]
    for result in hints:
        file_path = result.get("filename") or result.get("file", "unknown")
        raw_score = result.get("score", 0.0)
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
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Two-stage retrieval: semantic hints + agentic exploration.

    Args:
        repo_client: Client for cloud semantic search (Relace backend only).
        search_client: Client for agentic search LLM.
        config: Relace configuration.
        base_dir: Repository base directory.
        query: Natural language query.
        trace: If True, collect per-turn trace data (turns_log) in the result.
        on_progress: Optional async callback receiving (current_turn, max_turns).

    Returns:
        Dict with explanation, files, and metadata (same format as agentic_search).
    """
    branch = ""
    score_threshold = 0.3
    max_hints = 8
    token_limit = 10000

    trace_id = get_trace_id() if tool_name_ctx.get() else str(uuid.uuid4())[:8]
    logger.debug("[%s] Starting agentic retrieval", trace_id)

    backend = (
        _resolve_auto_backend(base_dir)
        if _settings.RETRIEVAL_BACKEND == "auto"
        else _settings.RETRIEVAL_BACKEND
    )
    hint_policy = _settings.RETRIEVAL_HINT_POLICY

    log_event(
        {
            "kind": "retrieval_backend_selected",
            "level": "info",
            "trace_id": trace_id,
            "base_dir": base_dir,
            "retrieval_backend": backend,
            "configured_backend": _settings.RETRIEVAL_BACKEND,
            "hint_policy": hint_policy,
        }
    )

    warnings_list: list[str] = []
    semantic_results: list[dict[str, Any]] = []
    hints_index_freshness = "unknown"
    background_refresh_scheduled = False
    reindex_action: str | None = None

    retrieval_t0 = time.perf_counter()
    if backend == "none":
        hints_index_freshness = "missing"
        _append_warning(
            warnings_list,
            "Semantic retrieval disabled (MCP_RETRIEVAL_BACKEND=none).",
        )
    elif backend in ("codanna", "chunkhound"):
        backend_name = _backend_display_name(backend)
        if is_backend_disabled(backend):
            _append_warning(
                warnings_list,
                f"{backend_name} backend disabled for this session. Proceeding without hints.",
            )
            log_event(
                {
                    "kind": "retrieval_hints_skipped",
                    "level": "warning",
                    "trace_id": trace_id,
                    "backend": backend,
                    "reason": "backend_disabled",
                    "hint_policy": hint_policy,
                }
            )
        elif not shutil.which(backend):
            disable_backend(backend, f"{backend} CLI not found in PATH")
            _append_warning(
                warnings_list,
                f"{backend_name} CLI not found in PATH. Proceeding without hints.",
            )
        else:
            freshness = classify_local_index_freshness(base_dir, backend)
            hints_index_freshness = freshness.freshness

            if freshness.refresh_recommended and _schedule_local_refresh(base_dir, backend):
                background_refresh_scheduled = True
                reindex_action = "scheduled_background_refresh"

            if not _should_use_semantic_hints(hint_policy, freshness.freshness):
                if freshness.freshness == "missing":
                    message = (
                        f"{backend_name} index missing. Proceeding without hints"
                        f"{' and scheduled background refresh.' if background_refresh_scheduled else '.'}"
                    )
                else:
                    message = (
                        f"Skipping {freshness.freshness} {backend_name} semantic hints because "
                        f"MCP_RETRIEVAL_HINT_POLICY={hint_policy}."
                    )
                    if background_refresh_scheduled:
                        message += " Scheduled background refresh."
                _append_warning(warnings_list, message)
                log_event(
                    {
                        "kind": "retrieval_hints_skipped",
                        "level": "warning",
                        "trace_id": trace_id,
                        "backend": backend,
                        "reason": freshness.reason or freshness.freshness,
                        "freshness": freshness.freshness,
                        "hint_policy": hint_policy,
                    }
                )
            else:
                if freshness.freshness == "stale":
                    message = f"Using stale {backend_name} semantic hints."
                    if background_refresh_scheduled:
                        message += " Scheduled background refresh."
                    _append_warning(warnings_list, message)
                elif freshness.freshness == "unknown":
                    _append_warning(
                        warnings_list,
                        f"{backend_name} index freshness is unknown; using available semantic hints.",
                    )

                search_fn = chunkhound_search if backend == "chunkhound" else codanna_search
                try:
                    semantic_results = await asyncio.to_thread(
                        search_fn,
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
                            "results_count": len(semantic_results),
                            "freshness": hints_index_freshness,
                            "hint_policy": hint_policy,
                        }
                    )
                    if not semantic_results:
                        _append_warning(
                            warnings_list,
                            f"{backend_name} returned no results. Proceeding without hints.",
                        )
                except ExternalCLIError as exc:
                    if exc.kind == "cli_not_found":
                        disable_backend(exc.backend, f"{exc.kind}: {exc}")
                    elif exc.kind == "index_missing":
                        hints_index_freshness = "missing"
                        if _schedule_local_refresh(base_dir, backend):
                            background_refresh_scheduled = True
                            reindex_action = "scheduled_background_refresh"
                    _append_warning(
                        warnings_list,
                        f"{_backend_display_name(exc.backend)} retrieval unavailable ({exc.kind}): {exc}",
                    )
                    logger.warning(
                        "[%s] %s backend error (%s): %s",
                        trace_id,
                        exc.backend,
                        exc.kind,
                        exc,
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
                            "hint_policy": hint_policy,
                        }
                    )
                except Exception as exc:
                    _append_warning(
                        warnings_list,
                        f"{backend_name} search crashed: {exc}. Proceeding without hints.",
                    )
                    logger.exception("[%s] %s unexpected exception", trace_id, backend)
                    log_event(
                        {
                            "kind": "retrieval_hints_error",
                            "level": "warning",
                            "trace_id": trace_id,
                            "backend": backend,
                            "error_kind": type(exc).__name__,
                            "error": redact_value(str(exc), 500),
                            "hint_policy": hint_policy,
                        }
                    )
    else:
        if repo_client is None:
            hints_index_freshness = "missing"
            _append_warning(
                warnings_list,
                "Relace semantic retrieval unavailable (RELACE_CLOUD_TOOLS=false). Proceeding without hints.",
            )
        else:
            freshness = classify_cloud_index_freshness(base_dir)
            hints_index_freshness = freshness.freshness

            if not _should_use_semantic_hints(hint_policy, freshness.freshness):
                if freshness.freshness == "missing":
                    message = (
                        "No synced Relace index found. Proceeding without hints. "
                        "Run cloud_sync() to enable semantic hints."
                    )
                else:
                    message = (
                        f"Skipping {freshness.freshness} Relace semantic hints because "
                        f"MCP_RETRIEVAL_HINT_POLICY={hint_policy}. Run cloud_sync() to refresh."
                    )
                _append_warning(warnings_list, message)
                log_event(
                    {
                        "kind": "retrieval_hints_skipped",
                        "level": "warning",
                        "trace_id": trace_id,
                        "backend": "relace",
                        "reason": freshness.reason or freshness.freshness,
                        "freshness": freshness.freshness,
                        "hint_policy": hint_policy,
                    }
                )
            else:
                if freshness.freshness == "stale":
                    _append_warning(
                        warnings_list,
                        "Using stale Relace semantic hints from the last synced revision. "
                        "Run cloud_sync() to refresh.",
                    )
                elif freshness.freshness == "unknown":
                    _append_warning(
                        warnings_list,
                        "Relace sync freshness is unknown; using the last synced semantic hints.",
                    )

                try:
                    cloud_result = await asyncio.to_thread(
                        cloud_search_logic,
                        repo_client,
                        base_dir,
                        query,
                        branch=branch,
                        score_threshold=score_threshold,
                        token_limit=token_limit,
                    )
                    for warning in cloud_result.get("warnings", []):
                        _append_warning(warnings_list, warning)

                    if cloud_result.get("error"):
                        _append_warning(
                            warnings_list,
                            f"Cloud search failed: {cloud_result['error']}. Proceeding without hints.",
                        )
                        logger.warning("[%s] Cloud search failed, see warnings", trace_id)
                    else:
                        semantic_results = cloud_result.get("results", [])
                        log_event(
                            {
                                "kind": "retrieval_hints_complete",
                                "level": "info",
                                "trace_id": trace_id,
                                "backend": "relace",
                                "results_count": len(semantic_results),
                                "freshness": hints_index_freshness,
                                "hint_policy": hint_policy,
                            }
                        )
                        if not semantic_results:
                            _append_warning(
                                warnings_list,
                                "Cloud search returned no results. Proceeding without hints.",
                            )
                except Exception as exc:
                    _append_warning(
                        warnings_list,
                        f"Cloud search error: {exc}. Proceeding without hints.",
                    )
                    logger.warning("[%s] Cloud search exception: %s", trace_id, exc)
                    log_event(
                        {
                            "kind": "retrieval_hints_error",
                            "level": "warning",
                            "trace_id": trace_id,
                            "backend": "relace",
                            "error_kind": type(exc).__name__,
                            "error": redact_value(str(exc), 500),
                            "hint_policy": hint_policy,
                        }
                    )

    retrieval_latency_s = round(time.perf_counter() - retrieval_t0, 3)

    hints_section = build_semantic_hints_section(semantic_results, max_hints)

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
        on_progress=on_progress,
    )

    compact_semantic_hints = _compact_semantic_hints(semantic_results, max_hints)

    result["trace_id"] = trace_id
    result["semantic_hints_used"] = len(compact_semantic_hints)
    result["semantic_hints"] = compact_semantic_hints
    result["retrieval_backend"] = backend
    result["hint_policy"] = hint_policy
    result["hints_index_freshness"] = hints_index_freshness
    result["background_refresh_scheduled"] = background_refresh_scheduled
    result["reindex_action"] = reindex_action
    result["retrieval_latency_s"] = retrieval_latency_s
    if warnings_list:
        result["warnings"] = warnings_list

    return result
