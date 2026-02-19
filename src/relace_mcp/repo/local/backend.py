import asyncio
import json
import logging
import os
import re
import shutil
import subprocess  # nosec B404
from typing import Any

logger = logging.getLogger(__name__)

_CHUNKHOUND_RESULT_RE = re.compile(
    r"^\[(\d+)\]\s+(.+)$",
    re.MULTILINE,
)
_CHUNKHOUND_SCORE_RE = re.compile(
    r"(?:Score|Similarity):\s+([\d.]+)",
)

_disabled_backends: set[str] = set()
_bg_index_tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
_bg_index_rerun: dict[tuple[str, str], bool] = {}
_bg_codanna_pending: dict[tuple[str, str], set[str]] = {}


class ExternalCLIError(RuntimeError):
    """Structured error for external CLI backend failures.

    Attributes:
        backend: Name of the backend (e.g. "chunkhound", "codanna").
        kind: Error category for programmatic handling.
        command: CLI command that failed.
    """

    def __init__(self, *, backend: str, kind: str, message: str, command: list[str] | None = None):
        super().__init__(message)
        self.backend = backend
        self.kind = kind
        self.command = command or []


def is_backend_disabled(name: str) -> bool:
    return name in _disabled_backends


def disable_backend(name: str, reason: str) -> None:
    _disabled_backends.add(name)
    logger.warning("Backend %r disabled for this session: %s", name, reason)


def _is_chunkhound_index_missing_error(message: str) -> bool:
    lowered = message.lower()
    return (
        "not indexed" in lowered
        or "no index" in lowered
        or "database not found" in lowered
        or ("chunkhound index" in lowered and "run" in lowered)
    )


def _format_cli_error_detail(stdout: str, stderr: str) -> str:
    stdout_text = (stdout or "").strip()
    stderr_text = (stderr or "").strip()
    if stderr_text and stdout_text and stdout_text != stderr_text:
        return f"{stderr_text}\n{stdout_text}"
    if stderr_text:
        return stderr_text
    if stdout_text:
        return stdout_text
    return "unknown error"


def check_backend_health(backend: str, base_dir: str | None) -> str:
    """Validate that an external CLI backend is usable.

    Returns:
        Status string: "ok", or "deferred (base_dir not set)".

    Raises:
        ExternalCLIError: If the CLI is missing or the index is unavailable.
    """
    if backend not in ("chunkhound", "codanna"):
        return "ok"

    cli_name = backend
    if not shutil.which(cli_name):
        raise ExternalCLIError(
            backend=backend,
            kind="cli_not_found",
            message=f"{cli_name} CLI not found in PATH. Install with: pip install {cli_name}",
        )

    if not base_dir:
        return "deferred (base_dir not set)"

    if backend == "chunkhound":
        _chunkhound_health_probe(base_dir)
    elif backend == "codanna":
        _codanna_health_probe(base_dir)

    return "ok"


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
            head = _get_git_head(base_dir)
            if head:
                _write_indexed_head(base_dir, head, _CHUNKHOUND_HEAD_FILE)
            return
        raise ExternalCLIError(
            backend="chunkhound",
            kind="nonzero_exit",
            message=str(exc),
            command=["chunkhound", "search"],
        ) from exc


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
            head = _get_git_head(base_dir)
            if head:
                _write_indexed_head(base_dir, head, _CODANNA_HEAD_FILE)
            return
        raise ExternalCLIError(
            backend="codanna",
            kind="nonzero_exit",
            message=str(exc),
            command=["codanna", "mcp"],
        ) from exc


def _run_cli_json(
    command: list[str], base_dir: str, timeout: int, env: dict[str, str] | None = None
) -> Any:
    if env is None:
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", base_dir),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }

    try:
        result = subprocess.run(  # nosec B603 B607
            command,
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"CLI timeout after {timeout}s: {exc}") from exc
    except FileNotFoundError as exc:
        cmd_name = command[0] if command else "unknown"
        raise RuntimeError(f"{cmd_name} CLI not found: {exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"CLI failed: {exc}") from exc

    if result.returncode != 0:
        cmd_name = command[0] if command else "CLI"
        detail = _format_cli_error_detail(result.stdout or "", result.stderr or "")
        raise RuntimeError(f"{cmd_name} error (exit {result.returncode}): {detail}")

    payload = (result.stdout or "").strip()
    if not payload:
        return None

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"JSON parse error: {exc}") from exc


def _run_cli_text(
    command: list[str], base_dir: str, timeout: int, env: dict[str, str] | None = None
) -> str:
    if env is None:
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", base_dir),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }

    try:
        result = subprocess.run(  # nosec B603 B607
            command,
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"CLI timeout after {timeout}s: {exc}") from exc
    except FileNotFoundError as exc:
        cmd_name = command[0] if command else "unknown"
        raise RuntimeError(f"{cmd_name} CLI not found: {exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"CLI failed: {exc}") from exc

    if result.returncode != 0:
        cmd_name = command[0] if command else "CLI"
        detail = _format_cli_error_detail(result.stdout or "", result.stderr or "")
        raise RuntimeError(f"{cmd_name} error (exit {result.returncode}): {detail}")

    return (result.stdout or "").strip()


def codanna_auto_reindex(base_dir: str) -> dict[str, Any]:
    """Check if codanna index is stale and reindex if needed.

    Compares current git HEAD with the last indexed HEAD.
    Returns status dict with "action" key: "skipped", "reindexed", or "error".
    """
    head = _get_git_head(base_dir)
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


def chunkhound_search(
    query: str,
    *,
    base_dir: str,
    limit: int = 8,
    threshold: float = 0.3,
    _retry: bool = False,
    allow_auto_index: bool = True,
) -> list[dict[str, Any]]:
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


_CHUNKHOUND_HEAD_FILE = ".chunkhound/last_indexed_head"
_CODANNA_HEAD_FILE = ".codanna/last_indexed_head"


def _get_git_head(base_dir: str) -> str | None:
    try:
        result = subprocess.run(  # nosec B603 B607
            ["git", "rev-parse", "HEAD"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode == 0:
            return (result.stdout or "").strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _read_indexed_head(base_dir: str, head_file: str) -> str | None:
    path = os.path.join(base_dir, head_file)
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _write_indexed_head(base_dir: str, head: str, head_file: str) -> None:
    path = os.path.join(base_dir, head_file)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(head)


def chunkhound_auto_reindex(base_dir: str) -> dict[str, Any]:
    """Check if chunkhound index is stale and reindex if needed.

    Compares current git HEAD with the last indexed HEAD.
    Returns status dict with "action" key: "skipped", "reindexed", or "error".
    """
    head = _get_git_head(base_dir)
    if not head:
        return {"action": "skipped", "reason": "not a git repo"}

    last_head = _read_indexed_head(base_dir, _CHUNKHOUND_HEAD_FILE)
    if last_head == head:
        return {"action": "skipped", "reason": "index up to date"}

    logger.info(
        "ChunkHound index stale (HEAD %s -> %s), reindexing...", (last_head or "none")[:8], head[:8]
    )

    env = os.environ.copy()
    env["LANG"] = "C.UTF-8"
    env["LC_ALL"] = "C.UTF-8"

    try:
        _ensure_chunkhound_index(base_dir, env)
        _write_indexed_head(base_dir, head, _CHUNKHOUND_HEAD_FILE)
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


def codanna_search(
    query: str,
    *,
    base_dir: str,
    limit: int = 8,
    threshold: float = 0.3,
    _retry: bool = False,
    allow_auto_index: bool = True,
) -> list[dict[str, Any]]:
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
