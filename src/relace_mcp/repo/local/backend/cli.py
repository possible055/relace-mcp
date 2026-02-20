import json
import os
import subprocess  # nosec B404
from typing import Any


def _format_cli_error_detail(stdout: str, stderr: str) -> str:
    stdout_text = (stdout or "").strip()
    stderr_text = (stderr or "").strip()
    if stderr_text and stdout_text and stdout_text != stderr_text:
        return f"{stderr_text}\n{stdout_text}"
    if stderr_text:
        return stderr_text
    if stdout_text:
        return stdout_text
    return "unknown error"


def _run_cli_json(
    command: list[str], base_dir: str, timeout: int, env: dict[str, str] | None = None
) -> Any:
    if env is None:
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", base_dir),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }

    try:
        result = subprocess.run(  # nosec B603 B607
            command,
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"CLI timeout after {timeout}s: {exc}") from exc
    except FileNotFoundError as exc:
        cmd_name = command[0] if command else "unknown"
        raise RuntimeError(f"{cmd_name} CLI not found: {exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"CLI failed: {exc}") from exc

    if result.returncode != 0:
        cmd_name = command[0] if command else "CLI"
        detail = _format_cli_error_detail(result.stdout or "", result.stderr or "")
        raise RuntimeError(f"{cmd_name} error (exit {result.returncode}): {detail}")

    payload = (result.stdout or "").strip()
    if not payload:
        return None

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"JSON parse error: {exc}") from exc


def _run_cli_text(
    command: list[str], base_dir: str, timeout: int, env: dict[str, str] | None = None
) -> str:
    if env is None:
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", base_dir),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }

    try:
        result = subprocess.run(  # nosec B603 B607
            command,
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"CLI timeout after {timeout}s: {exc}") from exc
    except FileNotFoundError as exc:
        cmd_name = command[0] if command else "unknown"
        raise RuntimeError(f"{cmd_name} CLI not found: {exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"CLI failed: {exc}") from exc

    if result.returncode != 0:
        cmd_name = command[0] if command else "CLI"
        detail = _format_cli_error_detail(result.stdout or "", result.stderr or "")
        raise RuntimeError(f"{cmd_name} error (exit {result.returncode}): {detail}")

    return (result.stdout or "").strip()
