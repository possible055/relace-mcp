import asyncio
import logging
import shutil
import time
import uuid
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from ..config import RelaceConfig, load_prompt_file
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
from ..utils import resolve_repo_path
from .harness import FastAgenticSearchHarness

if TYPE_CHECKING:
    from ..clients.repo import RelaceRepoClient
    from ..clients.search import SearchLLMClient

logger = logging.getLogger(__name__)

_auto_backend_cache: dict[str, str] = {}


async def _run_blocking_retrieval_call(
    func: Callable[..., Any],
    /,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Run a blocking retrieval helper in a short-lived worker thread.

    Using an explicit executor avoids leaving the event loop's default executor
    alive across tests and short-lived CLI invocations.
    """
    loop = asyncio.get_running_loop()

    def _call() -> Any:
        return func(*args, **kwargs)

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="relace-retrieval") as executor:
        return await loop.run_in_executor(executor, _call)


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


def _hint_limit_for_freshness(max_hints: int, freshness: str) -> int:
    if freshness in {"stale", "unknown"}:
        return min(max_hints, 4)
    if freshness == "missing":
        return 0
    return max_hints


def _normalize_hint_filename(filename: str, base_dir: str) -> str | None:
    normalized = filename.strip()
    if not normalized or any(ch in normalized for ch in ("\n", "\r", "<", ">")):
        return None

    try:
        resolved = resolve_repo_path(
            normalized,
            base_dir,
            require_within_base_dir=True,
        )
    except ValueError:
        return None

    base_path = Path(base_dir).resolve()
    resolved_path = Path(resolved)
    try:
        rel_path = resolved_path.relative_to(base_path).as_posix()
    except ValueError:
        return None

    if not rel_path or rel_path == ".":
        return None
    return f"/repo/{rel_path}"


def _compact_semantic_hints(
    semantic_results: list[dict[str, Any]], max_hints: int, *, base_dir: str | None = None
) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for result in semantic_results[:max_hints]:
        filename = result.get("filename") or result.get("file") or ""
        if not isinstance(filename, str) or not filename.strip():
            continue
        if base_dir is not None:
            filename = _normalize_hint_filename(filename, base_dir)
            if filename is None:
                continue
        raw_score = result.get("score", 0.0)
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = 0.0
        hints.append({"filename": filename, "score": score})
    return hints


def _format_semantic_hints_block(
    semantic_results: list[dict[str, Any]],
    max_hints: int = 8,
    *,
    base_dir: str | None = None,
    block_template: str,
) -> str:
    if not semantic_results:
        return ""

    hints = _compact_semantic_hints(semantic_results, max_hints, base_dir=base_dir)
    if not hints:
        return ""
    hints_list = "\n".join(f"- {h['filename']} (score: {h['score']:.2f})" for h in hints)
    return block_template.strip().format(hints_list=hints_list)


def _build_first_turn_retrieval_guidance(
    semantic_results: list[dict[str, Any]],
    *,
    freshness: str,
    max_hints: int,
    base_dir: str,
    prompts: dict[str, Any],
) -> str:
    freshness_descriptions = cast(dict[str, str], prompts["freshness_descriptions"])
    freshness_description = freshness_descriptions.get(freshness, freshness_descriptions["missing"])
    semantic_hints_block_template = cast(str, prompts["semantic_hints_block_template"])
    no_hints_fallback = cast(str, prompts["no_hints_fallback"])
    first_turn_guidance_template = cast(str, prompts["first_turn_guidance_template"])

    hint_limit = _hint_limit_for_freshness(max_hints, freshness)
    hints_block = _format_semantic_hints_block(
        semantic_results,
        hint_limit,
        base_dir=base_dir,
        block_template=semantic_hints_block_template,
    )
    semantic_hints_block = hints_block if hints_block else no_hints_fallback.strip()

    return first_turn_guidance_template.strip().format(
        freshness_description=freshness_description,
        semantic_hints_block=semantic_hints_block,
    )


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
                    semantic_results = await _run_blocking_retrieval_call(
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
                    cloud_result = await _run_blocking_retrieval_call(
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

    backend_kind = "relace" if search_client.api_compat == _settings.RELACE_PROVIDER else "openai"
    prompts = load_prompt_file(f"retrieval_{backend_kind}")

    first_turn_guidance = _build_first_turn_retrieval_guidance(
        semantic_results,
        freshness=hints_index_freshness,
        max_hints=max_hints,
        base_dir=base_dir,
        prompts=prompts,
    )

    from dataclasses import replace

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
        first_turn_guidance=first_turn_guidance,
        trace_id=trace_id,
        on_progress=on_progress,
    )

    compact_semantic_hints = _compact_semantic_hints(
        semantic_results,
        _hint_limit_for_freshness(max_hints, hints_index_freshness),
        base_dir=base_dir,
    )

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
