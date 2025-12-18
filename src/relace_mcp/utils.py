import os
from pathlib import Path

# File size limit (10MB) to prevent memory exhaustion
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024


def validate_file_path(file_path: str, base_dir: str, *, allow_empty: bool = False) -> Path:
    """Validates and resolves file path, preventing path traversal attacks.

    Accepts absolute or relative paths. Relative paths are resolved against base_dir.

    Args:
        file_path: File path to validate (absolute or relative).
        base_dir: Base directory that restricts access scope.
        allow_empty: If True, allows empty paths (will error in subsequent processing).

    Returns:
        Resolved Path object.

    Raises:
        RuntimeError: If path is invalid or outside allowed directory.
    """
    if not allow_empty and (not file_path or not file_path.strip()):
        raise RuntimeError("file_path cannot be empty")

    # Handle relative paths: resolve against base_dir
    if not os.path.isabs(file_path):
        file_path = os.path.join(base_dir, file_path)

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
