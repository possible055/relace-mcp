import asyncio
import logging
import os
import subprocess  # nosec B404
import time
from typing import Any

from ...observability import log_event, log_trace_event, redact_value
from ..core.git import get_git_head, is_git_dirty
from .index_state import (
    _CODANNA_DIRTY_TS_FILE,
    _CODANNA_HEAD_FILE,
    DIRTY_TTL_SECONDS,
    _read_dirty_ts,
    _read_indexed_head,
    _write_dirty_ts,
    _write_indexed_head,
)
from .locking import BackendIndexRunResult, try_acquire_backend_index_lock
from .registry import (
    _bg_index_rerun,
    _bg_index_tasks,
    is_bg_index_running,
)

logger = logging.getLogger(__name__)


def _mark_codanna_index_fresh(base_dir: str) -> None:
    head = get_git_head(base_dir)
    if head:
        _write_indexed_head(base_dir, head, _CODANNA_HEAD_FILE)
    if is_git_dirty(base_dir):
        _write_dirty_ts(base_dir, _CODANNA_DIRTY_TS_FILE)


def _build_codanna_env() -> dict[str, str]:
    env = os.environ.copy()
    env["LANG"] = "C.UTF-8"
    env["LC_ALL"] = "C.UTF-8"
    return env


def _codanna_command_prefix(op: str) -> str:
    if op == "init":
        return "codanna init"
    return "codanna index"


def _codanna_log_fields(
    command: list[str],
    *,
    base_dir: str,
    timeout_s: int,
    op: str,
    background: bool,
    file_path: str | None = None,
    rel_path: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "backend": "codanna",
        "op": op,
        "command": command,
        "cwd": base_dir,
        "background": background,
        "timeout_s": timeout_s,
    }
    if file_path is not None:
        payload["file_path"] = file_path
    if rel_path is not None:
        payload["rel_path"] = rel_path
    return payload


def _run_sync_codanna_command(
    command: list[str],
    *,
    base_dir: str,
    env: dict[str, str],
    timeout_s: int,
    op: str,
    background: bool,
    file_path: str | None = None,
    rel_path: str | None = None,
) -> subprocess.CompletedProcess[str]:
    started = time.perf_counter()
    payload = _codanna_log_fields(
        command,
        base_dir=base_dir,
        timeout_s=timeout_s,
        op=op,
        background=background,
        file_path=file_path,
        rel_path=rel_path,
    )

    log_event({"kind": "backend_index_start", "level": "info", **payload})
    log_trace_event(
        {
            "kind": "cli_request",
            "cli": "codanna",
            "mode": "text",
            "env_keys": sorted(env.keys()),
            **payload,
        }
    )

    try:
        result = subprocess.run(  # nosec B603 B607
            command,
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        log_trace_event(
            {
                "kind": "cli_error",
                "cli": "codanna",
                "mode": "text",
                "error_type": type(exc).__name__,
                "error": str(exc),
                **payload,
            }
        )
        log_event(
            {
                "kind": "backend_index_error",
                "level": "error",
                "latency_ms": latency_ms,
                "error_kind": "timeout",
                "error": redact_value(str(exc), 500),
                **payload,
            }
        )
        raise RuntimeError(f"{_codanna_command_prefix(op)} timeout: {exc}") from exc
    except FileNotFoundError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        log_trace_event(
            {
                "kind": "cli_error",
                "cli": "codanna",
                "mode": "text",
                "error_type": type(exc).__name__,
                "error": str(exc),
                **payload,
            }
        )
        log_event(
            {
                "kind": "backend_index_error",
                "level": "error",
                "latency_ms": latency_ms,
                "error_kind": "cli_not_found",
                "error": "codanna CLI not found",
                **payload,
            }
        )
        raise RuntimeError("codanna CLI not found") from exc
    except OSError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        log_trace_event(
            {
                "kind": "cli_error",
                "cli": "codanna",
                "mode": "text",
                "error_type": type(exc).__name__,
                "error": str(exc),
                **payload,
            }
        )
        log_event(
            {
                "kind": "backend_index_error",
                "level": "error",
                "latency_ms": latency_ms,
                "error_kind": "os_error",
                "error": redact_value(str(exc), 500),
                **payload,
            }
        )
        raise RuntimeError(f"{_codanna_command_prefix(op)} failed: {exc}") from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        log_trace_event(
            {
                "kind": "cli_error",
                "cli": "codanna",
                "mode": "text",
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "detail": stderr,
                **payload,
            }
        )
        log_event(
            {
                "kind": "backend_index_error",
                "level": "error",
                "latency_ms": latency_ms,
                "returncode": result.returncode,
                "stderr_preview": redact_value(stderr, 500),
                **payload,
            }
        )
        raise RuntimeError(f"{_codanna_command_prefix(op)} failed: {stderr}")

    log_trace_event(
        {
            "kind": "cli_response",
            "cli": "codanna",
            "mode": "text",
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            **payload,
        }
    )
    log_event(
        {
            "kind": "backend_index_complete",
            "level": "info",
            "latency_ms": latency_ms,
            "returncode": result.returncode,
            "stdout_len": len(result.stdout or ""),
            "stderr_len": len(result.stderr or ""),
            **payload,
        }
    )
    return result


def codanna_auto_reindex(base_dir: str) -> dict[str, Any]:
    """Check if codanna index is stale and reindex if needed."""
    head = get_git_head(base_dir)
    if not head:
        return {"action": "skipped", "reason": "not a git repo"}

    last_head = _read_indexed_head(base_dir, _CODANNA_HEAD_FILE)

    dirty_trigger = False
    if last_head == head:
        if not is_git_dirty(base_dir):
            return {"action": "skipped", "reason": "index up to date"}
        if is_bg_index_running(base_dir, "codanna"):
            return {"action": "skipped", "reason": "bg_index_running"}
        last_ts = _read_dirty_ts(base_dir, _CODANNA_DIRTY_TS_FILE)
        if last_ts is not None and (time.time() - last_ts) < DIRTY_TTL_SECONDS:
            return {"action": "skipped", "reason": "dirty_ttl"}
        dirty_trigger = True

    reason = "dirty_worktree" if dirty_trigger else "head_changed"
    logger.info(
        "Codanna index stale (%s, HEAD %s -> %s), reindexing...",
        reason,
        (last_head or "none")[:8],
        head[:8],
    )

    try:
        _ensure_codanna_index(base_dir, _build_codanna_env())
        logger.info("Codanna auto-reindex completed")
        return {"action": "reindexed", "old_head": last_head, "new_head": head}
    except (RuntimeError, OSError) as exc:
        logger.warning("Codanna auto-reindex failed: %s", exc)
        return {"action": "error", "message": str(exc)}


def _ensure_codanna_index(base_dir: str, env: dict[str, str]) -> None:
    if not os.path.isdir(os.path.join(base_dir, ".codanna")):
        _run_sync_codanna_command(
            ["codanna", "init"],
            base_dir=base_dir,
            env=env,
            timeout_s=60,
            op="init",
            background=False,
        )

    _run_sync_codanna_command(
        ["codanna", "index"],
        base_dir=base_dir,
        env=env,
        timeout_s=600,
        op="index",
        background=False,
    )
    _mark_codanna_index_fresh(base_dir)
    logger.debug("Codanna index created successfully")


def codanna_index_file(file_path: str, base_dir: str) -> None:
    """Refresh the full Codanna index after a file edit."""
    _ensure_codanna_index(base_dir, _build_codanna_env())
    logger.debug("Codanna full reindex triggered by edit: %s", file_path)


async def _async_run_codanna_full_index(base_dir: str) -> BackendIndexRunResult:
    """Background full Codanna init+index when the index may not exist yet."""
    lease = try_acquire_backend_index_lock(base_dir, "codanna")
    if not lease.acquired:
        log_event(
            {
                "kind": "backend_index_skipped",
                "level": "info",
                "backend": "codanna",
                "op": "index",
                "cwd": base_dir,
                "background": True,
                "reason": lease.reason,
                "lock_path": lease.lock_path,
            }
        )
        logger.info("Codanna full background index skipped for %s (%s)", base_dir, lease.reason)
        return BackendIndexRunResult(
            status="lock_held" if lease.reason == "lock_held" else "lock_error",
            reason=lease.reason,
            lock_path=lease.lock_path,
        )

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _ensure_codanna_index, base_dir, _build_codanna_env())
        _mark_codanna_index_fresh(base_dir)
        logger.debug("Codanna full background init+index completed for %s", base_dir)
        return BackendIndexRunResult(status="completed", lock_path=lease.lock_path)
    except (RuntimeError, OSError) as exc:
        logger.warning("Codanna full background init+index failed: %s", exc)
        return BackendIndexRunResult(
            status="error",
            reason=str(exc),
            lock_path=lease.lock_path,
        )
    finally:
        lease.release()


def schedule_bg_codanna_full_index(base_dir: str) -> None:
    """Schedule a background Codanna full init+index."""
    key = (base_dir, "codanna")
    task = _bg_index_tasks.get(key)
    if task is not None and not task.done():
        _bg_index_rerun[key] = True
        return

    def _on_done(_task: asyncio.Task[Any]) -> None:
        if _bg_index_rerun.pop(key, False):
            schedule_bg_codanna_full_index(base_dir)

    new_task = asyncio.create_task(_async_run_codanna_full_index(base_dir))
    new_task.add_done_callback(_on_done)
    _bg_index_tasks[key] = new_task


def schedule_bg_codanna_index(file_path: str, base_dir: str) -> None:
    """Schedule a background Codanna full refresh after a file edit."""
    schedule_bg_codanna_full_index(base_dir)
