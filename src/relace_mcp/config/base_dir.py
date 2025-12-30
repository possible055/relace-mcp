import logging
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

if TYPE_CHECKING:
    from fastmcp.server.context import Context
    from mcp.types import Root

logger = logging.getLogger(__name__)

# Roots cache: stores resolved (base_dir, source) from MCP Roots.
# Keyed by session/client ID to avoid cross-workspace leakage when serving multiple clients.
_roots_cache: dict[str, tuple[str, str]] = {}


def _roots_cache_key(ctx: "Context | None") -> str | None:
    """Derive a stable cache key for the current client/session (best-effort)."""
    if ctx is None:
        return None

    # FastMCP Context.session_id raises if request_context is not yet available.
    session_id: str | None = None
    if getattr(ctx, "request_context", None) is not None:
        try:
            session_id = ctx.session_id
        except Exception:
            session_id = None
    if isinstance(session_id, str) and session_id:
        return session_id

    # client_id is optional and returns None when request_context/meta is missing.
    client_id = getattr(ctx, "client_id", None)
    if isinstance(client_id, str) and client_id:
        return f"client:{client_id}"
    return None


def invalidate_roots_cache(ctx: "Context | None" = None) -> None:
    """Invalidate the cached MCP Roots resolution.

    Called by RootsMiddleware when receiving notifications/roots/list_changed.
    If a session/client key is available, only that entry is cleared; otherwise clears all.
    """
    global _roots_cache
    key = _roots_cache_key(ctx)
    if key is None:
        if _roots_cache:
            logger.info("[base_dir] Roots cache cleared due to roots/list_changed notification")
            _roots_cache.clear()
        return

    if key in _roots_cache:
        logger.info(
            "[base_dir] Roots cache invalidated due to roots/list_changed notification (session=%s)",
            key,
        )
        _roots_cache.pop(key, None)


# Markers that indicate a directory is a project root
PROJECT_MARKERS = (".git", "pyproject.toml", "package.json", "Cargo.toml", "go.mod", ".project")


def validate_project_directory(path: str) -> tuple[bool, str]:
    """Validate path is a safe project directory, not a system directory.

    This function checks for potentially dangerous paths that could lead to
    accidental file operations on system directories.

    Args:
        path: Directory path to validate

    Returns:
        Tuple of (is_safe, reason_if_unsafe). If is_safe is True, reason is empty.
    """
    resolved = Path(path).resolve()

    # Check 1: Filesystem root is never valid (POSIX '/', Windows drive/UNC root)
    if resolved == Path(resolved.anchor):
        return False, f"system directory: {resolved}"

    # Check 2: Project markers - at least one should exist
    has_marker = any((resolved / marker).exists() for marker in PROJECT_MARKERS)
    if not has_marker:
        return False, f"no project markers found ({', '.join(PROJECT_MARKERS)})"

    return True, ""


def validate_base_dir(path: str, *, require_write: bool = False) -> bool:
    """Validate if path is a valid project base directory.

    Args:
        path: Directory path to validate
        require_write: If True, ensure directory is writable

    Returns:
        True if valid, False otherwise
    """
    p = Path(path)
    try:
        resolved = p.resolve()
        if resolved == resolved.parent:
            logger.debug("Path is filesystem root (unsafe): %s", resolved)
            return False
    except OSError as exc:
        logger.debug("Path is not accessible: %s (%s)", path, exc)
        return False
    try:
        if not p.exists():
            logger.debug("Path does not exist: %s", path)
            return False
        if not p.is_dir():
            logger.debug("Path is not a directory: %s", path)
            return False
    except OSError as exc:
        logger.debug("Path is not accessible: %s (%s)", path, exc)
        return False

    # Permission sanity checks: require directory to be traversable and listable.
    # `os.access` is best-effort across platforms; `scandir` provides a stronger runtime check.
    if not os.access(p, os.R_OK):
        logger.debug("Path is not readable: %s", path)
        return False
    if not os.access(p, os.X_OK):
        logger.debug("Path is not traversable: %s", path)
        return False
    try:
        with os.scandir(p) as it:
            next(it, None)
    except OSError as exc:
        logger.debug("Path is not listable: %s (%s)", path, exc)
        return False

    if require_write:
        if not os.access(p, os.W_OK):
            logger.debug("Path is not writable: %s", path)
            return False
        try:
            # Create and auto-delete a temp file to validate real write permissions.
            # Uses a short-lived file to avoid leaving artifacts.
            with tempfile.NamedTemporaryFile(dir=p, prefix=".relace_write_test_", delete=True):
                pass
        except OSError as exc:
            logger.debug("Path is not writable (tempfile failed): %s (%s)", path, exc)
            return False

    return True


def uri_to_path(uri: str) -> str:
    """Convert file:// URI to filesystem path robustly.

    Args:
        uri: File URI (e.g., "file:///home/user/project")

    Returns:
        Filesystem path (e.g., "/home/user/project")
    """
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        # If it's not a file URI, it might be a raw path already
        # but let's be safe and try to parse it.
        return unquote(uri)

    # file:// URIs may include a netloc for UNC paths: file://server/share/folder
    # Reconstruct as //server/share/folder so url2pathname can handle it on Windows.
    # Note: parsed.path is str when input is str (Python guarantees this)
    raw_path = parsed.path
    if parsed.netloc and parsed.netloc != "localhost":
        raw_path = f"//{parsed.netloc}{parsed.path}"

    # url2pathname handles Windows drive letters correctly on Windows.
    path = url2pathname(raw_path)

    # On some systems, url2pathname might leave a leading slash on Windows paths
    # like /C:/Users -> C:\Users. Path() usually handles this, but let's be explicit.
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


def select_best_root(roots: "Sequence[Root]") -> str:
    """Select best root from multiple MCP Roots using heuristics.

    Priority:
    1. Root containing .git directory
    2. Root containing pyproject.toml
    3. Root containing package.json
    4. First root in list

    Args:
        roots: List of MCP Root objects

    Returns:
        Filesystem path of selected root
    """
    # Pre-parse all URIs to local paths
    root_paths: list[str] = []
    for r in roots:
        try:
            p = str(Path(uri_to_path(str(r.uri))).resolve())
            if validate_base_dir(p):
                root_paths.append(p)
        except Exception:  # nosec B112 - intentionally skip invalid roots
            continue

    if not root_paths:
        # If no valid roots found, fallback to first one anyway as a last resort
        # even if it might fail validation later
        try:
            return uri_to_path(str(roots[0].uri))
        except Exception as e:
            raise ValueError(f"All MCP Roots are invalid or unparseable: {e}") from e

    # Priority 1: .git
    for path in root_paths:
        if (Path(path) / ".git").exists():
            return path

    # Priority 2/3: Project markers
    markers = ["pyproject.toml", "package.json", "go.mod", "Cargo.toml"]
    for marker in markers:
        for path in root_paths:
            if (Path(path) / marker).exists():
                return path

    # Fallback to first valid root
    return root_paths[0]


async def resolve_base_dir_from_roots(roots: "Sequence[Root]") -> tuple[str, str]:
    """Resolve base_dir from MCP Roots.

    Args:
        roots: List of MCP Root objects from client

    Returns:
        Tuple of (base_dir, source_description)
    """
    if len(roots) == 1:
        path = uri_to_path(str(roots[0].uri))
        name = roots[0].name or "unnamed"
        logger.info("Using MCP Root: %s (%s)", path, name)
        return path, f"MCP Root ({name})"

    # Multi-root: use heuristic selection
    path = select_best_root(roots)
    logger.info("Using MCP Root (selected from %d roots): %s", len(roots), path)
    return path, f"MCP Root (selected from {len(roots)} roots)"


def _check_project_safety(resolved: str, source: str) -> None:
    """Log warning if resolved path is potentially unsafe.

    This is called for auto-resolved paths (MCP Roots, Git root, cwd).
    Explicit RELACE_BASE_DIR is trusted and skips this check.
    """
    is_safe, reason = validate_project_directory(resolved)
    if not is_safe:
        logger.warning(
            "Potentially unsafe project directory (%s): %s - %s",
            source,
            resolved,
            reason,
        )


async def resolve_base_dir(
    config_base_dir: str | None,
    ctx: "Context | None" = None,
) -> tuple[str, str]:
    """Resolve base_dir with fallback chain.

    Priority:
    1. RELACE_BASE_DIR env var (explicit config takes priority, trusted)
    2. Cached MCP Roots (invalidated by notifications/roots/list_changed)
    3. Fresh MCP Roots from client (dynamic, per-workspace)
    4. Git repository root detection (fallback)
    5. Current working directory (last resort with warning)

    Args:
        config_base_dir: Base directory from config (may be None)
        ctx: FastMCP Context object (may be None if not in tool context)

    Returns:
        Tuple of (base_dir, source_description)
    """
    # 1. Explicit config takes priority - trusted, no safety check
    if config_base_dir:
        resolved_path = str(Path(config_base_dir).resolve())
        logger.debug("[base_dir] Using RELACE_BASE_DIR: %s", resolved_path)
        return resolved_path, "RELACE_BASE_DIR"

    # 2. Try cached MCP Roots first (invalidated by RootsMiddleware on change)
    global _roots_cache
    cache_key = _roots_cache_key(ctx)
    if cache_key is not None:
        cached = _roots_cache.get(cache_key)
        if cached is not None:
            cached_path, cached_source = cached
            if validate_base_dir(cached_path):
                logger.debug(
                    "[base_dir] Using cached roots (session=%s): %s",
                    cache_key,
                    cached_path,
                )
                return cached
            logger.info(
                "[base_dir] Cached roots invalid, clearing (session=%s): %s",
                cache_key,
                cached_path,
            )
            _roots_cache.pop(cache_key, None)

    # 3. Try MCP Roots from client
    if ctx is not None:
        try:
            roots = await ctx.list_roots()
            if roots:
                path, source = await resolve_base_dir_from_roots(roots)
                resolved = str(Path(path).resolve())
                if validate_base_dir(resolved):
                    logger.info("[base_dir] Resolved from %s: %s", source, resolved)
                    _check_project_safety(resolved, source)
                    if cache_key is not None:
                        _roots_cache[cache_key] = (resolved, source)
                    return resolved, source
                logger.warning(
                    "MCP Roots resolved to invalid base_dir: %s (source=%s). Falling back...",
                    resolved,
                    source,
                )
        except Exception as e:
            logger.info("MCP Roots unavailable (client may not support roots): %s", e)

    # 4. Try Git root detection from cwd
    try:
        cwd = Path.cwd().resolve()
    except Exception:
        # Fallback if cwd is invalid/deleted
        cwd = Path(".").resolve()

    if git_root := find_git_root(str(cwd)):
        resolved = str(git_root.resolve())
        source = "Git root (fallback)"
        if not validate_base_dir(resolved):
            logger.warning("[base_dir] Git root is invalid or inaccessible: %s", resolved)
        else:
            logger.info("[base_dir] Resolved from %s: %s (cwd: %s)", source, resolved, cwd)
            logger.warning(
                "RELACE_BASE_DIR not set and MCP Roots unavailable. Using Git root: %s",
                resolved,
            )
            _check_project_safety(resolved, source)
            return resolved, source

    # 5. Fallback to cwd with warning
    resolved = str(cwd)
    source = "cwd (fallback)"
    logger.info("[base_dir] Resolved from %s: %s", source, resolved)
    if not validate_base_dir(resolved):
        raise RuntimeError(f"Cannot resolve a valid base_dir (cwd is invalid): {cwd}")

    logger.warning(
        "RELACE_BASE_DIR not set, MCP Roots unavailable, no Git repo found. "
        "Using cwd: %s (may be unreliable)",
        cwd,
    )
    _check_project_safety(resolved, source)
    return resolved, source
