import os

_CHUNKHOUND_HEAD_FILE = ".chunkhound/last_indexed_head"
_CODANNA_HEAD_FILE = ".codanna/last_indexed_head"


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
