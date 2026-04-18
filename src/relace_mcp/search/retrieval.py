import asyncio
import logging
import shutil
import time
import uuid
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
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
from ..repo.freshness import (
    classify_cloud_index_freshness,
    classify_local_index_freshness,
    semantic_hints_usable_for_policy,
)
from ..utils import resolve_repo_path
from .harness import FastAgenticSearchHarness
from .prompt_messages import format_hints_list, render_retrieval_guidance_message

if TYPE_CHECKING:
    from ..clients.repo import RelaceRepoClient
    from ..clients.search import SearchLLMClient

logger = logging.getLogger(__name__)
_background_retrieval_tasks: set[asyncio.Task[Any]] = set()


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


def _track_background_task(task: asyncio.Task[Any]) -> asyncio.Task[Any]:
    _background_retrieval_tasks.add(task)
    task.add_done_callback(_background_retrieval_tasks.discard)
    return task


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
    except (ValueError, OSError):
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


def _resolve_retrieval_format_kwargs(
    compact_hints: list[dict[str, Any]],
    *,
    freshness: str,
    prompts: dict[str, Any],
) -> dict[str, str]:
    """Resolve freshness_message and hints_list for retrieval guidance rendering."""
    freshness_messages = cast(dict[str, str], prompts["freshness_messages"])
    msg_key = "missing" if freshness == "missing" else "available"
    return {
        "freshness_message": freshness_messages[msg_key],
        "hints_list": format_hints_list(compact_hints),
    }


@dataclass
class RetrievalPreflight:
    should_run: bool
    hints_index_freshness: str
    warnings_list: list[str] = field(default_factory=list)
    background_refresh_scheduled: bool = False
    reindex_action: str | None = None


@dataclass
class RetrievalTaskResult:
    semantic_results: list[dict[str, Any]] = field(default_factory=list)
    warnings_list: list[str] = field(default_factory=list)
    retrieval_latency_s: float | None = None
    hints_index_freshness: str | None = None
    background_refresh_scheduled: bool = False
    reindex_action: str | None = None


@dataclass
class RetrievalRuntimeState:
    task: asyncio.Task[RetrievalTaskResult] | None
    prompts: dict[str, Any]
    freshness: str
    max_hints: int
    base_dir: str
    _task_result: RetrievalTaskResult | None = None
    _compact_hints: list[dict[str, Any]] | None = None
    _guidance_message: str | None = None
    _guidance_consumed: bool = False

    def _build_guidance_message(self, compact_hints: list[dict[str, Any]]) -> str | None:
        if not compact_hints:
            return None
        template = str(self.prompts.get("retrieval_guidance_message_template", "")).strip()
        if not template:
            return None
        retrieval_kwargs = _resolve_retrieval_format_kwargs(
            compact_hints,
            freshness=self.freshness,
            prompts=self.prompts,
        )
        return render_retrieval_guidance_message(template, **retrieval_kwargs)

    def _materialize_task_result(self, task_result: RetrievalTaskResult) -> RetrievalTaskResult:
        self._task_result = task_result
        compact_hints = _compact_semantic_hints(
            task_result.semantic_results,
            _hint_limit_for_freshness(self.max_hints, self.freshness),
            base_dir=self.base_dir,
        )
        self._compact_hints = compact_hints
        self._guidance_message = self._build_guidance_message(compact_hints)
        return task_result

    def _resolve_ready_result(self) -> RetrievalTaskResult | None:
        if self._task_result is not None:
            return self._task_result
        if self.task is None or not self.task.done():
            return None
        if self.task.cancelled():
            return self._materialize_task_result(RetrievalTaskResult())
        try:
            task_result = self.task.result()
        except Exception as exc:
            logger.warning("Retrieval task failed unexpectedly: %s", exc)
            task_result = RetrievalTaskResult()
        return self._materialize_task_result(task_result)

    def poll_guidance_messages(self, turn: int) -> list[str]:
        if self._guidance_consumed:
            return []
        if turn < 1:
            return []
        if self._resolve_ready_result() is None:
            return []
        if not self._guidance_message:
            return []
        self._guidance_consumed = True
        return [self._guidance_message]

    async def finalize(self) -> RetrievalTaskResult:
        ready_result = self._resolve_ready_result()
        if ready_result is not None:
            return ready_result
        if self.task is None:
            return self._materialize_task_result(RetrievalTaskResult())

        # Leave the task running in the background. Cancelling here would propagate
        # CancelledError into _run_blocking_retrieval_call, forcing ThreadPoolExecutor
        # __exit__ -> shutdown(wait=True) on the event loop thread and blocking the
        # loop until the worker thread's slow call (cloud_search / CLI) returns.
        # The task is tracked in _background_retrieval_tasks so it won't be GC'd.
        return self._materialize_task_result(RetrievalTaskResult())

    def injected_hints(self) -> list[dict[str, Any]]:
        if not self._guidance_consumed or self._compact_hints is None:
            return []
        return self._compact_hints


def _prepare_retrieval_preflight(
    repo_client: "RelaceRepoClient | None",
    *,
    base_dir: str,
    backend: str,
    hint_policy: str,
    trace_id: str,
) -> RetrievalPreflight:
    warnings_list: list[str] = []
    hints_index_freshness = "unknown"
    background_refresh_scheduled = False
    reindex_action: str | None = None

    if backend == "none":
        hints_index_freshness = "missing"
        _append_warning(
            warnings_list,
            "Semantic retrieval disabled (MCP_RETRIEVAL_BACKEND=none).",
        )
        return RetrievalPreflight(
            should_run=False,
            hints_index_freshness=hints_index_freshness,
            warnings_list=warnings_list,
        )

    if backend in ("codanna", "chunkhound"):
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
            return RetrievalPreflight(
                should_run=False,
                hints_index_freshness=hints_index_freshness,
                warnings_list=warnings_list,
            )

        if not shutil.which(backend):
            disable_backend(backend, f"{backend} CLI not found in PATH")
            _append_warning(
                warnings_list,
                f"{backend_name} CLI not found in PATH. Proceeding without hints.",
            )
            return RetrievalPreflight(
                should_run=False,
                hints_index_freshness=hints_index_freshness,
                warnings_list=warnings_list,
            )

        freshness = classify_local_index_freshness(base_dir, backend)
        hints_index_freshness = freshness.freshness

        if freshness.refresh_recommended and _schedule_local_refresh(base_dir, backend):
            background_refresh_scheduled = True
            reindex_action = "scheduled_background_refresh"

        if not semantic_hints_usable_for_policy(freshness.freshness, hint_policy):
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
            return RetrievalPreflight(
                should_run=False,
                hints_index_freshness=hints_index_freshness,
                warnings_list=warnings_list,
                background_refresh_scheduled=background_refresh_scheduled,
                reindex_action=reindex_action,
            )

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

        return RetrievalPreflight(
            should_run=True,
            hints_index_freshness=hints_index_freshness,
            warnings_list=warnings_list,
            background_refresh_scheduled=background_refresh_scheduled,
            reindex_action=reindex_action,
        )

    if repo_client is None:
        hints_index_freshness = "missing"
        _append_warning(
            warnings_list,
            "Relace semantic retrieval unavailable. Proceeding without hints.",
        )
        return RetrievalPreflight(
            should_run=False,
            hints_index_freshness=hints_index_freshness,
            warnings_list=warnings_list,
        )

    freshness = classify_cloud_index_freshness(base_dir)
    hints_index_freshness = freshness.freshness

    if not semantic_hints_usable_for_policy(freshness.freshness, hint_policy):
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
        return RetrievalPreflight(
            should_run=False,
            hints_index_freshness=hints_index_freshness,
            warnings_list=warnings_list,
        )

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

    return RetrievalPreflight(
        should_run=True,
        hints_index_freshness=hints_index_freshness,
        warnings_list=warnings_list,
    )


async def _run_semantic_retrieval(
    repo_client: "RelaceRepoClient | None",
    *,
    query: str,
    base_dir: str,
    backend: str,
    hint_policy: str,
    trace_id: str,
    hints_index_freshness: str,
    max_hints: int,
    score_threshold: float,
    token_limit: int,
) -> RetrievalTaskResult:
    task_result = RetrievalTaskResult()
    retrieval_t0 = time.perf_counter()

    if backend in ("codanna", "chunkhound"):
        backend_name = _backend_display_name(backend)
        search_fn = chunkhound_search if backend == "chunkhound" else codanna_search
        try:
            task_result.semantic_results = await _run_blocking_retrieval_call(
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
                    "results_count": len(task_result.semantic_results),
                    "freshness": hints_index_freshness,
                    "hint_policy": hint_policy,
                }
            )
            if not task_result.semantic_results:
                _append_warning(
                    task_result.warnings_list,
                    f"{backend_name} returned no results. Proceeding without hints.",
                )
        except ExternalCLIError as exc:
            if exc.kind == "cli_not_found":
                disable_backend(exc.backend, f"{exc.kind}: {exc}")
            elif exc.kind == "index_missing":
                task_result.hints_index_freshness = "missing"
                if _schedule_local_refresh(base_dir, backend):
                    task_result.background_refresh_scheduled = True
                    task_result.reindex_action = "scheduled_background_refresh"
            _append_warning(
                task_result.warnings_list,
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
                task_result.warnings_list,
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
    elif backend == "relace" and repo_client is not None:
        try:
            cloud_result = await _run_blocking_retrieval_call(
                cloud_search_logic,
                repo_client,
                base_dir,
                query,
                branch="",
                score_threshold=score_threshold,
                token_limit=token_limit,
            )
            for warning in cloud_result.get("warnings", []):
                _append_warning(task_result.warnings_list, warning)

            if cloud_result.get("error"):
                _append_warning(
                    task_result.warnings_list,
                    f"Cloud search failed: {cloud_result['error']}. Proceeding without hints.",
                )
                logger.warning("[%s] Cloud search failed, see warnings", trace_id)
            else:
                task_result.semantic_results = cloud_result.get("results", [])
                log_event(
                    {
                        "kind": "retrieval_hints_complete",
                        "level": "info",
                        "trace_id": trace_id,
                        "backend": "relace",
                        "results_count": len(task_result.semantic_results),
                        "freshness": hints_index_freshness,
                        "hint_policy": hint_policy,
                    }
                )
                if not task_result.semantic_results:
                    _append_warning(
                        task_result.warnings_list,
                        "Cloud search returned no results. Proceeding without hints.",
                    )
        except Exception as exc:
            _append_warning(
                task_result.warnings_list,
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

    task_result.retrieval_latency_s = round(time.perf_counter() - retrieval_t0, 3)
    return task_result


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
        on_progress: Optional async callback receiving (completed_turns, max_turns).

    Returns:
        Dict with explanation, files, and metadata (same format as agentic_search).
    """
    score_threshold = 0.3
    max_hints = 8
    token_limit = 10000

    trace_id = get_trace_id() if tool_name_ctx.get() else str(uuid.uuid4())[:8]
    logger.debug("[%s] Starting agentic retrieval", trace_id)

    backend = _settings.RETRIEVAL_BACKEND
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
    backend_kind = "relace" if search_client.api_compat == _settings.RELACE_PROVIDER else "openai"
    prompts = load_prompt_file(f"retrieval_{backend_kind}")

    from ..lsp.languages import get_lsp_languages

    preflight = _prepare_retrieval_preflight(
        repo_client,
        base_dir=base_dir,
        backend=backend,
        hint_policy=hint_policy,
        trace_id=trace_id,
    )
    warnings_list.extend(preflight.warnings_list)
    hints_index_freshness = preflight.hints_index_freshness
    background_refresh_scheduled = preflight.background_refresh_scheduled
    reindex_action = preflight.reindex_action

    retrieval_task: asyncio.Task[RetrievalTaskResult] | None = None
    if preflight.should_run:
        retrieval_task = _track_background_task(
            asyncio.create_task(
                _run_semantic_retrieval(
                    repo_client,
                    query=query,
                    base_dir=base_dir,
                    backend=backend,
                    hint_policy=hint_policy,
                    trace_id=trace_id,
                    hints_index_freshness=hints_index_freshness,
                    max_hints=max_hints,
                    score_threshold=score_threshold,
                    token_limit=token_limit,
                ),
                name=f"relace-retrieval:{backend}",
            )
        )
        await asyncio.sleep(0)

    retrieval_state = RetrievalRuntimeState(
        task=retrieval_task,
        prompts=prompts,
        freshness=hints_index_freshness,
        max_hints=max_hints,
        base_dir=base_dir,
    )

    effective_config = replace(config, base_dir=base_dir)
    lsp_languages = get_lsp_languages(Path(base_dir))

    harness = FastAgenticSearchHarness(
        effective_config,
        search_client,
        lsp_languages=lsp_languages,
        prompts=prompts,
        trace=trace,
        runtime_user_messages_provider=retrieval_state.poll_guidance_messages,
    )
    result = await harness.run_async(
        query=query,
        trace_id=trace_id,
        on_progress=on_progress,
    )

    task_result = await retrieval_state.finalize()
    warnings_list.extend(task_result.warnings_list)
    if task_result.hints_index_freshness is not None:
        hints_index_freshness = task_result.hints_index_freshness
    if task_result.background_refresh_scheduled:
        background_refresh_scheduled = True
    if task_result.reindex_action is not None:
        reindex_action = task_result.reindex_action

    compact_semantic_hints = retrieval_state.injected_hints()

    result["trace_id"] = trace_id
    result["semantic_hints_used"] = len(compact_semantic_hints)
    result["semantic_hints"] = compact_semantic_hints
    result["retrieval_backend"] = backend
    result["hint_policy"] = hint_policy
    result["hints_index_freshness"] = hints_index_freshness
    result["background_refresh_scheduled"] = background_refresh_scheduled
    result["reindex_action"] = reindex_action
    result["retrieval_latency_s"] = task_result.retrieval_latency_s
    if warnings_list:
        result["warnings"] = warnings_list

    return result
