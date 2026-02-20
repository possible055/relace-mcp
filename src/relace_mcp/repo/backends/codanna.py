# pyright: reportUnusedFunction=false
import asyncio
import logging
import os
import subprocess  # nosec B404
from typing import Any

from ..core.git import get_git_head
from .cli import _run_cli_json
from .errors import ExternalCLIError
from .index_state import _CODANNA_HEAD_FILE, _read_indexed_head, _write_indexed_head
from .registry import (
    _bg_codanna_pending,
    _bg_index_rerun,
    _bg_index_tasks,
    disable_backend,
)

logger = logging.getLogger(__name__)


def _codanna_health_probe(base_dir: str) -> None:
    try:
        _run_cli_json(
            [
                "codanna",
                "mcp",
                "semantic_search_with_context",
                "query:healthcheck",
                "limit:1",
                "threshold:0",
                "--json",
            ],
            base_dir,
            timeout=30,
        )
    except RuntimeError as exc:
        msg = str(exc).lower()
        if "index" in msg and ("missing" in msg or "not found" in msg or "not built" in msg):
            logger.debug("Codanna index not found in health probe, attempting to create...")
            env = os.environ.copy()
            env["LANG"] = "C.UTF-8"
            env["LC_ALL"] = "C.UTF-8"
            try:
                _ensure_codanna_index(base_dir, env)
            except RuntimeError as reindex_exc:
                raise ExternalCLIError(
                    backend="codanna",
                    kind="index_missing",
                    message=f"Codanna index not available. Auto-index failed: {reindex_exc}",
                    command=["codanna", "mcp"],
                ) from reindex_exc
            head = get_git_head(base_dir)
            if head:
                _write_indexed_head(base_dir, head, _CODANNA_HEAD_FILE)
            return
        raise ExternalCLIError(
            backend="codanna",
            kind="nonzero_exit",
            message=str(exc),
            command=["codanna", "mcp"],
        ) from exc


def codanna_auto_reindex(base_dir: str) -> dict[str, Any]:
    """Check if codanna index is stale and reindex if needed.

    Compares current git HEAD with the last indexed HEAD.
    Returns status dict with "action" key: "skipped", "reindexed", or "error".
    """
    head = get_git_head(base_dir)
    if not head:
        return {"action": "skipped", "reason": "not a git repo"}

    last_head = _read_indexed_head(base_dir, _CODANNA_HEAD_FILE)
    if last_head == head:
        return {"action": "skipped", "reason": "index up to date"}

    logger.info(
        "Codanna index stale (HEAD %s -> %s), reindexing...", (last_head or "none")[:8], head[:8]
    )

    env = os.environ.copy()
    env["LANG"] = "C.UTF-8"
    env["LC_ALL"] = "C.UTF-8"

    try:
        _ensure_codanna_index(base_dir, env)
        _write_indexed_head(base_dir, head, _CODANNA_HEAD_FILE)
        logger.info("Codanna auto-reindex completed")
        return {"action": "reindexed", "old_head": last_head, "new_head": head}
    except (RuntimeError, OSError) as exc:
        logger.warning("Codanna auto-reindex failed: %s", exc)
        return {"action": "error", "message": str(exc)}


def _ensure_codanna_index(base_dir: str, env: dict[str, str]) -> None:
    # If .codanna directory doesn't exist, we must run `codanna init` first.
    if not os.path.isdir(os.path.join(base_dir, ".codanna")):
        try:
            result = subprocess.run(  # nosec B603 B607
                ["codanna", "init"],
                cwd=base_dir,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
                env=env,
            )
            if result.returncode != 0:
                stderr = (result.stderr or "").strip()
                raise RuntimeError(f"codanna init failed: {stderr}")
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"codanna init timeout: {exc}") from exc
        except FileNotFoundError as exc:
            raise RuntimeError("codanna CLI not found") from exc

    try:
        result = subprocess.run(  # nosec B603 B607
            ["codanna", "index"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
            env=env,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(f"codanna index failed: {stderr}")
        logger.debug("Codanna index created successfully")
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"codanna index timeout: {exc}") from exc
    except FileNotFoundError as exc:
        raise RuntimeError("codanna CLI not found") from exc


def codanna_search(
    query: str,
    *,
    base_dir: str,
    limit: int = 8,
    threshold: float = 0.3,
    _retry: bool = False,
    allow_auto_index: bool = True,
) -> list[dict[str, Any]]:
    """Run Codanna semantic search and return filename/score pairs.

    This calls the external `codanna` CLI (I/O + subprocess). If the index is
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
    command = [
        "codanna",
        "mcp",
        "semantic_search_with_context",
        f"query:{query}",
        f"limit:{limit}",
        f"threshold:{threshold}",
        "--json",
    ]

    try:
        data = _run_cli_json(command, base_dir, timeout=60)
    except RuntimeError as exc:
        msg = str(exc)
        lowered = msg.lower()
        if "cli not found" in lowered:
            raise ExternalCLIError(
                backend="codanna",
                kind="cli_not_found",
                message="codanna CLI not found. Install with: pip install codanna",
                command=command,
            ) from exc
        if "index" in lowered and (
            "missing" in lowered or "not found" in lowered or "not built" in lowered
        ):
            if not allow_auto_index or _retry:
                raise ExternalCLIError(
                    backend="codanna",
                    kind="index_missing",
                    message="Codanna index creation failed or index still not found",
                    command=command,
                ) from exc
            logger.debug("Codanna index not found, attempting to create...")
            env = os.environ.copy()
            env["LANG"] = "C.UTF-8"
            env["LC_ALL"] = "C.UTF-8"
            try:
                _ensure_codanna_index(base_dir, env)
            except RuntimeError as reindex_exc:
                raise ExternalCLIError(
                    backend="codanna",
                    kind="index_missing",
                    message=f"Codanna auto-index failed: {reindex_exc}",
                    command=["codanna", "index"],
                ) from reindex_exc
            return codanna_search(
                query,
                base_dir=base_dir,
                limit=limit,
                threshold=threshold,
                _retry=True,
                allow_auto_index=allow_auto_index,
            )
        raise ExternalCLIError(
            backend="codanna",
            kind="nonzero_exit",
            message=msg,
            command=command,
        ) from exc

    if data is None:
        return []

    # Codanna envelope schema: results are in "data" array, not "results"
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []

    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        # Codanna schema: filename lives in item["symbol"]["file_path"]
        # or item["context"]["file_path"]
        symbol = item.get("symbol")
        context = item.get("context")
        filename = None
        if isinstance(symbol, dict):
            filename = symbol.get("file_path")
        if not filename and isinstance(context, dict):
            filename = context.get("file_path")
        score = item.get("score")
        if not filename:
            continue
        try:
            score_val = float(score) if score is not None else 0.0
        except (TypeError, ValueError):
            score_val = 0.0
        results.append({"filename": filename, "score": score_val})

    return results


def codanna_index_file(file_path: str, base_dir: str) -> None:
    """Incrementally update Codanna index for a single edited file.

    Runs `codanna index <rel_path>` to re-index only the changed file,
    avoiding a full project reindex. Safe to call after every fast_apply edit.

    Args:
        file_path: Absolute path of the edited file.
        base_dir: Repository root (used as cwd and for relative path resolution).
    """
    env = os.environ.copy()
    env["LANG"] = "C.UTF-8"
    env["LC_ALL"] = "C.UTF-8"
    try:
        rel_path = os.path.relpath(file_path, base_dir)
    except ValueError:
        rel_path = file_path
    command = ["codanna", "index", rel_path]
    try:
        result = subprocess.run(  # nosec B603 B607
            command,
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
            env=env,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(f"codanna index failed: {stderr}")
        logger.debug("Codanna incremental reindex triggered by edit: %s", rel_path)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"codanna index timeout: {exc}") from exc
    except FileNotFoundError as exc:
        raise RuntimeError("codanna CLI not found") from exc


async def _async_run_codanna_index(file_path: str, base_dir: str) -> None:
    env = os.environ.copy()
    env["LANG"] = "C.UTF-8"
    env["LC_ALL"] = "C.UTF-8"
    try:
        rel_path = os.path.relpath(file_path, base_dir)
    except ValueError:
        rel_path = file_path
    try:
        proc = await asyncio.create_subprocess_exec(
            "codanna",
            "index",
            rel_path,
            cwd=base_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except FileNotFoundError:
        logger.warning("codanna CLI not found in background index; disabling backend")
        disable_backend("codanna", "cli_not_found: codanna not in PATH")
        return
    except OSError as exc:
        logger.warning("codanna background index failed to start: %s", exc)
        return
    try:
        _, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=120)
    except TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        logger.warning("Codanna background index timed out for %s", rel_path)
        return
    if proc.returncode != 0:
        stderr = (stderr_bytes or b"").decode("utf-8", errors="replace").strip()
        logger.warning("Codanna background index failed (exit %d): %s", proc.returncode, stderr)
    else:
        logger.debug("Codanna background index completed for %s", rel_path)


async def _async_run_codanna_full_index(base_dir: str) -> None:
    """Background full Codanna init+index when the index may not exist yet."""
    env = os.environ.copy()
    env["LANG"] = "C.UTF-8"
    env["LC_ALL"] = "C.UTF-8"
    try:
        await asyncio.get_event_loop().run_in_executor(None, _ensure_codanna_index, base_dir, env)
        logger.debug("Codanna full background init+index completed for %s", base_dir)
    except (RuntimeError, OSError) as exc:
        logger.warning("Codanna full background init+index failed: %s", exc)


def schedule_bg_codanna_full_index(base_dir: str) -> None:
    """Schedule a background Codanna full init+index. Sync, fire-and-forget.

    Use this instead of schedule_bg_codanna_index when the .codanna directory
    may not exist yet (e.g., first run or index_missing recovery). Runs
    `codanna init` followed by `codanna index` via a thread executor.
    """
    key = (base_dir, "codanna")
    task = _bg_index_tasks.get(key)
    if task is not None and not task.done():
        _bg_index_rerun[(base_dir, "codanna")] = True
        return

    def _on_done(_t: asyncio.Task[None]) -> None:
        # A full index covers the entire project, so any single-file pending
        # updates accumulated during the run are already included — discard them.
        _bg_codanna_pending.pop(key, None)
        if _bg_index_rerun.pop((base_dir, "codanna"), False):
            schedule_bg_codanna_full_index(base_dir)

    new_task = asyncio.create_task(_async_run_codanna_full_index(base_dir))
    new_task.add_done_callback(_on_done)
    _bg_index_tasks[key] = new_task


def schedule_bg_codanna_index(file_path: str, base_dir: str) -> None:
    """Schedule a background Codanna single-file reindex. Sync, fire-and-forget.

    Queues all pending paths while an index is running so intermediate edits
    are not dropped.
    """
    key = (base_dir, "codanna")
    task = _bg_index_tasks.get(key)
    if task is not None and not task.done():
        pending = _bg_codanna_pending.get(key)
        if pending is None:
            pending = set()
            _bg_codanna_pending[key] = pending
        pending.add(file_path)
        return

    def _on_done(_t: asyncio.Task[None]) -> None:
        pending = _bg_codanna_pending.get(key)
        if not pending:
            _bg_codanna_pending.pop(key, None)
            return

        next_path = pending.pop()
        if not pending:
            _bg_codanna_pending.pop(key, None)
        schedule_bg_codanna_index(next_path, base_dir)

    new_task = asyncio.create_task(_async_run_codanna_index(file_path, base_dir))
    new_task.add_done_callback(_on_done)
    _bg_index_tasks[key] = new_task
