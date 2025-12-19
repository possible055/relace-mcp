import os
from pathlib import Path

# File size limit (10MB) to prevent memory exhaustion
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024


def resolve_repo_path(
    path: str,
    base_dir: str,
    *,
    allow_relative: bool = True,
    allow_absolute: bool = True,
    require_within_base_dir: bool = False,
) -> str:
    """Resolve /repo/... virtual path to absolute filesystem path.

    Security:
        - Normalizes path to prevent /repo// escape attacks
        - Validates result is within base_dir for /repo and relative paths

    Args:
        path: Input path (/repo/..., relative, or absolute).
        base_dir: Repository root directory.
        allow_relative: Accept relative paths (default True).
        allow_absolute: Accept non-/repo absolute paths (default True).
        require_within_base_dir: Require absolute paths to stay within base_dir.

    Returns:
        Resolved absolute filesystem path.

    Raises:
        ValueError: If path format is invalid or escapes base_dir.
    """
    base_resolved = Path(base_dir).resolve()

    # Handle /repo virtual root
    if path == "/repo" or path == "/repo/":
        return str(base_resolved)

    if path.startswith("/repo/"):
        rel = path[6:]  # Remove "/repo/"
        # SECURITY: Normalize to prevent /repo//etc/passwd -> /etc/passwd
        rel = rel.lstrip("/")  # Remove leading slashes
        if not rel:
            return str(base_resolved)
        # Use Path to normalize .. and resolve symlinks
        try:
            resolved = (base_resolved / rel).resolve()
        except (OSError, RuntimeError) as exc:
            raise ValueError(f"Cannot resolve path (circular symlink?): {path}") from exc
        # Validate within base_dir
        try:
            resolved.relative_to(base_resolved)
        except ValueError as exc:
            raise ValueError(f"Path escapes base_dir: {path}") from exc
        return str(resolved)

    # Handle relative paths
    if not os.path.isabs(path):
        if not allow_relative:
            raise ValueError(f"Relative path not allowed: {path}")
        try:
            resolved = (base_resolved / path).resolve()
        except (OSError, RuntimeError) as exc:
            raise ValueError(f"Cannot resolve path (circular symlink?): {path}") from exc
        try:
            resolved.relative_to(base_resolved)
        except ValueError as exc:
            raise ValueError(f"Path escapes base_dir: {path}") from exc
        return str(resolved)

    # Handle absolute paths
    if not allow_absolute:
        raise ValueError(f"Absolute path not allowed: {path}")
    try:
        resolved = Path(path).resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"Cannot resolve path (circular symlink?): {path}") from exc
    if require_within_base_dir:
        try:
            resolved.relative_to(base_resolved)
        except ValueError as exc:
            raise ValueError(f"Path escapes base_dir: {path}") from exc
    return str(resolved)


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
