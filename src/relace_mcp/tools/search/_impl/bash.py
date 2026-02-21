import os
import re
import shutil
import subprocess  # nosec B404

from ....utils import resolve_repo_path
from .bash_security import is_blocked_command
from .constants import BASH_MAX_OUTPUT_CHARS, BASH_TIMEOUT_SECONDS


def _format_bash_result(result: subprocess.CompletedProcess[str]) -> str:
    """Format bash execution result."""
    stdout = result.stdout or ""
    stderr = result.stderr or ""

    if result.returncode != 0 and stderr:
        output = f"Exit code: {result.returncode}\n"
        if stdout:
            output += f"stdout:\n{stdout}\n"
        output += f"stderr:\n{stderr}"
    else:
        output = stdout + stderr

    if len(output) > BASH_MAX_OUTPUT_CHARS:
        output = output[:BASH_MAX_OUTPUT_CHARS]
        output += f"\n... output capped at {BASH_MAX_OUTPUT_CHARS} chars ..."

    return output.strip() if output.strip() else "(no output)"


def _translate_repo_paths_in_command(command: str, base_dir: str) -> str:
    """Translate /repo paths in command to base_dir paths via regex.

    Preserves shell operators (|, &&, 2>, etc.) by working at string level.
    """

    def _replace(m: re.Match[str]) -> str:
        token = m.group(0)
        try:
            resolved = resolve_repo_path(
                token, base_dir, allow_relative=False, allow_absolute=False
            )
            if os.name == "nt":
                resolved = resolved.replace("\\", "/")
            return resolved
        except ValueError:
            return token

    # Match /repo followed by /path chars, or standalone /repo at word boundary
    return re.sub(r"/repo(?:/[\w.+\-/]*)?", _replace, command)


def bash_handler(command: str, base_dir: str) -> str:
    """Execute read-only bash command (Unix-only).

    Args:
        command: Bash command to execute.
        base_dir: Working directory for command execution.

    Returns:
        Command output or error message.
    """
    blocked, reason = is_blocked_command(command, base_dir)

    if blocked:
        return f"Error: Command blocked for security reasons. {reason}"

    translated_command = _translate_repo_paths_in_command(command, base_dir)
    # Defense-in-depth: disable glob expansion to avoid path checks being bypassed
    translated_command = f"set -f; {translated_command}"

    try:
        bash_path = shutil.which("bash")
        if bash_path is None:
            return (
                "Error: bash is not available on this system. "
                "Install a bash shell (Linux/macOS) or use WSL/Git Bash on Windows."
            )

        result = subprocess.run(  # nosec B603 B602 B607
            [bash_path, "-c", translated_command],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=BASH_TIMEOUT_SECONDS,
            env={
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": base_dir,
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
            },
            check=False,
        )

        return _format_bash_result(result)

    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {BASH_TIMEOUT_SECONDS}s"
    except Exception as exc:
        return f"Error executing command: {exc}"
