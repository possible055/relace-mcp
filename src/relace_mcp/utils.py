import os
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname


def uri_to_path(uri: str) -> str:
    """Convert file:// URI to filesystem path robustly.

    Args:
        uri: File URI (e.g., "file:///home/user/project")

    Returns:
        Filesystem path (e.g., "/home/user/project")
    """
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return unquote(uri)

    raw_path = parsed.path
    if parsed.netloc and parsed.netloc != "localhost":
        raw_path = f"//{parsed.netloc}{parsed.path}"

    path = url2pathname(raw_path)

    if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[1] == ":":
        path = path[1:]

    return path


def find_git_root(start: str) -> Path | None:
    """Walk up from start directory to find .git directory.

    Args:
        start: Starting directory path

    Returns:
        Path to Git repository root, or None if not found
    """
    current = Path(start).resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return None


def _is_path_within_base(resolved: Path, base_resolved: Path) -> bool:
    """Check if resolved path is within base directory (handles case-insensitivity).

    Uses os.path.samefile for existing paths (handles symlinks and case-insensitive FS).
    Falls back to string prefix comparison for non-existing paths.

    Args:
        resolved: Resolved path to check.
        base_resolved: Resolved base directory.

    Returns:
        True if path is within base directory.
    """
    # For existing paths, use samefile to handle symlinks and case-insensitivity
    if resolved.exists() and base_resolved.exists():
        # Check if any parent is the same as base_dir
        current = resolved
        while current != current.parent:
            try:
                if os.path.samefile(current, base_resolved):
                    return True
            except OSError:
                break
            current = current.parent
        return False

    # For non-existing paths, use relative_to (standard check)
    try:
        resolved.relative_to(base_resolved)
        return True
    except ValueError:
        return False


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
        if not _is_path_within_base(resolved, base_resolved):
            raise ValueError(f"Path escapes base_dir: {path}")
        return str(resolved)

    # Handle relative paths
    if not os.path.isabs(path):
        if not allow_relative:
            raise ValueError(f"Relative path not allowed: {path}")
        try:
            resolved = (base_resolved / path).resolve()
        except (OSError, RuntimeError) as exc:
            raise ValueError(f"Cannot resolve path (circular symlink?): {path}") from exc
        if not _is_path_within_base(resolved, base_resolved):
            raise ValueError(f"Path escapes base_dir: {path}")
        return str(resolved)

    # Handle absolute paths
    if not allow_absolute:
        raise ValueError(f"Absolute path not allowed: {path}")
    try:
        resolved = Path(path).resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"Cannot resolve path (circular symlink?): {path}") from exc
    if require_within_base_dir:
        if not _is_path_within_base(resolved, base_resolved):
            raise ValueError(f"Path escapes base_dir: {path}")
    return str(resolved)


def map_path_no_resolve(path: str, base_dir: str) -> Path:
    """Map /repo/... virtual path to Path WITHOUT resolving symlinks.

    Use this when you need to check is_symlink() BEFORE resolution.
    Only handles /repo/... and relative paths. Absolute paths returned as-is.

    Args:
        path: Input path (/repo/..., relative, or absolute).
        base_dir: Repository root directory.

    Returns:
        Path object (not resolved, symlinks intact).
    """
    base_path = Path(base_dir)

    if path == "/repo" or path == "/repo/":
        return base_path

    if path.startswith("/repo/"):
        rel = path[6:].lstrip("/")
        if not rel:
            return base_path
        return base_path / rel

    if not os.path.isabs(path):
        return base_path / path

    return Path(path)


def validate_file_path(
    file_path: str,
    base_dir: str,
    *,
    extra_paths: Sequence[str] = (),
    allow_empty: bool = False,
) -> Path:
    """Validates and resolves file path, preventing path traversal attacks.

    Accepts absolute or relative paths. Relative paths are resolved against base_dir.

    Args:
        file_path: File path to validate (absolute or relative).
        base_dir: Base directory that restricts access scope.
        extra_paths: Additional allowed directories (already resolved absolute paths).
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
    except (OSError, ValueError, RuntimeError) as exc:
        raise RuntimeError(f"Invalid file path: {file_path}") from exc

    base_resolved = Path(base_dir).resolve()
    if _is_path_within_base(resolved, base_resolved):
        return resolved

    # Check extra_paths
    for extra in extra_paths:
        extra_resolved = Path(extra).resolve()
        if _is_path_within_base(resolved, extra_resolved):
            return resolved

    raise RuntimeError(f"Access denied: {file_path} is outside allowed directory {base_dir}")
