import json
import os
import re
from pathlib import Path
from urllib.parse import unquote

from relace_mcp.utils import uri_to_path

# --- Constants ---

WSL_MNT_PREFIX = "/mnt/"
_SKIP_USER_DIRS = frozenset(("Public", "Default", "Default User", "All Users"))

# CWD patterns to extract IDE name from installation path
# Windows: AppData\Local\Programs\<IDE> or Program Files\<IDE>
_WINDOWS_IDE_CWD_PATTERN = re.compile(
    r"^(?:.+[/\\]AppData[/\\]Local[/\\]Programs|[A-Za-z]:[/\\]Program Files(?:\s*\(x86\))?)[/\\]([^/\\]+)"
)
# macOS: /Applications/<IDE>.app/...
_MACOS_IDE_CWD_PATTERN = re.compile(r"^/Applications/([^/]+)\.app(?:/|$)")
# Linux: /usr/share/<ide>, /opt/<ide>, ~/.local/share/<ide> (AppImage), or /snap/<ide>
_LINUX_IDE_CWD_PATTERN = re.compile(r"^(?:/usr/share|/opt|/snap|.+/\.local/share)/([^/]+)")

# IDE installation folder name -> Roaming/config folder name mapping
# Most forks use the same name, only VS Code variants differ
_IDE_NAME_TO_ROAMING: dict[str, str] = {
    "Microsoft VS Code": "Code",
    "Microsoft VS Code Insiders": "Code - Insiders",
}


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


def _get_workspace_storage_for_ide(ide_name: str) -> Path | None:
    """Get workspaceStorage path for given IDE on current platform (tries case variants)."""
    import sys

    base_name = ide_name.removesuffix(".app")

    # Map installation folder name to roaming folder name (handles VS Code variants)
    mapped_name = _IDE_NAME_TO_ROAMING.get(base_name)
    if mapped_name:
        variants = [mapped_name]
    else:
        # Most forks use the same name; try case variants
        variants = [base_name, base_name.title(), base_name.lower()]

    home = Path.home()

    for name in variants:
        if sys.platform == "darwin":
            storage = home / "Library" / "Application Support" / name / "User" / "workspaceStorage"
        elif sys.platform == "win32":
            appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
            storage = appdata / name / "User" / "workspaceStorage"
        else:
            storage = home / ".config" / name / "User" / "workspaceStorage"

        if storage.exists():
            return storage
    return None


def _extract_ide_name_from_cwd() -> str | None:
    """Extract IDE name from CWD if running from IDE installation path."""
    try:
        cwd = str(Path.cwd().resolve())
    except Exception:
        return None

    # Try Windows pattern
    if match := _WINDOWS_IDE_CWD_PATTERN.match(cwd):
        return match.group(1)
    # Try macOS pattern
    if match := _MACOS_IDE_CWD_PATTERN.match(cwd):
        return match.group(1)
    # Try Linux pattern
    if match := _LINUX_IDE_CWD_PATTERN.match(cwd):
        return match.group(1)
    return None


# --- Public API ---


def is_cwd_in_ide_installation() -> bool:
    """Check if CWD is inside an IDE installation directory."""
    return _extract_ide_name_from_cwd() is not None


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
    """Resolve project path when CWD is IDE installation directory.

    Cross-platform support:
        Windows: AppData\\Local\\Programs\\<IDE> -> AppData\\Roaming\\<IDE>\\User\\workspaceStorage
        macOS:   /Applications/<IDE>.app/... -> ~/Library/Application Support/<IDE>/User/workspaceStorage
        Linux:   /usr/share/<ide> or /opt/<ide> -> ~/.config/<IDE>/User/workspaceStorage

    Returns:
        Absolute path to project directory, or None if not applicable.
    """
    ide_name = _extract_ide_name_from_cwd()
    if not ide_name:
        return None

    storage_dir = _get_workspace_storage_for_ide(ide_name)
    if not storage_dir:
        return None

    return _resolve_project_from_storage_dir(storage_dir)
