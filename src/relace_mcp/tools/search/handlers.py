import os
import re
import subprocess  # nosec B404
from collections import deque
from pathlib import Path
from typing import Any

# 檔案大小上限（10MB）
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
# 目錄列出上限
MAX_DIR_ITEMS = 250
# grep 結果上限
MAX_GREP_MATCHES = 50
# grep 超時（秒）
GREP_TIMEOUT_SECONDS = 30
# Python fallback grep 最大深度
MAX_GREP_DEPTH = 10
# Context 截斷：每個 tool result 最大字元數
MAX_TOOL_RESULT_CHARS = 50000


def map_repo_path(path: str, base_dir: str) -> str:
    """將模型傳來的 /repo/... 路徑轉為實際檔案系統路徑。

    Args:
        path: 模型傳來的路徑，預期格式為 /repo 或 /repo/...
        base_dir: 實際的 repo root 目錄。

    Returns:
        實際檔案系統路徑。

    Raises:
        RuntimeError: 若 path 不以 /repo 開頭。
    """
    if path == "/repo" or path == "/repo/":
        return base_dir
    if not path.startswith("/repo/"):
        raise RuntimeError(f"Fast Agentic Search expects absolute paths under /repo/, got: {path}")
    rel = path[len("/repo/") :]
    return os.path.join(base_dir, rel)


def validate_path(file_path: str, base_dir: str) -> Path:
    """驗證路徑在 base_dir 內，防止 path traversal。"""
    try:
        resolved = Path(file_path).resolve()
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Invalid file path: {file_path}") from exc

    base_resolved = Path(base_dir).resolve()
    try:
        resolved.relative_to(base_resolved)
    except ValueError as exc:
        raise RuntimeError(
            f"Access denied: {file_path} is outside allowed directory {base_dir}"
        ) from exc

    return resolved


def view_file_handler(path: str, view_range: list[int], base_dir: str) -> str:
    """view_file 工具實作。"""
    try:
        fs_path = map_repo_path(path, base_dir)
        resolved = validate_path(fs_path, base_dir)

        if not resolved.exists():
            return f"Error: File not found: {path}"
        if not resolved.is_file():
            return f"Error: Not a file: {path}"

        file_size = resolved.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            return (
                f"Error: File too large ({file_size} bytes). Maximum: {MAX_FILE_SIZE_BYTES} bytes"
            )

        content = resolved.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()

        start = view_range[0] if len(view_range) > 0 else 1
        end = view_range[1] if len(view_range) > 1 else 100

        # -1 表示到檔尾
        if end == -1:
            end = len(lines)

        # 轉為 0-indexed
        start_idx = max(0, start - 1)
        end_idx = min(len(lines), end)

        result_lines = []
        for idx in range(start_idx, end_idx):
            line_num = idx + 1
            result_lines.append(f"{line_num} {lines[idx]}")

        result = "\n".join(result_lines)

        if end_idx < len(lines):
            result += "\n... rest of file truncated ..."

        return result

    except Exception as exc:
        return f"Error reading file: {exc}"


def view_directory_handler(path: str, include_hidden: bool, base_dir: str) -> str:
    """view_directory 工具實作（BFS-like 順序：先列當前層，再遞迴）。"""
    try:
        fs_path = map_repo_path(path, base_dir)
        resolved = validate_path(fs_path, base_dir)

        if not resolved.exists():
            return f"Error: Directory not found: {path}"
        if not resolved.is_dir():
            return f"Error: Not a directory: {path}"

        items: list[str] = []

        # BFS：使用 queue 實現廣度優先
        queue: deque[tuple[Path, Path]] = deque()  # (absolute_path, relative_path)
        queue.append((resolved, Path(".")))

        while queue and len(items) < MAX_DIR_ITEMS:
            current_abs, current_rel = queue.popleft()

            try:
                entries = list(current_abs.iterdir())
            except PermissionError:
                continue

            # 分類並排序
            dirs_list: list[tuple[str, Path]] = []
            files_list: list[tuple[str, Path]] = []

            for entry in entries:
                name = entry.name
                if not include_hidden and name.startswith("."):
                    continue

                if entry.is_dir():
                    dirs_list.append((name, entry))
                elif entry.is_file():
                    files_list.append((name, entry))

            dirs_list.sort(key=lambda x: x[0])
            files_list.sort(key=lambda x: x[0])

            # 先列出當前層的檔案（符合官方範例順序）
            for name, _ in files_list:
                if len(items) >= MAX_DIR_ITEMS:
                    break
                rel_path = current_rel / name
                # 移除開頭的 "./"
                path_str = str(rel_path)
                if path_str.startswith("./"):
                    path_str = path_str[2:]
                items.append(path_str)

            # 列出子目錄並加入 queue
            for name, entry in dirs_list:
                if len(items) >= MAX_DIR_ITEMS:
                    break
                rel_path = current_rel / name
                path_str = str(rel_path)
                if path_str.startswith("./"):
                    path_str = path_str[2:]
                items.append(f"{path_str}/")
                # 加入 queue 以便後續遞迴
                queue.append((entry, rel_path))

        result = "\n".join(items)
        if len(items) >= MAX_DIR_ITEMS:
            result += f"\n... output truncated at {MAX_DIR_ITEMS} items ..."

        return result

    except Exception as exc:
        return f"Error listing directory: {exc}"


def grep_search_handler(
    query: str,
    case_sensitive: bool,
    exclude_pattern: str | None,
    include_pattern: str | None,
    base_dir: str,
) -> str:
    """grep_search 工具實作（使用 ripgrep 或 fallback 到 Python re）。"""
    try:
        # 嘗試使用 ripgrep
        cmd = ["rg", "--line-number", "--no-heading", "--color=never"]

        if not case_sensitive:
            cmd.append("-i")

        if include_pattern:
            cmd.extend(["-g", include_pattern])

        if exclude_pattern:
            cmd.extend(["-g", f"!{exclude_pattern}"])

        # 注意：--max-count 是每個檔案的上限，不是總數
        # 我們用較大的值，然後在 post-processing 截斷
        cmd.extend(["--max-count", "100"])
        cmd.append(query)
        cmd.append(".")

        try:
            result = subprocess.run(  # nosec B603
                cmd,
                cwd=base_dir,
                capture_output=True,
                text=True,
                timeout=GREP_TIMEOUT_SECONDS,
                check=False,
            )

            if result.returncode == 0:
                output = result.stdout.strip()
                lines = output.split("\n") if output else []
                # Post-processing: 截斷到 MAX_GREP_MATCHES
                if len(lines) > MAX_GREP_MATCHES:
                    lines = lines[:MAX_GREP_MATCHES]
                    output = "\n".join(lines)
                    output += f"\n... output capped at {MAX_GREP_MATCHES} matches ..."
                return output if output else "No matches found."
            elif result.returncode == 1:
                # ripgrep returns 1 when no matches found
                return "No matches found."
            else:
                # ripgrep error, fallback to Python
                raise FileNotFoundError("ripgrep failed")

        except (FileNotFoundError, subprocess.TimeoutExpired):
            # Fallback 到 Python 實作
            return _grep_search_python_fallback(
                query, case_sensitive, include_pattern, exclude_pattern, base_dir
            )

    except Exception as exc:
        return f"Error in grep search: {exc}"


def _grep_search_python_fallback(
    query: str,
    case_sensitive: bool,
    include_pattern: str | None,
    exclude_pattern: str | None,
    base_dir: str,
) -> str:
    """純 Python 的 grep 實作（當 ripgrep 不可用時）。"""
    import fnmatch
    import signal
    from contextlib import contextmanager

    @contextmanager
    def timeout_context(seconds: int):
        """簡易 timeout context manager（僅 Unix）。"""

        def handler(signum, frame):
            raise TimeoutError(f"Python grep timed out after {seconds}s")

        if hasattr(signal, "SIGALRM"):
            old_handler = signal.signal(signal.SIGALRM, handler)
            signal.alarm(seconds)
            try:
                yield
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        else:
            # Windows: no timeout support
            yield

    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        pattern = re.compile(query, flags)
    except re.error as exc:
        return f"Invalid regex pattern: {exc}"

    matches: list[str] = []
    base_path = Path(base_dir)

    try:
        with timeout_context(GREP_TIMEOUT_SECONDS):
            for root, dirs, files in os.walk(base_path):
                # 計算深度，超過限制則停止遞迴
                try:
                    depth = len(Path(root).relative_to(base_path).parts)
                except ValueError:
                    depth = 0
                if depth >= MAX_GREP_DEPTH:
                    dirs.clear()
                    continue

                # 跳過隱藏目錄
                dirs[:] = [d for d in dirs if not d.startswith(".")]

                for filename in files:
                    if filename.startswith("."):
                        continue

                    # 檢查 include/exclude pattern
                    if include_pattern and not fnmatch.fnmatch(filename, include_pattern):
                        continue
                    if exclude_pattern and fnmatch.fnmatch(filename, exclude_pattern):
                        continue

                    filepath = Path(root) / filename
                    try:
                        rel_path = filepath.relative_to(base_path)
                    except ValueError:
                        continue

                    try:
                        content = filepath.read_text(encoding="utf-8", errors="ignore")
                        for line_num, line in enumerate(content.splitlines(), 1):
                            if pattern.search(line):
                                matches.append(f"{rel_path}:{line_num}:{line}")
                                if len(matches) >= MAX_GREP_MATCHES:
                                    break
                    except (OSError, UnicodeDecodeError):
                        continue

                    if len(matches) >= MAX_GREP_MATCHES:
                        break

                if len(matches) >= MAX_GREP_MATCHES:
                    break

    except TimeoutError as exc:
        if matches:
            result = "\n".join(matches)
            return result + f"\n... search timed out, showing {len(matches)} matches ..."
        return str(exc)

    if not matches:
        return "No matches found."

    result = "\n".join(matches)
    if len(matches) >= MAX_GREP_MATCHES:
        result += f"\n... output capped at {MAX_GREP_MATCHES} matches ..."

    return result


def report_back_handler(explanation: str, files: dict[str, list[list[int]]]) -> dict[str, Any]:
    """report_back 工具實作，直接回傳結構化結果。"""
    return {
        "explanation": explanation,
        "files": files,
    }


def truncate_for_context(text: str, max_chars: int = MAX_TOOL_RESULT_CHARS) -> str:
    """截斷過長的 tool result 以避免 context overflow。"""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    return truncated + f"\n... truncated ({len(text)} chars total, showing {max_chars}) ..."


def estimate_context_size(messages: list[dict[str, Any]]) -> int:
    """估算 messages 的總字元數。"""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(content)
        # tool_calls 也佔空間
        tool_calls = msg.get("tool_calls", [])
        for tc in tool_calls:
            func = tc.get("function", {})
            total += len(func.get("arguments", ""))
    return total


# === Bash Tool ===

BASH_TIMEOUT_SECONDS = 30
BASH_MAX_OUTPUT_CHARS = 50000

BASH_ALLOWED_COMMANDS = frozenset(
    {
        "ls",
        "find",
        "cat",
        "head",
        "tail",
        "wc",
        "file",
        "stat",
        "tree",
        "du",
        "df",
        "grep",
        "egrep",
        "fgrep",
        "rg",
        "ag",
        "awk",
        "sed",
        "sort",
        "uniq",
        "cut",
        "tr",
        "column",
        "xargs",
        "basename",
        "dirname",
        "realpath",
        "readlink",
        "date",
        "echo",
        "printf",
        "true",
        "false",
        "test",
        "[",
        "diff",
        "comm",
        "git",
        "python",
        "python3",
    }
)

BASH_BLOCKED_COMMANDS = frozenset(
    {
        "rm",
        "rmdir",
        "unlink",
        "shred",
        "mv",
        "cp",
        "install",
        "mkdir",
        "chmod",
        "chown",
        "chgrp",
        "wget",
        "curl",
        "fetch",
        "aria2c",
        "ssh",
        "scp",
        "rsync",
        "sftp",
        "ftp",
        "telnet",
        "nc",
        "netcat",
        "ncat",
        "socat",
        "sudo",
        "su",
        "doas",
        "pkexec",
        "pkill",
        "kill",
        "killall",
        "skill",
        "dd",
        "mkfs",
        "fdisk",
        "mount",
        "umount",
        "losetup",
        "reboot",
        "shutdown",
        "halt",
        "poweroff",
        "init",
        "useradd",
        "userdel",
        "usermod",
        "passwd",
        "chpasswd",
        "crontab",
        "at",
        "batch",
        "nohup",
        "disown",
        "setsid",
        "exec",
        "eval",
        "source",
        "touch",
        "tee",
        "truncate",
        "fallocate",
        "ln",
        "link",
        "mkfifo",
        "mknod",
        "tar",
        "zip",
        "unzip",
        "gzip",
        "gunzip",
        "bzip2",
        "xz",
        "make",
        "cmake",
        "ninja",
        "cargo",
        "npm",
        "pip",
        "pip3",
    }
)

GIT_BLOCKED_SUBCOMMANDS = frozenset(
    {
        "clone",
        "fetch",
        "pull",
        "push",
        "checkout",
        "reset",
        "revert",
        "restore",
        "clean",
        "stash",
        "merge",
        "rebase",
        "cherry-pick",
        "commit",
        "add",
        "rm",
        "mv",
        "init",
        "remote",
        "submodule",
        "config",
        "gc",
        "prune",
        "fsck",
        "reflog",
    }
)

GIT_ALLOWED_SUBCOMMANDS = frozenset(
    {
        "log",
        "show",
        "diff",
        "status",
        "branch",
        "blame",
        "annotate",
        "shortlog",
        "ls-files",
        "ls-tree",
        "cat-file",
        "rev-parse",
        "rev-list",
        "describe",
        "name-rev",
        "for-each-ref",
        "grep",
        "tag",
    }
)

PYTHON_BLOCKED_PATTERNS = [
    r"open\s*\(",
    r"write\s*\(",
    r"requests\.",
    r"urllib",
    r"socket",
    r"subprocess",
    r"os\.system",
    r"os\.popen",
    r"eval\s*\(",
    r"exec\s*\(",
    r"compile\s*\(",
    r"__import__",
    r"importlib",
]

BASH_BLOCKED_PATTERNS = [
    r">\s*[^&]",
    r">>\s*",
    r"\s\|\s",
    r"^\|",
    r"\|$",
    r"`",
    r"\$\(",
    r"\$\{",
    r";\s*\w",
    r"&&",
    r"\|\|",
    r"-exec\b",
    r"-execdir\b",
    r"-ok\b",
    r"-delete\b",
    r"xargs.*\brm\b",
    r"xargs.*\brmdir\b",
    r"\bsed\b.*-i",
    r"\bperl\b.*-[pi]",
]


def _contains_absolute_path_outside_repo(command: str) -> tuple[bool, str]:
    import shlex

    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    for token in tokens:
        if token.startswith("/"):
            if token == "/repo" or token.startswith("/repo/"):  # nosec B105
                continue
            if token == "/":  # nosec B105
                return True, "Root path '/' not allowed"
            return True, f"Absolute path outside /repo not allowed: {token}"

    return False, ""


def _is_blocked_git_command(tokens: list[str]) -> tuple[bool, str]:
    git_idx = -1
    for i, t in enumerate(tokens):
        if os.path.basename(t) == "git":
            git_idx = i
            break

    if git_idx == -1:
        return False, ""

    for t in tokens[git_idx + 1 :]:
        if t.startswith("-"):
            continue
        if t in GIT_BLOCKED_SUBCOMMANDS:
            return True, f"Blocked git subcommand: {t}"
        if t in GIT_ALLOWED_SUBCOMMANDS:
            return False, ""
        return True, f"Unknown git subcommand not in allowlist: {t}"

    return False, ""


def _is_blocked_python_command(command: str) -> tuple[bool, str]:
    if "python" not in command.lower():
        return False, ""

    if "-c" not in command:
        return True, "Python without -c is not allowed (may execute files)"

    for pattern in PYTHON_BLOCKED_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True, f"Blocked Python pattern: {pattern}"

    return False, ""


def _is_blocked_command(command: str) -> tuple[bool, str]:
    import shlex

    command_stripped = command.strip()
    if not command_stripped:
        return True, "Empty command"

    for pattern in BASH_BLOCKED_PATTERNS:
        if re.search(pattern, command):
            return True, f"Blocked pattern detected: {pattern}"

    has_abs_path, reason = _contains_absolute_path_outside_repo(command)
    if has_abs_path:
        return True, reason

    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    if not tokens:
        return True, "Empty command after parsing"

    base_cmd = os.path.basename(tokens[0])

    if base_cmd in BASH_BLOCKED_COMMANDS:
        return True, f"Blocked command: {base_cmd}"

    if base_cmd not in BASH_ALLOWED_COMMANDS:
        return True, f"Command not in allowlist: {base_cmd}"

    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        token_base = os.path.basename(token)
        if token_base in BASH_BLOCKED_COMMANDS:
            return True, f"Blocked command in arguments: {token_base}"

    if base_cmd == "git":
        blocked, reason = _is_blocked_git_command(tokens)
        if blocked:
            return True, reason

    if base_cmd in ("python", "python3"):
        blocked, reason = _is_blocked_python_command(command)
        if blocked:
            return True, reason

    return False, ""


def bash_handler(command: str, base_dir: str) -> str:
    blocked, reason = _is_blocked_command(command)
    if blocked:
        return f"Error: Command blocked for security reasons. {reason}"

    try:
        result = subprocess.run(  # nosec B603 B602 B607
            ["bash", "-c", command],
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

    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {BASH_TIMEOUT_SECONDS}s"
    except Exception as exc:
        return f"Error executing command: {exc}"
