import os
import time
from dataclasses import dataclass

from .backends.index_state import (
    _CHUNKHOUND_DIRTY_TS_FILE,
    _CHUNKHOUND_HEAD_FILE,
    _CODANNA_DIRTY_TS_FILE,
    _CODANNA_HEAD_FILE,
    DIRTY_TTL_SECONDS,
    _read_dirty_ts,
    _read_indexed_head,
)
from .core import get_current_git_info, is_git_dirty, load_sync_state


@dataclass(frozen=True)
class FreshnessStatus:
    freshness: str
    hints_usable: bool
    refresh_recommended: bool
    reason: str | None = None


def classify_cloud_index_freshness(base_dir: str) -> FreshnessStatus:
    sync_state = load_sync_state(base_dir)
    if sync_state is None:
        return FreshnessStatus(
            freshness="missing",
            hints_usable=False,
            refresh_recommended=True,
            reason="sync_state_missing",
        )

    _branch, current_head = get_current_git_info(base_dir)
    if not current_head:
        return FreshnessStatus(
            freshness="unknown",
            hints_usable=True,
            refresh_recommended=False,
            reason="git_head_unavailable",
        )

    if sync_state.git_head_sha and sync_state.git_head_sha != current_head:
        return FreshnessStatus(
            freshness="stale",
            hints_usable=True,
            refresh_recommended=True,
            reason="git_head_changed",
        )

    if is_git_dirty(base_dir):
        return FreshnessStatus(
            freshness="stale",
            hints_usable=True,
            refresh_recommended=True,
            reason="dirty_worktree",
        )

    return FreshnessStatus(
        freshness="fresh",
        hints_usable=True,
        refresh_recommended=False,
        reason="up_to_date",
    )


def classify_local_index_freshness(base_dir: str, backend: str) -> FreshnessStatus:
    if backend == "codanna":
        index_dir = ".codanna"
        head_file = _CODANNA_HEAD_FILE
        dirty_file = _CODANNA_DIRTY_TS_FILE
    elif backend == "chunkhound":
        index_dir = ".chunkhound"
        head_file = _CHUNKHOUND_HEAD_FILE
        dirty_file = _CHUNKHOUND_DIRTY_TS_FILE
    else:
        raise ValueError(f"Unsupported local backend: {backend}")

    if not os.path.isdir(os.path.join(base_dir, index_dir)):
        return FreshnessStatus(
            freshness="missing",
            hints_usable=False,
            refresh_recommended=True,
            reason="index_dir_missing",
        )

    last_indexed_head = _read_indexed_head(base_dir, head_file)
    if not last_indexed_head:
        return FreshnessStatus(
            freshness="stale",
            hints_usable=True,
            refresh_recommended=True,
            reason="last_indexed_head_missing",
        )

    _branch, current_head = get_current_git_info(base_dir)
    if not current_head:
        return FreshnessStatus(
            freshness="unknown",
            hints_usable=True,
            refresh_recommended=False,
            reason="git_head_unavailable",
        )

    if current_head != last_indexed_head:
        return FreshnessStatus(
            freshness="stale",
            hints_usable=True,
            refresh_recommended=True,
            reason="git_head_changed",
        )

    if is_git_dirty(base_dir):
        last_dirty_ts = _read_dirty_ts(base_dir, dirty_file)
        refresh_recommended = True
        if last_dirty_ts is not None and (time.time() - last_dirty_ts) < DIRTY_TTL_SECONDS:
            refresh_recommended = False
        return FreshnessStatus(
            freshness="stale",
            hints_usable=True,
            refresh_recommended=refresh_recommended,
            reason="dirty_worktree",
        )

    return FreshnessStatus(
        freshness="fresh",
        hints_usable=True,
        refresh_recommended=False,
        reason="up_to_date",
    )
