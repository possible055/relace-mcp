import json
import re
from pathlib import Path
from urllib.parse import unquote

from relace_mcp.utils import uri_to_path

# --- Constants ---

WSL_MNT_PREFIX = "/mnt/"
_WINDOWS_IDE_CWD_PATTERN = re.compile(r"^(.+)[/\\]AppData[/\\]Local[/\\]Programs[/\\]([^/\\]+)")
_SKIP_USER_DIRS = frozenset(("Public", "Default", "Default User", "All Users"))


# --- Internal helpers ---


def _scan_workspace_subdirs(storage_dir: Path) -> list[Path]:
    """Return workspace subdirs sorted by mtime (newest first)."""
    subdirs: list[tuple[Path, float]] = []
    try:
        for entry in storage_dir.iterdir():
            if entry.is_dir() and not entry.name.isdigit():
                try:
                    subdirs.append((entry, entry.stat().st_mtime))
                except OSError:
                    continue
    except OSError:
        return []
    subdirs.sort(key=lambda x: x[1], reverse=True)
    return [p for p, _ in subdirs]


def _extract_folder_from_workspace_json(workspace_json: Path) -> str | None:
    """Extract folder path from workspace.json (handles file:// and vscode-remote://)."""
    try:
        data = json.loads(workspace_json.read_text(encoding="utf-8"))
        folder = data.get("folder")
        if not folder:
            return None
        if folder.startswith("file:///"):
            return uri_to_path(folder)
        if folder.startswith("vscode-remote://wsl"):
            decoded = unquote(folder)
            idx = decoded.find("/", len("vscode-remote://wsl+"))
            if idx != -1:
                return decoded[idx:]
        return None
    except (json.JSONDecodeError, OSError):
        return None


def _resolve_project_from_storage_dir(storage_dir: Path) -> str | None:
    """Find most recent project path from workspaceStorage directory."""
    for subdir in _scan_workspace_subdirs(storage_dir):
        workspace_json = subdir / "workspace.json"
        if workspace_json.exists():
            if path := _extract_folder_from_workspace_json(workspace_json):
                return path
    return None


def _get_wsl_workspace_storage_dir() -> Path | None:
    """Find most recent workspaceStorage in WSL mount (/mnt/c/Users/...)."""
    wsl_users_dir = Path(f"{WSL_MNT_PREFIX}c/Users")
    if not wsl_users_dir.exists():
        return None

    best: tuple[Path, float] | None = None
    for user_dir in wsl_users_dir.iterdir():
        if not user_dir.is_dir() or user_dir.name in _SKIP_USER_DIRS:
            continue
        roaming_dir = user_dir / "AppData" / "Roaming"
        if not roaming_dir.exists():
            continue
        for app_dir in roaming_dir.iterdir():
            if not app_dir.is_dir():
                continue
            storage_path = app_dir / "User" / "workspaceStorage"
            if storage_path.exists():
                try:
                    mtime = storage_path.stat().st_mtime
                    if best is None or mtime > best[1]:
                        best = (storage_path, mtime)
                except OSError:
                    continue
    return best[0] if best else None


# --- Public API ---


def resolve_workspace_from_storage() -> str | None:
    """Resolve project path from IDE workspaceStorage (WSL environment).

    Fallback mechanism when MCP Roots are unavailable. Scans VSCode-based
    IDE storage directories and returns the most recently used workspace.

    Returns:
        Absolute path to project directory, or None if not found.
    """
    storage_dir = _get_wsl_workspace_storage_dir()
    if not storage_dir:
        return None
    return _resolve_project_from_storage_dir(storage_dir)


def resolve_workspace_from_cwd_ide_path() -> str | None:
    """Resolve project path when CWD is IDE installation directory (Windows native).

    Detects when MCP server is spawned from IDE install path and maps it
    to the corresponding workspaceStorage location.

    Pattern:
        C:\\Users\\xxx\\AppData\\Local\\Programs\\<IDE>
        -> C:\\Users\\xxx\\AppData\\Roaming\\<IDE>\\User\\workspaceStorage

    Returns:
        Absolute path to project directory, or None if not applicable.
    """
    try:
        cwd_str = str(Path.cwd().resolve())
    except Exception:
        return None

    match = _WINDOWS_IDE_CWD_PATTERN.match(cwd_str)
    if not match:
        return None

    user_dir, ide_name = match.groups()
    roaming_storage = (
        Path(user_dir) / "AppData" / "Roaming" / ide_name / "User" / "workspaceStorage"
    )
    if not roaming_storage.exists():
        return None

    return _resolve_project_from_storage_dir(roaming_storage)
