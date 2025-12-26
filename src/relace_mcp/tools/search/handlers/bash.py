import os
import shutil
import subprocess  # nosec B404

from ....utils import resolve_repo_path
from .bash_security import _is_blocked_command
from .constants import BASH_MAX_OUTPUT_CHARS, BASH_TIMEOUT_SECONDS


def _format_bash_result(result: subprocess.CompletedProcess[str]) -> str:
    """Format bash execution result.

    Args:
        result: subprocess.CompletedProcess object.

    Returns:
        Formatted output string.
    """
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
    """Translate /repo paths in command tokens to base_dir paths.

    Only translates tokens that look like paths (exactly /repo or starting with /repo/).
    Does not modify strings that happen to contain /repo as substring.

    Security:
        Uses resolve_repo_path to prevent /repo// escape attacks.

    Args:
        command: Original command string.
        base_dir: Base directory to translate /repo to.

    Returns:
        Command with /repo paths translated.
    """
    import shlex

    try:
        tokens = shlex.split(command)
    except ValueError:
        # Fallback: no translation if parsing fails
        return command

    translated = []
    for token in tokens:
        if token == "/repo" or token.startswith("/repo/"):  # nosec B105
            try:
                resolved = resolve_repo_path(
                    token, base_dir, allow_relative=False, allow_absolute=False
                )
                # Git Bash on Windows generally prefers forward slashes (C:/Users/...).
                if os.name == "nt":
                    resolved = resolved.replace("\\", "/")
                translated.append(resolved)
            except ValueError:
                # Security: invalid path (escape attempt), keep original (will fail safely)
                translated.append(token)
        else:
            translated.append(token)

    return shlex.join(translated)


def bash_handler(command: str, base_dir: str) -> str:
    """Execute read-only bash command (Unix-only).

    Platform:
        Unix/Linux/macOS only. Windows not supported (no bash).

    Args:
        command: Bash command to execute.
        base_dir: Working directory for command execution.

    Returns:
        Command output or error message.
    """
    # Step 1: Security check on ORIGINAL command (before path translation)
    blocked, reason = _is_blocked_command(command, base_dir)

    if blocked:
        return f"Error: Command blocked for security reasons. {reason}"

    # Step 2: Translate /repo paths AFTER security check
    translated_command = _translate_repo_paths_in_command(command, base_dir)

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
