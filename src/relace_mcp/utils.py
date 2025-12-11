from pathlib import Path


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
