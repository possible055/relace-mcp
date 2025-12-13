import os
import re
import subprocess  # nosec B404
from collections import deque
from pathlib import Path
from typing import Any

from ...utils import MAX_FILE_SIZE_BYTES, normalize_repo_path, validate_file_path
from .schemas import GrepSearchParams

# 目錄列出上限
MAX_DIR_ITEMS = 250
# grep 結果上限
MAX_GREP_MATCHES = 50
# grep 超時（秒）
GREP_TIMEOUT_SECONDS = 30
# Python fallback grep 最大深度
MAX_GREP_DEPTH = 10
# Context 截斷：每個 tool result 最大字元數（分工具類型）
MAX_TOOL_RESULT_CHARS = 50000  # truncate_for_context 的預設上限
MAX_VIEW_FILE_CHARS = 20000
MAX_GREP_SEARCH_CHARS = 12000
MAX_BASH_CHARS = 15000
MAX_VIEW_DIRECTORY_CHARS = 8000


def _timeout_context(seconds: int):
    """簡易 timeout context manager（僅 Unix）。

    Args:
        seconds: 超時秒數。

    Yields:
        None

    Raises:
        TimeoutError: 當操作超時時。
    """
    import signal
    from contextlib import contextmanager

    @contextmanager
    def timeout_impl():
        def handler(signum, frame):
            raise TimeoutError(f"Operation timed out after {seconds}s")

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

    return timeout_impl()


def map_repo_path(path: str, base_dir: str) -> str:
    """將模型傳來的 /repo/... 路徑轉為實際檔案系統路徑。

    此函數刻意只接受 /repo 虛擬根目錄格式（/repo 或 /repo/...），
    用於強制 search agent 一律以 /repo 作為「虛擬 repo root」回傳路徑。
    內部實作委派給 normalize_repo_path 進行實際路徑轉換。

    Args:
        path: 模型傳來的路徑，預期格式為 /repo 或 /repo/...
        base_dir: 實際的 repo root 目錄。

    Returns:
        實際檔案系統路徑。

    Raises:
        RuntimeError: 若 path 不以 /repo 開頭。
    """
    if path not in ("/repo", "/repo/") and not path.startswith("/repo/"):
        raise RuntimeError(f"Fast Agentic Search expects absolute paths under /repo/, got: {path}")
    return normalize_repo_path(path, base_dir)


def _validate_file_for_view(resolved: Path, path: str) -> str | None:
    """驗證檔案是否可讀取。

    Args:
        resolved: 解析後的檔案路徑。
        path: 原始請求路徑。

    Returns:
        錯誤訊息（若有問題），否則 None。
    """
    if not resolved.exists():
        return f"Error: File not found: {path}"
    if not resolved.is_file():
        return f"Error: Not a file: {path}"

    file_size = resolved.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        return f"Error: File too large ({file_size} bytes). Maximum: {MAX_FILE_SIZE_BYTES} bytes"

    return None


def _parse_view_range(view_range: list[int], total_lines: int) -> tuple[int, int]:
    """解析並正規化 view_range。

    Args:
        view_range: [start, end] 範圍。
        total_lines: 檔案總行數。

    Returns:
        (start_idx, end_idx) 0-indexed 範圍。
    """
    start = view_range[0] if len(view_range) > 0 else 1
    end = view_range[1] if len(view_range) > 1 else 100

    if end == -1:
        end = total_lines

    start_idx = max(0, start - 1)
    end_idx = min(total_lines, end)

    return start_idx, end_idx


def _format_file_lines(lines: list[str], start_idx: int, end_idx: int) -> str:
    """格式化檔案行（附帶行號）。

    Args:
        lines: 檔案所有行。
        start_idx: 起始索引（0-indexed）。
        end_idx: 結束索引（0-indexed）。

    Returns:
        格式化後的內容字串。
    """
    result_lines = [f"{idx + 1} {lines[idx]}" for idx in range(start_idx, end_idx)]
    result = "\n".join(result_lines)

    if end_idx < len(lines):
        result += "\n... rest of file truncated ..."

    return result


def view_file_handler(path: str, view_range: list[int], base_dir: str) -> str:
    """view_file 工具實作。"""
    try:
        fs_path = map_repo_path(path, base_dir)
        resolved = validate_file_path(fs_path, base_dir, allow_empty=True)

        error = _validate_file_for_view(resolved, path)
        if error:
            return error

        content = resolved.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()

        start_idx, end_idx = _parse_view_range(view_range, len(lines))
        return _format_file_lines(lines, start_idx, end_idx)

    except Exception as exc:
        return f"Error reading file: {exc}"


def _strip_dot_prefix(path_str: str) -> str:
    """移除路徑開頭的 './'。

    Args:
        path_str: 路徑字串。

    Returns:
        移除前綴後的路徑字串。
    """
    return path_str[2:] if path_str.startswith("./") else path_str


def _collect_entries(
    current_abs: Path,
    include_hidden: bool,
) -> tuple[list[tuple[str, Path]], list[tuple[str, Path]]]:
    """收集目錄中的檔案和子目錄。

    Args:
        current_abs: 當前目錄絕對路徑。
        include_hidden: 是否包含隱藏檔案。

    Returns:
        (files_list, dirs_list) tuple，每個列表包含 (name, Path) 元組。
    """
    try:
        entries = list(current_abs.iterdir())
    except PermissionError:
        return [], []

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

    return files_list, dirs_list


def _collect_directory_items(resolved: Path, include_hidden: bool) -> tuple[list[str], bool]:
    """BFS 收集目錄項目。

    Args:
        resolved: 目錄絕對路徑。
        include_hidden: 是否包含隱藏檔案。

    Returns:
        (items, truncated) tuple，items 為項目列表，truncated 表示是否被截斷。
    """
    items: list[str] = []
    queue: deque[tuple[Path, Path]] = deque()
    queue.append((resolved, Path(".")))

    while queue and len(items) < MAX_DIR_ITEMS:
        current_abs, current_rel = queue.popleft()
        files_list, dirs_list = _collect_entries(current_abs, include_hidden)

        # 先列出當前層的檔案
        for name, _ in files_list:
            if len(items) >= MAX_DIR_ITEMS:
                break
            rel_path = current_rel / name
            items.append(_strip_dot_prefix(str(rel_path)))

        # 列出子目錄並加入 queue
        for name, entry in dirs_list:
            if len(items) >= MAX_DIR_ITEMS:
                break
            rel_path = current_rel / name
            items.append(_strip_dot_prefix(str(rel_path)) + "/")
            queue.append((entry, rel_path))

    truncated = len(items) >= MAX_DIR_ITEMS
    return items, truncated


def view_directory_handler(path: str, include_hidden: bool, base_dir: str) -> str:
    """view_directory 工具實作（BFS-like 順序：先列當前層，再遞迴）。"""
    try:
        fs_path = map_repo_path(path, base_dir)
        resolved = validate_file_path(fs_path, base_dir, allow_empty=True)

        if not resolved.exists():
            return f"Error: Directory not found: {path}"
        if not resolved.is_dir():
            return f"Error: Not a directory: {path}"

        items, truncated = _collect_directory_items(resolved, include_hidden)

        result = "\n".join(items)
        if truncated:
            result += f"\n... output truncated at {MAX_DIR_ITEMS} items ..."

        return result

    except Exception as exc:
        return f"Error listing directory: {exc}"


def _exceeds_max_depth(root: Path, base_path: Path, max_depth: int) -> bool:
    """檢查目錄深度是否超過限制。

    Args:
        root: 當前目錄路徑。
        base_path: 基準目錄路徑。
        max_depth: 最大深度。

    Returns:
        True 若深度超過限制。
    """
    try:
        depth = len(Path(root).relative_to(base_path).parts)
    except ValueError:
        depth = 0
    return depth >= max_depth


def _matches_file_patterns(
    filename: str, include_pattern: str | None, exclude_pattern: str | None
) -> bool:
    """檢查檔名是否符合 include/exclude pattern。

    Args:
        filename: 檔案名稱。
        include_pattern: include pattern (fnmatch 格式)。
        exclude_pattern: exclude pattern (fnmatch 格式)。

    Returns:
        True 若檔案符合條件。
    """
    import fnmatch

    if include_pattern and not fnmatch.fnmatch(filename, include_pattern):
        return False
    if exclude_pattern and fnmatch.fnmatch(filename, exclude_pattern):
        return False
    return True


def _compile_search_pattern(query: str, case_sensitive: bool) -> re.Pattern | str:
    """編譯 regex pattern。

    Args:
        query: 搜尋 pattern。
        case_sensitive: 是否區分大小寫。

    Returns:
        編譯後的 Pattern，或錯誤訊息字串。
    """
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        return re.compile(query, flags)
    except re.error as exc:
        return f"Invalid regex pattern: {exc}"


def _filter_visible_dirs(dirs: list[str]) -> list[str]:
    """過濾掉隱藏目錄。

    Args:
        dirs: 目錄名稱列表。

    Returns:
        可見目錄列表。
    """
    return [d for d in dirs if not d.startswith(".")]


def _is_searchable_file(
    filename: str, include_pattern: str | None, exclude_pattern: str | None
) -> bool:
    """判斷檔案是否應被搜尋。

    Args:
        filename: 檔案名稱。
        include_pattern: include pattern。
        exclude_pattern: exclude pattern。

    Returns:
        True 若檔案應被搜尋。
    """
    if filename.startswith("."):
        return False
    return _matches_file_patterns(filename, include_pattern, exclude_pattern)


def _iter_searchable_files(
    base_path: Path,
    include_pattern: str | None,
    exclude_pattern: str | None,
):
    """產生符合過濾條件的檔案路徑。

    Args:
        base_path: 搜尋起點。
        include_pattern: 檔案名稱 include pattern (fnmatch)。
        exclude_pattern: 檔案名稱 exclude pattern (fnmatch)。

    Yields:
        (filepath, rel_path) tuple。
    """
    for root, dirs, files in os.walk(base_path):
        if _exceeds_max_depth(Path(root), base_path, MAX_GREP_DEPTH):
            dirs.clear()
            continue

        dirs[:] = _filter_visible_dirs(dirs)

        for filename in files:
            if not _is_searchable_file(filename, include_pattern, exclude_pattern):
                continue

            filepath = Path(root) / filename
            try:
                rel_path = filepath.relative_to(base_path)
            except ValueError:
                continue

            yield filepath, rel_path


def _search_in_file(
    filepath: Path,
    pattern: re.Pattern,
    rel_path: Path,
    limit: int,
) -> list[str]:
    """搜尋單一檔案並返回 match 列表。

    Args:
        filepath: 檔案絕對路徑。
        pattern: 編譯後的 regex pattern。
        rel_path: 檔案相對路徑（用於輸出）。
        limit: 最多回傳的 match 數量（用於 global cap）。

    Returns:
        Match 列表，格式為 "rel_path:line_num:line"。
    """
    if limit <= 0:
        return []

    matches: list[str] = []
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        for line_num, line in enumerate(content.splitlines(), 1):
            if pattern.search(line):
                matches.append(f"{rel_path}:{line_num}:{line}")
                if len(matches) >= limit:
                    break
    except (OSError, UnicodeDecodeError):
        pass

    return matches


def _build_ripgrep_command(params: GrepSearchParams) -> list[str]:
    """構建 ripgrep 命令列表。

    Args:
        params: grep 搜尋參數。

    Returns:
        ripgrep 命令列表。
    """
    cmd = ["rg", "--line-number", "--no-heading", "--color=never"]

    if not params.case_sensitive:
        cmd.append("-i")

    if params.include_pattern:
        cmd.extend(["-g", params.include_pattern])

    if params.exclude_pattern:
        cmd.extend(["-g", f"!{params.exclude_pattern}"])

    cmd.extend(["--max-count", "100"])
    cmd.append(params.query)
    cmd.append(".")

    return cmd


def _process_ripgrep_output(stdout: str) -> str:
    """處理 ripgrep 輸出並截斷至上限。

    Args:
        stdout: ripgrep 的 stdout 輸出。

    Returns:
        處理後的輸出字串。
    """
    output = stdout.strip()
    if not output:
        return "No matches found."

    lines = output.split("\n")
    if len(lines) > MAX_GREP_MATCHES:
        lines = lines[:MAX_GREP_MATCHES]
        output = "\n".join(lines)
        output += f"\n... output capped at {MAX_GREP_MATCHES} matches ..."

    return output


def _try_ripgrep(params: GrepSearchParams) -> str:
    """嘗試使用 ripgrep 執行搜尋。

    Args:
        params: grep 搜尋參數。

    Returns:
        搜尋結果字串。

    Raises:
        FileNotFoundError: ripgrep 不可用或執行失敗。
        subprocess.TimeoutExpired: 搜尋超時。
    """
    cmd = _build_ripgrep_command(params)

    result = subprocess.run(  # nosec B603
        cmd,
        cwd=params.base_dir,
        capture_output=True,
        text=True,
        timeout=GREP_TIMEOUT_SECONDS,
        check=False,
    )

    if result.returncode == 0:
        return _process_ripgrep_output(result.stdout)
    elif result.returncode == 1:
        return "No matches found."
    else:
        raise FileNotFoundError("ripgrep failed")


def grep_search_handler(params: GrepSearchParams) -> str:
    """grep_search 工具實作（使用 ripgrep 或 fallback 到 Python re）。"""
    try:
        return _try_ripgrep(params)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return _grep_search_python_fallback(params)
    except Exception as exc:
        return f"Error in grep search: {exc}"


def _grep_search_python_fallback(params: GrepSearchParams) -> str:
    """純 Python 的 grep 實作（當 ripgrep 不可用時）。"""
    # 編譯 pattern
    pattern = _compile_search_pattern(params.query, params.case_sensitive)
    if isinstance(pattern, str):
        # 編譯失敗，返回錯誤訊息
        return pattern

    matches: list[str] = []
    base_path = Path(params.base_dir)

    try:
        with _timeout_context(GREP_TIMEOUT_SECONDS):
            for filepath, rel_path in _iter_searchable_files(
                base_path, params.include_pattern, params.exclude_pattern
            ):
                remaining = MAX_GREP_MATCHES - len(matches)
                if remaining <= 0:
                    break
                file_matches = _search_in_file(filepath, pattern, rel_path, remaining)
                matches.extend(file_matches)

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


def truncate_for_context(
    text: str, max_chars: int = MAX_TOOL_RESULT_CHARS, tool_hint: str = ""
) -> str:
    """截斷過長的 tool result 以避免 context overflow。

    Args:
        text: 要截斷的文字。
        max_chars: 最大字元數。
        tool_hint: 截斷時顯示的工具提示訊息。
    """
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    hint_msg = f"\n... [truncated] ({len(text)} chars total, showing {max_chars})"
    if tool_hint:
        hint_msg += f"\n{tool_hint}"
    return truncated + hint_msg


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

# Python 危險模式（用於檢查 python -c 命令中的危險操作）
PYTHON_DANGEROUS_PATTERNS = [
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


def _is_traversal_token(token: str) -> bool:
    """檢查 token 是否為路徑穿越模式。

    Args:
        token: 待檢查的 token。

    Returns:
        True 若為路徑穿越模式。
    """
    if token in ("..", "./..", ".\\.."):
        return True
    if token.endswith("/..") or token.endswith("\\.."):
        return True
    if "/../" in token or "\\..\\" in token:
        return True
    return False


def _check_absolute_paths(tokens: list[str]) -> tuple[bool, str]:
    """檢查 tokens 中的絕對路徑是否安全。

    Args:
        tokens: 命令 tokens。

    Returns:
        (is_blocked, reason) tuple。
    """
    for token in tokens:
        if token.startswith("/"):
            if token == "/repo" or token.startswith("/repo/"):  # nosec B105
                continue
            # 阻止存取系統目錄
            return True, f"Absolute path outside /repo not allowed: {token}"
    return False, ""


def _check_blocked_patterns(command: str) -> tuple[bool, str]:
    """檢查命令中的危險模式（pipe, redirect, command substitution 等）。

    Args:
        command: 待檢查的命令字串。

    Returns:
        (is_blocked, reason) tuple。
    """
    for pattern in BASH_BLOCKED_PATTERNS:
        if re.search(pattern, command):
            if pattern == r"\|":
                return True, (
                    "Blocked pattern: pipe operator. "
                    "Use grep_search tool for pattern matching instead"
                )
            return True, f"Blocked pattern: {pattern}"
    return False, ""


def _check_path_safety(command: str, tokens: list[str]) -> tuple[bool, str]:
    """檢查路徑穿越和絕對路徑安全性。

    Args:
        command: 原始命令字串。
        tokens: 命令 tokens。

    Returns:
        (is_blocked, reason) tuple。
    """
    # 檢查路徑穿越
    if "../" in command or "..\\" in command:
        return True, "Path traversal pattern detected"

    if any(_is_traversal_token(t) for t in tokens):
        return True, "Path traversal pattern detected"

    # 檢查絕對路徑
    return _check_absolute_paths(tokens)


def _check_git_subcommand(tokens: list[str], base_cmd: str) -> tuple[bool, str]:
    """檢查 git 子命令是否在白名單中。

    Args:
        tokens: 命令 tokens。
        base_cmd: 基本命令（應為 'git'）。

    Returns:
        (is_blocked, reason) tuple。
    """
    if base_cmd != "git":
        return False, ""

    # 特殊處理 git（白名單策略：僅允許明確的 read-only 子命令）
    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        if token not in GIT_ALLOWED_SUBCOMMANDS:
            return True, f"Git subcommand not in allowlist: {token}"
        # 找到第一個非 flag 的 token 即為子命令，檢查完畢
        break

    return False, ""


def _check_python_code(tokens: list[str], base_cmd: str) -> tuple[bool, str]:
    """檢查 python -c 代碼中的危險操作。

    Args:
        tokens: 命令 tokens。
        base_cmd: 基本命令（應為 'python' 或 'python3'）。

    Returns:
        (is_blocked, reason) tuple。
    """
    if base_cmd not in ("python", "python3"):
        return False, ""

    # 特殊處理 python（僅允許 -c，且檢查危險模式）
    if len(tokens) < 3 or tokens[1] != "-c":
        return True, "Python without -c flag is not allowed (prevents script execution)"

    # 檢查 -c 中的危險模式（涵蓋所有可能的檔案修改與網路操作）
    python_code = " ".join(tokens[2:])
    for pattern, desc in PYTHON_DANGEROUS_PATTERNS:
        if re.search(pattern, python_code, re.IGNORECASE):
            return True, f"Blocked Python pattern: {desc}"

    return False, ""


def _check_command_in_arguments(tokens: list[str]) -> tuple[bool, str]:
    """檢查參數中是否藏有危險命令。

    Args:
        tokens: 命令 tokens。

    Returns:
        (is_blocked, reason) tuple。
    """
    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        token_base = os.path.basename(token)
        if token_base in BASH_BLOCKED_COMMANDS:
            return True, f"Blocked command in arguments: {token_base}"

    return False, ""


def _parse_command_tokens(command: str) -> list[str]:
    """解析命令為 tokens。

    Args:
        command: 命令字串。

    Returns:
        token 列表。
    """
    import shlex

    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _validate_command_base(base_cmd: str) -> tuple[bool, str]:
    """驗證命令基本安全性（黑白名單）。

    Args:
        base_cmd: 基本命令名稱。

    Returns:
        (is_blocked, reason) tuple。
    """
    if base_cmd in BASH_BLOCKED_COMMANDS:
        return True, f"Blocked command: {base_cmd}"

    if base_cmd not in BASH_SAFE_COMMANDS:
        return True, f"Command not in allowlist: {base_cmd}"

    return False, ""


def _validate_specialized_commands(tokens: list[str], base_cmd: str) -> tuple[bool, str]:
    """驗證特殊命令（git, python）和參數。

    Args:
        tokens: 命令 tokens。
        base_cmd: 基本命令名稱。

    Returns:
        (is_blocked, reason) tuple。
    """
    blocked, reason = _check_git_subcommand(tokens, base_cmd)
    if blocked:
        return blocked, reason

    blocked, reason = _check_python_code(tokens, base_cmd)
    if blocked:
        return blocked, reason

    return _check_command_in_arguments(tokens)


def _is_blocked_command(command: str, base_dir: str) -> tuple[bool, str]:
    """檢查命令是否違反安全規則。

    Args:
        command: 待執行的 bash 命令。
        base_dir: 命令執行的基準目錄。

    Returns:
        (is_blocked, reason) tuple。
    """
    command_stripped = command.strip()
    if not command_stripped:
        return True, "Empty command"

    # 檢查危險模式
    blocked, reason = _check_blocked_patterns(command)
    if blocked:
        return blocked, reason

    # 解析命令 tokens
    tokens = _parse_command_tokens(command)
    if not tokens:
        return True, "Empty command after parsing"

    # 檢查路徑安全
    blocked, reason = _check_path_safety(command, tokens)
    if blocked:
        return blocked, reason

    # 驗證基本命令
    base_cmd = os.path.basename(tokens[0])
    blocked, reason = _validate_command_base(base_cmd)
    if blocked:
        return blocked, reason

    # 驗證特殊命令
    return _validate_specialized_commands(tokens, base_cmd)


def _format_bash_result(result: subprocess.CompletedProcess) -> str:
    """格式化 bash 執行結果。

    Args:
        result: subprocess.CompletedProcess 物件。

    Returns:
        格式化後的輸出字串。
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

        return _format_bash_result(result)

    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {BASH_TIMEOUT_SECONDS}s"
    except Exception as exc:
        return f"Error executing command: {exc}"
