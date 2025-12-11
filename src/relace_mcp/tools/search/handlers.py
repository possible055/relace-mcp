import os
import re
import subprocess  # nosec B404
from collections import deque
from pathlib import Path
from typing import Any

from ...utils import validate_file_path

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


def view_file_handler(path: str, view_range: list[int], base_dir: str) -> str:
    """view_file 工具實作。"""
    try:
        fs_path = map_repo_path(path, base_dir)
        resolved = validate_file_path(fs_path, base_dir, allow_empty=True)

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
        resolved = validate_file_path(fs_path, base_dir, allow_empty=True)

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
# NOTE: Unix-only (requires bash shell, not available on Windows)

BASH_TIMEOUT_SECONDS = 30
BASH_MAX_OUTPUT_CHARS = 50000

# 阻止危險命令（黑名單）
BASH_BLOCKED_COMMANDS = frozenset(
    {
        # 檔案修改
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
        "touch",
        "tee",
        "truncate",
        "ln",
        "mkfifo",
        # 網路存取
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
        # 權限提升
        "sudo",
        "su",
        "doas",
        "pkexec",
        # 程序控制
        "kill",
        "killall",
        "pkill",
        # 系統管理
        "reboot",
        "shutdown",
        "halt",
        "poweroff",
        "init",
        "useradd",
        "userdel",
        "usermod",
        "passwd",
        "crontab",
        # 危險工具
        "dd",
        "eval",
        "exec",
        "source",
        # 封裝管理（可能觸發網路/安裝）
        "make",
        "cmake",
        "ninja",
        "cargo",
        "npm",
        "pip",
        "pip3",
    }
)

# 阻止危險模式（防止繞過）
BASH_BLOCKED_PATTERNS = [
    r">\s*[^&]",  # 重導向寫入
    r">>\s*",  # 附加寫入
    r"\|",  # 管道（可能繞過限制）
    r"`",  # 命令替換
    r"\$\(",  # 命令替換
    r";\s*\w",  # 命令串接
    r"&&",  # 條件執行
    r"\|\|",  # 條件執行
    r"-exec\b",  # find -exec（可能執行危險命令）
    r"-delete\b",  # find -delete
    r"\bsed\b.*-i",  # sed in-place 編輯
]

# Git 允許的 read-only 子命令（白名單策略）
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

# 允許的讀取命令（白名單：用於阻止未知命令）
BASH_SAFE_COMMANDS = frozenset(
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
        "diff",
        "git",
        "python",
        "python3",
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
    }
)


def _is_blocked_command(command: str, base_dir: str) -> tuple[bool, str]:
    """檢查命令是否違反安全規則。

    Args:
        command: 待執行的 bash 命令。
        base_dir: 命令執行的基準目錄。

    Returns:
        (is_blocked, reason) tuple。
    """
    import shlex

    command_stripped = command.strip()
    if not command_stripped:
        return True, "Empty command"

    # 檢查危險模式
    for pattern in BASH_BLOCKED_PATTERNS:
        if re.search(pattern, command):
            if pattern == r"\|":
                return True, (
                    "Blocked pattern: pipe operator. "
                    "Use grep_search tool for pattern matching instead"
                )
            return True, f"Blocked pattern: {pattern}"

    # 檢查路徑穿越
    if "../" in command or "..\\" in command:
        return True, "Path traversal pattern detected"

    # 檢查絕對路徑（非 /repo）
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    for token in tokens:
        if token.startswith("/"):
            if token == "/repo" or token.startswith("/repo/"):  # nosec B105
                continue
            # 阻止存取系統目錄
            return True, f"Absolute path outside /repo not allowed: {token}"

    if not tokens:
        return True, "Empty command after parsing"

    base_cmd = os.path.basename(tokens[0])

    # 檢查黑名單命令
    if base_cmd in BASH_BLOCKED_COMMANDS:
        return True, f"Blocked command: {base_cmd}"

    # 檢查白名單（阻止未知命令）
    if base_cmd not in BASH_SAFE_COMMANDS:
        return True, f"Command not in allowlist: {base_cmd}"

    # 特殊處理 git（白名單策略：僅允許明確的 read-only 子命令）
    if base_cmd == "git":
        for token in tokens[1:]:
            if token.startswith("-"):
                continue
            if token not in GIT_ALLOWED_SUBCOMMANDS:
                return True, f"Git subcommand not in allowlist: {token}"
            # 找到第一個非 flag 的 token 即為子命令，檢查完畢
            break

    # 特殊處理 python（僅允許 -c，且檢查危險模式）
    if base_cmd in ("python", "python3"):
        if len(tokens) < 3 or tokens[1] != "-c":
            return True, "Python without -c flag is not allowed (prevents script execution)"
        # 檢查 -c 中的危險模式（涵蓋所有可能的檔案修改與網路操作）
        python_code = " ".join(tokens[2:])
        dangerous_patterns = [
            # 檔案操作
            (r"open\s*\(", "file operations"),
            (r"\bwrite\s*\(", "write operations"),
            (r"\bremove\s*\(", "file removal"),
            (r"\bunlink\s*\(", "file removal"),
            (r"\brmdir\s*\(", "directory removal"),
            (r"\brename\s*\(", "file rename"),
            (r"\bmkdir\s*\(", "directory creation"),
            (r"\bchmod\s*\(", "permission change"),
            (r"\bchown\s*\(", "ownership change"),
            # 模組匯入（危險）
            (r"os\.remove", "os.remove"),
            (r"os\.unlink", "os.unlink"),
            (r"os\.rmdir", "os.rmdir"),
            (r"os\.system", "os.system"),
            (r"os\.popen", "os.popen"),
            (r"shutil\.rmtree", "shutil.rmtree"),
            (r"shutil\.move", "shutil.move"),
            (r"shutil\.copy", "shutil.copy"),
            (r"pathlib", "pathlib (file operations)"),
            (r"subprocess", "subprocess execution"),
            # 網路操作
            (r"urllib", "network access"),
            (r"requests\.", "network access"),
            (r"http\.client", "network access"),
            (r"http\.server", "network access"),
            (r"socket", "network access"),
            # 危險內建函式
            (r"\beval\s*\(", "eval"),
            (r"\bexec\s*\(", "exec"),
            (r"__import__", "__import__"),
            (r"compile\s*\(", "compile"),
        ]
        for pattern, desc in dangerous_patterns:
            if re.search(pattern, python_code, re.IGNORECASE):
                return True, f"Blocked Python pattern: {desc}"

    # 檢查參數中是否藏有危險命令
    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        token_base = os.path.basename(token)
        if token_base in BASH_BLOCKED_COMMANDS:
            return True, f"Blocked command in arguments: {token_base}"

    return False, ""


def bash_handler(command: str, base_dir: str) -> str:
    """執行 read-only bash 命令（Unix-only）。

    Platform:
        Unix/Linux/macOS only. Windows 不支援（無 bash）。

    Args:
        command: 待執行的 bash 命令。
        base_dir: 命令執行的工作目錄。

    Returns:
        命令輸出或錯誤訊息。
    """
    blocked, reason = _is_blocked_command(command, base_dir)

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
