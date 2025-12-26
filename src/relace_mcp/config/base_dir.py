from __future__ import annotations

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


def select_best_root(roots: Sequence[Root]) -> str:
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


async def resolve_base_dir_from_roots(roots: Sequence[Root]) -> tuple[str, str]:
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


async def resolve_base_dir(
    config_base_dir: str | None,
    ctx: Context | None = None,
) -> tuple[str, str]:
    """Resolve base_dir with fallback chain.

    Priority:
    1. RELACE_BASE_DIR env var (explicit config takes priority)
    2. MCP Roots from client (dynamic, per-workspace)
    3. Git repository root detection (fallback)
    4. Current working directory (last resort with warning)

    Args:
        config_base_dir: Base directory from config (may be None)
        ctx: FastMCP Context object (may be None if not in tool context)

    Returns:
        Tuple of (base_dir, source_description)
    """
    # 1. Explicit config takes priority
    if config_base_dir:
        resolved_path = str(Path(config_base_dir).resolve())
        return resolved_path, "RELACE_BASE_DIR"

    # 2. Try MCP Roots
    if ctx is not None:
        try:
            roots = await ctx.list_roots()
            if roots:
                path, source = await resolve_base_dir_from_roots(roots)
                resolved = str(Path(path).resolve())
                if validate_base_dir(resolved):
                    return resolved, source
                logger.warning(
                    "MCP Roots resolved to invalid base_dir: %s (source=%s). Falling back...",
                    resolved,
                    source,
                )
        except Exception as e:
            logger.debug("MCP Roots unavailable: %s", e)

    # 3. Try Git root detection from cwd
    try:
        cwd = Path.cwd().resolve()
    except Exception:
        # Fallback if cwd is invalid/deleted
        cwd = Path(".").resolve()

    if git_root := find_git_root(str(cwd)):
        logger.warning(
            "RELACE_BASE_DIR not set and MCP Roots unavailable. Using Git root: %s (from cwd: %s)",
            git_root,
            cwd,
        )
        return str(git_root.resolve()), "Git root (fallback)"

    # 4. Fallback to cwd with warning
    if not validate_base_dir(str(cwd)):
        logger.error("Final fallback CWD is invalid or inaccessible: %s", cwd)

    logger.warning(
        "RELACE_BASE_DIR not set, MCP Roots unavailable, no Git repo found. "
        "Using cwd: %s (may be unreliable)",
        cwd,
    )
    return str(cwd), "cwd (fallback)"
