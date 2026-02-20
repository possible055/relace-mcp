# pyright: reportUnusedFunction=false
import asyncio
import logging
import os
import re
import subprocess  # nosec B404
import time
from typing import Any

from ..core.git import get_git_head, is_git_dirty
from .cli import _run_cli_text
from .errors import ExternalCLIError
from .index_state import (
    _CHUNKHOUND_DIRTY_TS_FILE,
    _CHUNKHOUND_HEAD_FILE,
    DIRTY_TTL_SECONDS,
    _read_dirty_ts,
    _read_indexed_head,
    _write_dirty_ts,
    _write_indexed_head,
)
from .registry import _bg_index_rerun, _bg_index_tasks, disable_backend, is_bg_index_running

logger = logging.getLogger(__name__)

_CHUNKHOUND_RESULT_RE = re.compile(
    r"^\[(\d+)\]\s+(.+)$",
    re.MULTILINE,
)
_CHUNKHOUND_SCORE_RE = re.compile(
    r"(?:Score|Similarity):\s+([\d.]+)",
)


def _is_chunkhound_index_missing_error(message: str) -> bool:
    lowered = message.lower()
    return (
        "not indexed" in lowered
        or "no index" in lowered
        or "database not found" in lowered
        or ("chunkhound index" in lowered and "run" in lowered)
    )


def _chunkhound_health_probe(base_dir: str) -> None:
    env = os.environ.copy()
    env["LANG"] = "C.UTF-8"
    env["LC_ALL"] = "C.UTF-8"
    try:
        _run_cli_text(
            ["chunkhound", "search", "healthcheck", "--page-size", "1"],
            base_dir,
            timeout=30,
            env=env,
        )
    except RuntimeError as exc:
        msg = str(exc)
        if _is_chunkhound_index_missing_error(msg):
            logger.debug("ChunkHound index not found in health probe, attempting to create...")
            try:
                _ensure_chunkhound_index(base_dir, env)
            except RuntimeError as reindex_exc:
                raise ExternalCLIError(
                    backend="chunkhound",
                    kind="index_missing",
                    message=f"ChunkHound index not found. Auto-index failed: {reindex_exc}",
                    command=["chunkhound", "search"],
                ) from reindex_exc
            head = get_git_head(base_dir)
            if head:
                _write_indexed_head(base_dir, head, _CHUNKHOUND_HEAD_FILE)
            return
        raise ExternalCLIError(
            backend="chunkhound",
            kind="nonzero_exit",
            message=str(exc),
            command=["chunkhound", "search"],
        ) from exc


def chunkhound_auto_reindex(base_dir: str) -> dict[str, Any]:
    """Check if chunkhound index is stale and reindex if needed.

    Compares current git HEAD with the last indexed HEAD.
    When HEAD matches but the worktree is dirty, reindexes at most
    once per DIRTY_TTL_SECONDS to cover external (non-fast_apply) edits.
    Returns status dict with "action" key: "skipped", "reindexed", or "error".
    """
    head = get_git_head(base_dir)
    if not head:
        return {"action": "skipped", "reason": "not a git repo"}

    last_head = _read_indexed_head(base_dir, _CHUNKHOUND_HEAD_FILE)

    dirty_trigger = False
    if last_head == head:
        if not is_git_dirty(base_dir):
            return {"action": "skipped", "reason": "index up to date"}
        if is_bg_index_running(base_dir, "chunkhound"):
            return {"action": "skipped", "reason": "bg_index_running"}
        last_ts = _read_dirty_ts(base_dir, _CHUNKHOUND_DIRTY_TS_FILE)
        if last_ts is not None and (time.time() - last_ts) < DIRTY_TTL_SECONDS:
            return {"action": "skipped", "reason": "dirty_ttl"}
        dirty_trigger = True

    reason = "dirty_worktree" if dirty_trigger else "head_changed"
    logger.info(
        "ChunkHound index stale (%s, HEAD %s -> %s), reindexing...",
        reason,
        (last_head or "none")[:8],
        head[:8],
    )

    env = os.environ.copy()
    env["LANG"] = "C.UTF-8"
    env["LC_ALL"] = "C.UTF-8"

    try:
        _ensure_chunkhound_index(base_dir, env)
        _write_indexed_head(base_dir, head, _CHUNKHOUND_HEAD_FILE)
        if dirty_trigger:
            _write_dirty_ts(base_dir, _CHUNKHOUND_DIRTY_TS_FILE)
        logger.info("ChunkHound auto-reindex completed")
        return {"action": "reindexed", "old_head": last_head, "new_head": head}
    except (RuntimeError, OSError) as exc:
        logger.warning("ChunkHound auto-reindex failed: %s", exc)
        return {"action": "error", "message": str(exc)}


def _ensure_chunkhound_index(base_dir: str, env: dict[str, str]) -> None:
    command = ["chunkhound", "index"]
    try:
        result = subprocess.run(  # nosec B603 B607
            command,
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
            env=env,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(f"chunkhound index failed: {stderr}")
        logger.debug("ChunkHound index created successfully")
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"chunkhound index timeout: {exc}") from exc
    except FileNotFoundError as exc:
        raise RuntimeError("chunkhound CLI not found") from exc


def _parse_chunkhound_text(output: str, threshold: float) -> list[dict[str, Any]]:
    """Parse chunkhound CLI text output into filename/score pairs.

    Expected format per result block:
        [N] path/to/file.py
        Score: 0.730
        Lines 10-20

    Raises:
        RuntimeError: If output contains result headers but no scores can be
            extracted, indicating an incompatible output format.
    """
    headers = list(_CHUNKHOUND_RESULT_RE.finditer(output))
    if not headers:
        if "no results" in output.lower() or "0 of" in output.lower():
            return []
        logger.debug("ChunkHound output has no parseable result blocks")
        return []

    results: list[dict[str, Any]] = []
    parsed_count = 0

    for i, header in enumerate(headers):
        filename = header.group(2).strip()
        block_start = header.end()
        block_end = headers[i + 1].start() if i + 1 < len(headers) else len(output)
        block = output[block_start:block_end]

        score_match = _CHUNKHOUND_SCORE_RE.search(block)
        if not score_match:
            continue
        parsed_count += 1

        try:
            score_val = float(score_match.group(1))
        except ValueError:
            score_val = 0.0

        if score_val < threshold:
            continue

        results.append({"filename": filename, "score": score_val})

    if parsed_count == 0 and len(headers) > 0:
        raise RuntimeError(
            f"ChunkHound output format incompatible: found {len(headers)} result headers "
            "but failed to extract any scores. The CLI output format may have changed."
        )

    return results


def chunkhound_search(
    query: str,
    *,
    base_dir: str,
    limit: int = 8,
    threshold: float = 0.3,
    _retry: bool = False,
    allow_auto_index: bool = True,
) -> list[dict[str, Any]]:
    """Run ChunkHound semantic search and return filename/score pairs.

    This calls the external `chunkhound` CLI (I/O + subprocess). If the index is
    missing and `allow_auto_index=True`, it attempts to create the index once
    and retries the search.

    Args:
        query: Natural language query.
        base_dir: Repository root (used as cwd).
        limit: Maximum number of results to return.
        threshold: Minimum score threshold to keep.
        _retry: Internal guard to prevent infinite auto-index loops.
        allow_auto_index: If False, raises immediately on index missing.

    Returns:
        List of dicts: `{"filename": str, "score": float}`.

    Raises:
        ExternalCLIError: For missing CLI, missing index (when not auto-indexing),
            or non-zero exit output.
    """
    env = os.environ.copy()
    env["HOME"] = os.environ.get("HOME", base_dir)
    env["LANG"] = "C.UTF-8"
    env["LC_ALL"] = "C.UTF-8"

    command = ["chunkhound", "search", query, "--page-size", str(limit)]

    try:
        output = _run_cli_text(command, base_dir, timeout=120, env=env)
    except RuntimeError as exc:
        error_text = str(exc)
        lowered = error_text.lower()
        if "cli not found" in lowered:
            raise ExternalCLIError(
                backend="chunkhound",
                kind="cli_not_found",
                message="chunkhound CLI not found. Install with: pip install chunkhound",
                command=command,
            ) from exc
        if _is_chunkhound_index_missing_error(error_text):
            if not allow_auto_index or _retry:
                raise ExternalCLIError(
                    backend="chunkhound",
                    kind="index_missing",
                    message="ChunkHound index creation failed or index still not found",
                    command=command,
                ) from exc
            logger.debug("ChunkHound index not found, attempting to create...")
            try:
                _ensure_chunkhound_index(base_dir, env)
            except RuntimeError as reindex_exc:
                raise ExternalCLIError(
                    backend="chunkhound",
                    kind="index_missing",
                    message=f"ChunkHound auto-index failed: {reindex_exc}",
                    command=["chunkhound", "index"],
                ) from reindex_exc
            return chunkhound_search(
                query,
                base_dir=base_dir,
                limit=limit,
                threshold=threshold,
                _retry=True,
                allow_auto_index=allow_auto_index,
            )
        raise ExternalCLIError(
            backend="chunkhound",
            kind="nonzero_exit",
            message=error_text,
            command=command,
        ) from exc

    if not output:
        return []

    return _parse_chunkhound_text(output, threshold)


def chunkhound_index_file(file_path: str, base_dir: str) -> None:
    """Incrementally update ChunkHound index after a file edit.

    ChunkHound's index command uses xxHash3-64 checksums internally, so it
    only re-processes files that have actually changed. This is safe to call
    after every fast_apply edit: unchanged files are skipped automatically.

    Args:
        file_path: Absolute path of the edited file (used for logging only).
        base_dir: Repository root to index from.
    """
    env = os.environ.copy()
    env["LANG"] = "C.UTF-8"
    env["LC_ALL"] = "C.UTF-8"
    try:
        _ensure_chunkhound_index(base_dir, env)
        logger.debug("ChunkHound incremental reindex triggered by edit: %s", file_path)
    except RuntimeError as exc:
        kind = "cli_not_found" if isinstance(exc.__cause__, FileNotFoundError) else "nonzero_exit"
        raise ExternalCLIError(
            backend="chunkhound",
            kind=kind,
            message=str(exc),
            command=["chunkhound", "index"],
        ) from exc


async def _async_run_chunkhound_index(base_dir: str) -> None:
    env = os.environ.copy()
    env["LANG"] = "C.UTF-8"
    env["LC_ALL"] = "C.UTF-8"
    try:
        proc = await asyncio.create_subprocess_exec(
            "chunkhound",
            "index",
            cwd=base_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except FileNotFoundError:
        logger.warning("chunkhound CLI not found in background index; disabling backend")
        disable_backend("chunkhound", "cli_not_found: chunkhound not in PATH")
        return
    except OSError as exc:
        logger.warning("chunkhound background index failed to start: %s", exc)
        return
    try:
        _, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=300)
    except TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        logger.warning("ChunkHound background index timed out for %s", base_dir)
        return
    if proc.returncode != 0:
        stderr = (stderr_bytes or b"").decode("utf-8", errors="replace").strip()
        logger.warning("ChunkHound background index failed (exit %d): %s", proc.returncode, stderr)
    else:
        logger.debug("ChunkHound background index completed for %s", base_dir)


def schedule_bg_chunkhound_index(base_dir: str) -> None:
    """Schedule a background ChunkHound incremental scan. Sync, fire-and-forget.

    Idempotent: if a scan is already running, sets rerun flag so it restarts
    after completion, ensuring edits made during a scan are not missed.
    """
    task = _bg_index_tasks.get((base_dir, "chunkhound"))
    if task is not None and not task.done():
        _bg_index_rerun[(base_dir, "chunkhound")] = True
        return

    def _on_done(_t: asyncio.Task[None]) -> None:
        if _bg_index_rerun.pop((base_dir, "chunkhound"), False):
            schedule_bg_chunkhound_index(base_dir)

    new_task = asyncio.create_task(_async_run_chunkhound_index(base_dir))
    new_task.add_done_callback(_on_done)
    _bg_index_tasks[(base_dir, "chunkhound")] = new_task
