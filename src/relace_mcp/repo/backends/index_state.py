# pyright: reportUnusedFunction=false
import os
import time

_CHUNKHOUND_HEAD_FILE = ".chunkhound/last_indexed_head"
_CODANNA_HEAD_FILE = ".codanna/last_indexed_head"

_CHUNKHOUND_DIRTY_TS_FILE = ".chunkhound/last_dirty_reindex_ts"
_CODANNA_DIRTY_TS_FILE = ".codanna/last_dirty_reindex_ts"

DIRTY_TTL_SECONDS = 60


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


def _read_dirty_ts(base_dir: str, ts_file: str) -> float | None:
    path = os.path.join(base_dir, ts_file)
    try:
        with open(path) as f:
            return float(f.read().strip())
    except (OSError, ValueError):
        return None


def _write_dirty_ts(base_dir: str, ts_file: str) -> None:
    path = os.path.join(base_dir, ts_file)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(str(time.time()))
