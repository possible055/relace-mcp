import logging
import shutil
from typing import Any

from relace_mcp.repo.backends.index_state import (
    _CHUNKHOUND_HEAD_FILE,
    _CODANNA_HEAD_FILE,
    _read_indexed_head,
)
from relace_mcp.repo.core import get_current_git_info, load_sync_state

logger = logging.getLogger(__name__)

_HEAD_FILES = {
    "chunkhound": _CHUNKHOUND_HEAD_FILE,
    "codanna": _CODANNA_HEAD_FILE,
}


def check_retrieval_backend(backend: str, base_dir: str) -> dict[str, Any]:
    """Preflight check for retrieval backend availability and index freshness.

    Returns:
        Dict with diagnostic keys (backend, cli_ok, index_ok, git_head, etc.).

    Raises:
        RuntimeError: If the backend is unusable — fail-fast for benchmarks.
    """
    if backend == "auto":
        for name in ("codanna", "chunkhound"):
            if shutil.which(name):
                backend = name
                break
        else:
            backend = "relace"

    info: dict[str, Any] = {"backend": backend}

    if backend == "none":
        return info

    if backend in ("chunkhound", "codanna"):
        cli_ok = shutil.which(backend) is not None
        info["cli_ok"] = cli_ok
        if not cli_ok:
            info["error"] = f"{backend} CLI not found in PATH"
            raise RuntimeError(info["error"])

        _, git_head = get_current_git_info(base_dir)
        head_file = _HEAD_FILES[backend]
        index_head = _read_indexed_head(base_dir, head_file)

        info["git_head"] = git_head
        info["index_head"] = index_head
        info["index_ok"] = index_head is not None
        info["stale"] = (index_head != git_head) if (index_head and git_head) else True

        if not index_head:
            info["error"] = f"{backend} index not found at {base_dir}"
            raise RuntimeError(info["error"])
        if info["stale"]:
            info["error"] = (
                f"{backend} index stale: "
                f"index={index_head[:8]} git={git_head[:8] if git_head else '?'}"
            )
            raise RuntimeError(info["error"])

        return info

    # relace backend
    _, git_head = get_current_git_info(base_dir)
    sync_state = load_sync_state(base_dir)

    info["git_head"] = git_head

    if not sync_state:
        info["error"] = "No cloud sync state found; run cloud_sync first"
        raise RuntimeError(info["error"])

    synced_head = sync_state.git_head_sha
    info["synced_head"] = synced_head
    info["stale"] = synced_head != git_head if (synced_head and git_head) else True

    if info["stale"]:
        info["error"] = (
            f"Cloud sync stale: "
            f"synced={synced_head[:8] if synced_head else '?'} "
            f"git={git_head[:8] if git_head else '?'}"
        )
        raise RuntimeError(info["error"])

    return info
