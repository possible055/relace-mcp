from collections import deque
from pathlib import Path

from ....utils import validate_file_path
from .constants import MAX_DIR_ITEMS
from .paths import map_repo_path


def _strip_dot_prefix(path_str: str) -> str:
    """Remove './' prefix from path.

    Args:
        path_str: Path string.

    Returns:
        Path string with prefix removed.
    """
    return path_str[2:] if path_str.startswith("./") else path_str


def _collect_entries(
    current_abs: Path,
    include_hidden: bool,
) -> tuple[list[tuple[str, Path]], list[tuple[str, Path]]]:
    """Collect files and subdirectories in directory.

    Args:
        current_abs: Current directory absolute path.
        include_hidden: Whether to include hidden files.

    Returns:
        (files_list, dirs_list) tuple, each list contains (name, Path) tuples.
    """
    try:
        entries = list(current_abs.iterdir())
    except PermissionError:
        return [], []

    dirs_list: list[tuple[str, Path]] = []
    files_list: list[tuple[str, Path]] = []

    for entry in entries:
        name = entry.name
        if not include_hidden and name.startswith("."):
            continue

        # Never follow symlinks (prevents traversal outside base_dir and cycles).
        if entry.is_symlink():
            files_list.append((name, entry))
        elif entry.is_dir():
            dirs_list.append((name, entry))
        elif entry.is_file():
            files_list.append((name, entry))

    dirs_list.sort(key=lambda x: x[0])
    files_list.sort(key=lambda x: x[0])

    return files_list, dirs_list


def _collect_directory_items(resolved: Path, include_hidden: bool) -> tuple[list[str], bool]:
    """BFS collect directory items.

    Args:
        resolved: Directory absolute path.
        include_hidden: Whether to include hidden files.

    Returns:
        (items, truncated) tuple, items is item list, truncated indicates if output was truncated.
    """
    items: list[str] = []
    queue: deque[tuple[Path, Path]] = deque()
    queue.append((resolved, Path(".")))

    while queue and len(items) < MAX_DIR_ITEMS:
        current_abs, current_rel = queue.popleft()
        files_list, dirs_list = _collect_entries(current_abs, include_hidden)

        # List current level files first
        for name, _ in files_list:
            if len(items) >= MAX_DIR_ITEMS:
                break
            rel_path = current_rel / name
            items.append(_strip_dot_prefix(str(rel_path)))

        # List subdirectories and add to queue
        for name, entry in dirs_list:
            if len(items) >= MAX_DIR_ITEMS:
                break
            rel_path = current_rel / name
            items.append(_strip_dot_prefix(str(rel_path)) + "/")
            queue.append((entry, rel_path))

    truncated = len(items) >= MAX_DIR_ITEMS
    return items, truncated


def view_directory_handler(path: str, include_hidden: bool, base_dir: str) -> str:
    """view_directory tool implementation (BFS-like order: list current level first, then recurse)."""
    try:
        fs_path = map_repo_path(path, base_dir)
        resolved = validate_file_path(fs_path, base_dir, allow_empty=True)

        if not resolved.exists():
            return f"Error: Directory not found: {path}"
        if not resolved.is_dir():
            return f"Error: Not a directory: {path}"

        items, truncated = _collect_directory_items(resolved, include_hidden)

        result = "\n".join(items)
        if truncated:
            result += f"\n... output truncated at {MAX_DIR_ITEMS} items ..."

        return result

    except Exception as exc:
        return f"Error listing directory: {exc}"
