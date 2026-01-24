import logging
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from relace_mcp.config.workspace_storage import (
    is_cwd_in_ide_installation,
    resolve_workspace_from_cwd_ide_path,
    resolve_workspace_from_storage,
)
from relace_mcp.utils import find_git_root, uri_to_path

if TYPE_CHECKING:
    from fastmcp.server.context import Context
    from mcp.types import Root

logger = logging.getLogger(__name__)

_MAX_CACHE_SIZE = 100
_roots_cache: dict[str, tuple[str, str]] = {}


def _roots_cache_key(ctx: "Context | None") -> str | None:
    if ctx is None:
        return None
    session_id: str | None = None
    if getattr(ctx, "request_context", None) is not None:
        try:
            session_id = ctx.session_id
        except Exception:
            session_id = None
    if isinstance(session_id, str) and session_id:
        return session_id
    client_id = getattr(ctx, "client_id", None)
    if isinstance(client_id, str) and client_id:
        return f"client:{client_id}"
    return None


def invalidate_roots_cache(ctx: "Context | None" = None) -> None:
    """Invalidate the cached MCP Roots resolution."""
    global _roots_cache
    key = _roots_cache_key(ctx)
    if key is None:
        if _roots_cache:
            logger.debug("[base_dir] Roots cache cleared")
            _roots_cache.clear()
        return
    if key in _roots_cache:
        logger.debug("[base_dir] Roots cache invalidated (session=%s)", key)
        _roots_cache.pop(key, None)


def _cache_roots(key: str, resolved: str, source: str) -> None:
    global _roots_cache
    if len(_roots_cache) >= _MAX_CACHE_SIZE:
        _roots_cache.clear()
    _roots_cache[key] = (resolved, source)


PROJECT_MARKERS = (".git", "pyproject.toml", "package.json", "Cargo.toml", "go.mod", ".project")


def _is_project_directory(path: str) -> tuple[bool, str]:
    """Check if path looks like a project directory (has markers, not system dir)."""
    resolved = Path(path).resolve()
    if resolved == Path(resolved.anchor):
        return False, f"system directory: {resolved}"
    if not any((resolved / m).exists() for m in PROJECT_MARKERS):
        return False, "no project markers found"
    return True, ""


def validate_project_directory(path: str) -> tuple[bool, str]:
    """Validate that a directory is safe to operate on.

    Args:
        path: Candidate project directory.

    Returns:
        (is_safe, reason). If is_safe is True, reason is an empty string.
    """
    return _is_project_directory(path)


def _is_accessible_directory(path: str, *, require_write: bool = False) -> bool:
    """Check if path is an accessible directory with proper permissions."""
    p = Path(path)
    try:
        resolved = p.resolve()
        if resolved == resolved.parent:
            return False
        if not p.exists() or not p.is_dir():
            return False
    except OSError:
        return False

    if not os.access(p, os.R_OK | os.X_OK):
        return False
    try:
        with os.scandir(p) as it:
            next(it, None)
    except OSError:
        return False

    if require_write:
        if not os.access(p, os.W_OK):
            return False
        try:
            with tempfile.NamedTemporaryFile(dir=p, prefix=".relace_write_test_", delete=True):
                pass
        except OSError:
            return False
    return True


def validate_base_dir(path: str) -> bool:
    """Validate base_dir is a usable directory.

    Args:
        path: Candidate base directory.

    Returns:
        True if the directory exists, is accessible, and is not a filesystem root.
    """
    return _is_accessible_directory(path)


def _select_best_root(roots: "Sequence[Root]") -> str:
    root_paths: list[str] = []
    for r in roots:
        try:
            p = str(Path(uri_to_path(str(r.uri))).resolve())
            if _is_accessible_directory(p):
                root_paths.append(p)
        except Exception:  # nosec B112
            continue

    if not root_paths:
        try:
            return uri_to_path(str(roots[0].uri))
        except Exception as e:
            raise ValueError(f"All MCP Roots are invalid: {e}") from e

    for marker in PROJECT_MARKERS:
        for path in root_paths:
            if (Path(path) / marker).exists():
                return path
    return root_paths[0]


def select_best_root(roots: "Sequence[Root]") -> str:
    """Select the best root path from MCP Roots.

    Args:
        roots: MCP Roots from the client.

    Returns:
        Absolute path string of the selected root.
    """
    return _select_best_root(roots)


async def resolve_base_dir(
    config_base_dir: str | None,
    ctx: "Context | None" = None,
) -> tuple[str, str]:
    """Resolve base_dir with fallback chain.

    Priority: MCP_BASE_DIR -> Cached Roots -> Fresh Roots -> Git root -> workspaceStorage -> cwd
    """
    # Log entry point for debugging
    try:
        current_cwd = str(Path.cwd())
    except Exception:
        current_cwd = "<unavailable>"
    logger.debug(
        "[base_dir] resolve started, config_base_dir=%s, cwd=%s", config_base_dir, current_cwd
    )

    # 1. Explicit config - trusted
    if config_base_dir:
        resolved = str(Path(config_base_dir).resolve())
        logger.debug("[base_dir] resolved=%s source=MCP_BASE_DIR", resolved)
        return resolved, "MCP_BASE_DIR"

    # 2. Cached MCP Roots
    cache_key = _roots_cache_key(ctx)
    if cache_key and (cached := _roots_cache.get(cache_key)):
        if _is_accessible_directory(cached[0]):
            logger.debug("[base_dir] resolved=%s source=%s (cached)", cached[0], cached[1])
            return cached
        _roots_cache.pop(cache_key, None)

    # 3. Fresh MCP Roots
    if ctx is not None:
        try:
            roots = await ctx.list_roots()
            logger.debug(
                "[base_dir] MCP roots: %s", [str(r.uri) for r in roots] if roots else "empty"
            )
            if roots:
                if len(roots) == 1:
                    path = uri_to_path(str(roots[0].uri))
                    source = f"MCP Root ({roots[0].name or 'unnamed'})"
                else:
                    path = _select_best_root(roots)
                    source = f"MCP Root (selected from {len(roots)} roots)"
                resolved = str(Path(path).resolve())
                if _is_accessible_directory(resolved):
                    if cache_key:
                        _cache_roots(cache_key, resolved, source)
                    logger.debug("[base_dir] resolved=%s source=%s", resolved, source)
                    return resolved, source
        except Exception as exc:
            logger.debug("[base_dir] MCP roots failed: %s", exc)

    # 4. Git root (preferred over workspaceStorage in normal cases)
    try:
        cwd = Path.cwd().resolve()
    except Exception:
        cwd = Path(".").resolve()

    if git_root := find_git_root(str(cwd)):
        resolved = str(git_root.resolve())
        if _is_accessible_directory(resolved):
            logger.debug("[base_dir] resolved=%s source=Git root (fallback)", resolved)
            return resolved, "Git root (fallback)"

    # 5. IDE workspaceStorage (only when CWD is IDE installation dir)
    # This prevents WSL from picking wrong project when launched from correct repo
    if is_cwd_in_ide_installation():
        logger.debug("[base_dir] CWD is IDE installation, trying workspaceStorage")
        workspace_path = resolve_workspace_from_storage() or resolve_workspace_from_cwd_ide_path()
        if workspace_path:
            resolved = str(Path(workspace_path).resolve())
            is_project, _ = _is_project_directory(resolved)
            if is_project and _is_accessible_directory(resolved):
                logger.debug("[base_dir] resolved=%s source=workspaceStorage (fallback)", resolved)
                return resolved, "workspaceStorage (fallback)"

    # 6. cwd
    resolved = str(cwd)
    if not _is_accessible_directory(resolved):
        raise RuntimeError(f"Cannot resolve valid base_dir: {cwd}")
    logger.debug("[base_dir] resolved=%s source=cwd (fallback)", resolved)
    return resolved, "cwd (fallback)"
