import os
from pathlib import Path

# 檔案大小上限（10MB），避免記憶體耗盡
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024


def normalize_repo_path(path: str, base_dir: str) -> str:
    """正規化路徑，支援 /repo/... 虛擬根目錄格式。

    Args:
        path: 輸入路徑，可為 /repo/...、相對路徑、或絕對路徑。
        base_dir: 實際的 repo root 目錄。

    Returns:
        正規化後的絕對路徑字串。
    """
    if not path or not path.strip():
        return path
    if path == "/repo" or path == "/repo/":
        return base_dir
    if path.startswith("/repo/"):
        rel = path[len("/repo/") :]
        return os.path.join(base_dir, rel)
    if not os.path.isabs(path):
        return os.path.join(base_dir, path)
    return path


def validate_file_path(file_path: str, base_dir: str, *, allow_empty: bool = False) -> Path:
    """Validates and resolves file path, preventing path traversal attacks.

    Args:
        file_path: File path to validate.
        base_dir: Base directory that restricts access scope.
        allow_empty: If True, allows empty paths (will error in subsequent processing).

    Returns:
        Resolved Path object.

    Raises:
        RuntimeError: If path is invalid or outside allowed directory.
    """
    if not allow_empty and (not file_path or not file_path.strip()):
        raise RuntimeError("file_path cannot be empty")

    try:
        resolved = Path(file_path).resolve()
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Invalid file path: {file_path}") from exc

    base_resolved = Path(base_dir).resolve()
    try:
        resolved.relative_to(base_resolved)
    except ValueError as exc:
        raise RuntimeError(
            f"Access denied: {file_path} is outside allowed directory {base_dir}"
        ) from exc

    return resolved
