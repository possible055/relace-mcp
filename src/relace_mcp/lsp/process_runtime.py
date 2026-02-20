import logging
import os
import shutil
import subprocess  # nosec B404 - required for LSP server communication
import sys
from pathlib import Path

import psutil

from relace_mcp.lsp.types import LSPError

logger = logging.getLogger(__name__)


def resolve_server_command(command: list[str], install_hint: str) -> list[str]:
    if not command:
        raise LSPError("Language server command is empty")

    executable = command[0]
    if not executable:
        raise LSPError("Language server executable is empty")

    hint = install_hint.strip()

    if any(sep in executable for sep in (os.sep, "/", "\\")):
        path = Path(executable)
        if path.exists():
            return [str(path), *command[1:]]
        if hint:
            raise LSPError(f"Language server '{executable}' not found. Install with: {hint}")
        raise LSPError(f"Language server '{executable}' not found")

    resolved = shutil.which(executable)
    if resolved:
        return [resolved, *command[1:]]

    scripts_dirs: list[Path] = []
    try:
        scripts_dirs.append(Path(sys.executable).parent)
    except Exception:  # nosec B110 - best-effort path resolution
        pass
    try:
        scripts_dirs.append(Path(sys.executable).resolve().parent)
    except Exception:  # nosec B110 - best-effort path resolution
        pass
    try:
        import sysconfig

        scripts_dirs.append(Path(sysconfig.get_path("scripts")))
    except Exception:  # nosec B110 - best-effort path resolution
        pass

    seen: set[Path] = set()
    for d in scripts_dirs:
        if d and d not in seen:
            seen.add(d)
    candidates = list(seen)
    for scripts_dir in candidates:
        candidate = scripts_dir / executable
        if candidate.exists():
            return [str(candidate), *command[1:]]

    if hint:
        raise LSPError(f"Language server '{executable}' not found. Install with: {hint}")

    raise LSPError(
        f"Language server '{executable}' not found. Ensure it is installed and on PATH "
        f"(or located in one of: {', '.join(str(p) for p in candidates)})."
    )


def start_server_process(command: list[str], workspace: str) -> subprocess.Popen[bytes]:
    logger.debug("Starting language server: %s", " ".join(command))
    return subprocess.Popen(  # nosec B603 - trusted command
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=workspace,
    )


def kill_process_tree(pid: int) -> None:
    try:
        parent = psutil.Process(pid)
    except psutil.Error:
        return

    for child in parent.children(recursive=True):
        try:
            child.kill()
        except psutil.Error:
            pass
    try:
        parent.kill()
    except psutil.Error:
        pass


def close_process_streams(process: subprocess.Popen[bytes]) -> None:
    for stream in (process.stdin, process.stdout, process.stderr):
        try:
            if stream:
                stream.close()
        except Exception:  # nosec B110 - best-effort cleanup
            pass


__all__ = [
    "close_process_streams",
    "kill_process_tree",
    "resolve_server_command",
    "start_server_process",
]
