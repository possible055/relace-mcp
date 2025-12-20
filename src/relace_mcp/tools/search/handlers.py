import os
import re
import subprocess  # nosec B404
from collections import deque
from functools import lru_cache
from pathlib import Path
from typing import Any

from ...utils import MAX_FILE_SIZE_BYTES, resolve_repo_path, validate_file_path
from .schemas import GrepSearchParams

# Directory listing limit
MAX_DIR_ITEMS = 250
# glob result limit
MAX_GLOB_MATCHES = 250
# glob max traversal depth
MAX_GLOB_DEPTH = 25
# grep result limit
MAX_GREP_MATCHES = 50
# grep timeout (seconds)
GREP_TIMEOUT_SECONDS = 30
# Python fallback grep max depth
MAX_GREP_DEPTH = 10
# Context truncation: max chars per tool result (by tool type)
MAX_TOOL_RESULT_CHARS = 50000  # default limit for truncate_for_context
MAX_VIEW_FILE_CHARS = 20000
MAX_GREP_SEARCH_CHARS = 12000
MAX_BASH_CHARS = 15000
MAX_VIEW_DIRECTORY_CHARS = 8000
MAX_GLOB_CHARS = 8000


def _timeout_context(seconds: int):
    """Simple timeout context manager.

    - Main thread (Unix): uses signal.alarm for preemptive timeout
    - Non-main thread or Windows: no native timeout support, caller must
      implement manual timeout checks using time.monotonic()

    Args:
        seconds: Timeout in seconds.

    Yields:
        None

    Raises:
        TimeoutError: When operation times out (main thread + Unix only).
    """
    import signal
    import threading
    from contextlib import contextmanager

    is_main_thread = threading.current_thread() is threading.main_thread()

    @contextmanager
    def timeout_impl():
        if is_main_thread and hasattr(signal, "SIGALRM"):
            # Main thread on Unix: use signal.alarm
            def handler(signum, frame):
                raise TimeoutError(f"Operation timed out after {seconds}s")

            old_handler = signal.signal(signal.SIGALRM, handler)
            signal.alarm(seconds)
            try:
                yield
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        else:
            # Non-main thread or Windows: no native timeout support
            # Caller must implement manual timeout checks
            yield

    return timeout_impl()


def map_repo_path(path: str, base_dir: str) -> str:
    """Map /repo/... virtual root path to actual filesystem path.

    This function is for INTERNAL use only - translating paths from Relace Search API
    which uses /repo as the virtual repository root.

    External API (fast_apply, fast_search results) now uses absolute paths.

    Args:
        path: Path from Relace API, format: /repo or /repo/...
        base_dir: Actual repo root directory.

    Returns:
        Actual filesystem absolute path.
    """
    try:
        return resolve_repo_path(path, base_dir)
    except ValueError:
        # Fallback: return original path, let validate_file_path handle error
        return path


def _validate_file_for_view(resolved: Path, path: str) -> str | None:
    """Validate if file is readable.

    Args:
        resolved: Resolved file path.
        path: Original request path.

    Returns:
        Error message (if there's a problem), otherwise None.
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
    """Parse and normalize view_range.

    Args:
        view_range: [start, end] range.
        total_lines: Total lines in file.

    Returns:
        (start_idx, end_idx) 0-indexed range.
    """
    start = view_range[0] if len(view_range) > 0 else 1
    end = view_range[1] if len(view_range) > 1 else 100

    if end == -1:
        end = total_lines

    start_idx = max(0, start - 1)
    end_idx = min(total_lines, end)

    return start_idx, end_idx


def _format_file_lines(lines: list[str], start_idx: int, end_idx: int) -> str:
    """Format file lines (with line numbers).

    Args:
        lines: All file lines.
        start_idx: Start index (0-indexed).
        end_idx: End index (0-indexed).

    Returns:
        Formatted content string.
    """
    result_lines = [f"{idx + 1} {lines[idx]}" for idx in range(start_idx, end_idx)]
    result = "\n".join(result_lines)

    if end_idx < len(lines):
        result += "\n... rest of file truncated ..."

    return result


def view_file_handler(path: str, view_range: list[int], base_dir: str) -> str:
    """view_file tool implementation."""
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
    """Remove './' prefix from path.

    Args:
        path_str: Path string.

    Returns:
        Path string with prefix removed.
    """
    return path_str[2:] if path_str.startswith("./") else path_str


def _collect_entries(
    current_abs: Path,
    include_hidden: bool,
) -> tuple[list[tuple[str, Path]], list[tuple[str, Path]]]:
    """Collect files and subdirectories in directory.

    Args:
        current_abs: Current directory absolute path.
        include_hidden: Whether to include hidden files.

    Returns:
        (files_list, dirs_list) tuple, each list contains (name, Path) tuples.
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
    """BFS collect directory items.

    Args:
        resolved: Directory absolute path.
        include_hidden: Whether to include hidden files.

    Returns:
        (items, truncated) tuple, items is item list, truncated indicates if output was truncated.
    """
    items: list[str] = []
    queue: deque[tuple[Path, Path]] = deque()
    queue.append((resolved, Path(".")))

    while queue and len(items) < MAX_DIR_ITEMS:
        current_abs, current_rel = queue.popleft()
        files_list, dirs_list = _collect_entries(current_abs, include_hidden)

        # List current level files first
        for name, _ in files_list:
            if len(items) >= MAX_DIR_ITEMS:
                break
            rel_path = current_rel / name
            items.append(_strip_dot_prefix(str(rel_path)))

        # List subdirectories and add to queue
        for name, entry in dirs_list:
            if len(items) >= MAX_DIR_ITEMS:
                break
            rel_path = current_rel / name
            items.append(_strip_dot_prefix(str(rel_path)) + "/")
            queue.append((entry, rel_path))

    truncated = len(items) >= MAX_DIR_ITEMS
    return items, truncated


def view_directory_handler(path: str, include_hidden: bool, base_dir: str) -> str:
    """view_directory tool implementation (BFS-like order: list current level first, then recurse)."""
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


def _normalize_glob_pattern(pattern: str) -> tuple[str, bool] | tuple[None, bool]:
    """Normalize a glob pattern and detect directory-only matching."""
    pattern = pattern.strip()
    if not pattern:
        return None, False

    pattern = pattern.replace("\\", "/")

    # Be forgiving: allow patterns that mistakenly include the /repo prefix.
    if pattern.startswith("/repo/"):
        pattern = pattern[6:].lstrip("/")
    elif pattern.startswith("/repo"):
        pattern = pattern[5:].lstrip("/")

    if pattern.startswith(("~", "/")):
        return None, False

    if pattern.startswith("./"):
        pattern = pattern[2:]

    # Block traversal like ../, /../, trailing /.., etc.
    if pattern == ".." or pattern.startswith("../") or pattern.endswith("/..") or "/../" in pattern:
        return None, False

    dir_only = pattern.endswith("/")
    if dir_only:
        pattern = pattern.rstrip("/")

    if not pattern:
        return None, False

    return pattern, dir_only


def _match_glob_segments(pattern_segments: tuple[str, ...], path_segments: tuple[str, ...]) -> bool:
    """Match a path against a segment-wise glob pattern (supports **)."""

    @lru_cache(maxsize=8192)
    def _match(pi: int, si: int) -> bool:
        if pi == len(pattern_segments):
            return si == len(path_segments)

        pat = pattern_segments[pi]
        if pat == "**":
            # Try matching zero segments
            if _match(pi + 1, si):
                return True
            # Or consume one segment and try again
            return si < len(path_segments) and _match(pi, si + 1)

        if si >= len(path_segments):
            return False

        import fnmatch

        if not fnmatch.fnmatchcase(path_segments[si], pat):
            return False

        return _match(pi + 1, si + 1)

    return _match(0, 0)


def glob_handler(
    pattern: str,
    path: str,
    include_hidden: bool,
    max_results: int,
    base_dir: str,
) -> str:
    """glob tool implementation (recursive file/directory matching)."""
    try:
        normalized, dir_only = _normalize_glob_pattern(pattern)
        if not normalized:
            return (
                "Error: Invalid glob pattern. Use a relative pattern without '..' or leading '/'."
            )

        fs_path = map_repo_path(path, base_dir)
        resolved = validate_file_path(fs_path, base_dir, allow_empty=True)

        if not resolved.exists():
            return f"Error: Directory not found: {path}"
        if not resolved.is_dir():
            return f"Error: Not a directory: {path}"

        try:
            requested_max = int(max_results)
        except (TypeError, ValueError):
            requested_max = MAX_GLOB_MATCHES

        if requested_max <= 0:
            requested_max = MAX_GLOB_MATCHES
        requested_max = min(requested_max, MAX_GLOB_MATCHES)

        pattern_has_sep = "/" in normalized
        pattern_segments = tuple(seg for seg in normalized.split("/") if seg)

        matches: list[str] = []
        stop = False

        for root, dirs, files in os.walk(resolved, followlinks=False):
            rel_root = Path(root).relative_to(resolved)
            if len(rel_root.parts) >= MAX_GLOB_DEPTH:
                dirs.clear()
                continue

            if not include_hidden:
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                files = [f for f in files if not f.startswith(".")]

            dirs.sort()
            files.sort()

            # Match directories (only when pattern ends with '/')
            if dir_only:
                for dname in dirs:
                    rel_path = rel_root / dname
                    rel_posix = rel_path.as_posix()
                    if pattern_has_sep:
                        ok = _match_glob_segments(pattern_segments, tuple(rel_posix.split("/")))
                    else:
                        import fnmatch

                        ok = fnmatch.fnmatchcase(dname, normalized)
                    if ok:
                        matches.append(rel_posix + "/")
                        if len(matches) >= requested_max:
                            stop = True
                            break

            if stop:
                break

            # Match files
            if dir_only:
                continue

            for fname in files:
                rel_path = rel_root / fname
                rel_posix = rel_path.as_posix()
                if pattern_has_sep:
                    ok = _match_glob_segments(pattern_segments, tuple(rel_posix.split("/")))
                else:
                    import fnmatch

                    ok = fnmatch.fnmatchcase(fname, normalized)

                if ok:
                    matches.append(rel_posix)
                    if len(matches) >= requested_max:
                        stop = True
                        break

            if stop:
                break

        if not matches:
            return "No matches found."

        result = "\n".join(matches)
        if stop:
            result += f"\n... output truncated at {requested_max} matches ..."

        return result

    except Exception as exc:
        return f"Error in glob: {exc}"


def _exceeds_max_depth(root: Path, base_path: Path, max_depth: int) -> bool:
    """Check if directory depth exceeds limit.

    Args:
        root: Current directory path.
        base_path: Base directory path.
        max_depth: Maximum depth.

    Returns:
        True if depth exceeds limit.
    """
    try:
        depth = len(Path(root).relative_to(base_path).parts)
    except ValueError:
        depth = 0
    return depth >= max_depth


def _matches_file_patterns(
    filename: str, include_pattern: str | None, exclude_pattern: str | None
) -> bool:
    """Check if filename matches include/exclude patterns.

    Args:
        filename: File name.
        include_pattern: include pattern (fnmatch format).
        exclude_pattern: exclude pattern (fnmatch format).

    Returns:
        True if file matches conditions.
    """
    import fnmatch

    if include_pattern and not fnmatch.fnmatch(filename, include_pattern):
        return False
    if exclude_pattern and fnmatch.fnmatch(filename, exclude_pattern):
        return False
    return True


def _compile_search_pattern(query: str, case_sensitive: bool) -> re.Pattern | str:
    """Compile regex pattern.

    Args:
        query: Search pattern.
        case_sensitive: Whether case sensitive.

    Returns:
        Compiled Pattern, or error message string.
    """
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        return re.compile(query, flags)
    except re.error as exc:
        return f"Invalid regex pattern: {exc}"


def _filter_visible_dirs(dirs: list[str]) -> list[str]:
    """Filter out hidden directories.

    Args:
        dirs: Directory name list.

    Returns:
        Visible directory list.
    """
    return [d for d in dirs if not d.startswith(".")]


def _is_searchable_file(
    filename: str, include_pattern: str | None, exclude_pattern: str | None
) -> bool:
    """Determine if file should be searched.

    Args:
        filename: File name.
        include_pattern: include pattern.
        exclude_pattern: exclude pattern.

    Returns:
        True if file should be searched.
    """
    if filename.startswith("."):
        return False
    return _matches_file_patterns(filename, include_pattern, exclude_pattern)


def _iter_searchable_files(
    base_path: Path,
    include_pattern: str | None,
    exclude_pattern: str | None,
):
    """Generate file paths matching filter conditions.

    Args:
        base_path: Search starting point.
        include_pattern: Filename include pattern (fnmatch).
        exclude_pattern: Filename exclude pattern (fnmatch).

    Yields:
        (filepath, rel_path) tuple.
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
    """Search single file and return match list.

    Args:
        filepath: File absolute path.
        pattern: Compiled regex pattern.
        rel_path: File relative path (for output).
        limit: Maximum matches to return (for global cap).

    Returns:
        Match list, format "rel_path:line_num:line".
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
    """Build ripgrep command list.

    Args:
        params: grep search parameters.

    Returns:
        ripgrep command list.
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
    """Process ripgrep output and truncate to limit.

    Args:
        stdout: ripgrep stdout output.

    Returns:
        Processed output string.
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
    """Try to execute search using ripgrep.

    Args:
        params: grep search parameters.

    Returns:
        Search result string.

    Raises:
        FileNotFoundError: ripgrep not available or execution failed.
        subprocess.TimeoutExpired: Search timed out.
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
    """grep_search tool implementation (uses ripgrep or fallback to Python re)."""
    try:
        return _try_ripgrep(params)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return _grep_search_python_fallback(params)
    except Exception as exc:
        return f"Error in grep search: {exc}"


def _grep_search_python_fallback(params: GrepSearchParams) -> str:
    """Pure Python grep implementation (when ripgrep not available)."""
    import time

    # Compile pattern
    pattern = _compile_search_pattern(params.query, params.case_sensitive)
    if isinstance(pattern, str):
        # Compilation failed, return error message
        return pattern

    matches: list[str] = []
    base_path = Path(params.base_dir)
    start_time = time.monotonic()

    try:
        with _timeout_context(GREP_TIMEOUT_SECONDS):
            for filepath, rel_path in _iter_searchable_files(
                base_path, params.include_pattern, params.exclude_pattern
            ):
                # Manual timeout check for non-main thread (where signal.alarm doesn't work)
                if time.monotonic() - start_time > GREP_TIMEOUT_SECONDS:
                    raise TimeoutError(f"Operation timed out after {GREP_TIMEOUT_SECONDS}s")

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
    """report_back tool implementation, returns structured result directly."""
    return {
        "explanation": explanation,
        "files": files,
    }


def truncate_for_context(
    text: str, max_chars: int = MAX_TOOL_RESULT_CHARS, tool_hint: str = ""
) -> str:
    """Truncate overly long tool result to avoid context overflow.

    Args:
        text: Text to truncate.
        max_chars: Maximum characters.
        tool_hint: Tool hint message shown when truncated.
    """
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    hint_msg = f"\n... [truncated] ({len(text)} chars total, showing {max_chars})"
    if tool_hint:
        hint_msg += f"\n{tool_hint}"
    return truncated + hint_msg


def estimate_context_size(messages: list[dict[str, Any]]) -> int:
    """Estimate total character count of messages."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(content)
        # tool_calls also take space
        tool_calls = msg.get("tool_calls", [])
        for tc in tool_calls:
            func = tc.get("function", {})
            total += len(func.get("arguments", ""))
    return total


# === Bash Tool ===
# NOTE: Unix-only (requires bash shell, not available on Windows)

BASH_TIMEOUT_SECONDS = 30
BASH_MAX_OUTPUT_CHARS = 50000

# Block dangerous commands (blacklist)
BASH_BLOCKED_COMMANDS = frozenset(
    {
        # File modification
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
        # Network access
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
        # Privilege escalation
        "sudo",
        "su",
        "doas",
        "pkexec",
        # Process control
        "kill",
        "killall",
        "pkill",
        # System administration
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
        # Dangerous tools
        "dd",
        "eval",
        "exec",
        "source",
        # Package management (may trigger network/ installation)
        "make",
        "cmake",
        "ninja",
        "cargo",
        "npm",
        "pip",
        "pip3",
    }
)


# Block dangerous patterns (prevent bypass)
BASH_BLOCKED_PATTERNS = [
    r">\s*[^&]",  # Redirect write
    r">>\s*",  # Append write
    r"\|",  # Pipe (may bypass restrictions)
    r"`",  # Command substitution
    r"\$\(",  # Command substitution
    r";\s*\w",  # Command chaining
    r"&&",  # Conditional execution
    r"\|\|",  # Conditional execution
    r"-exec\b",  # find -exec (may execute dangerous commands)
    r"-delete\b",  # find -delete
    r"\bsed\b.*-i",  # sed in-place edit
]

# Git allowed read-only subcommands (whitelist strategy)
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

# Allowed read commands (whitelist: block unknown commands)
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

# Python dangerous patterns (check dangerous operations in python -c commands)
PYTHON_DANGEROUS_PATTERNS = [
    # File operations
    (r"open\s*\(", "file operations"),
    (r"\bwrite\s*\(", "write operations"),
    (r"\bremove\s*\(", "file removal"),
    (r"\bunlink\s*\(", "file removal"),
    (r"\brmdir\s*\(", "directory removal"),
    (r"\brename\s*\(", "file rename"),
    (r"\bmkdir\s*\(", "directory creation"),
    (r"\bchmod\s*\(", "permission change"),
    (r"\bchown\s*\(", "ownership change"),
    # Module imports (dangerous)
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
    # Network operations
    (r"urllib", "network access"),
    (r"requests\.", "network access"),
    (r"http\.client", "network access"),
    (r"http\.server", "network access"),
    (r"socket", "network access"),
    # Dangerous built-in functions
    (r"\beval\s*\(", "eval"),
    (r"\bexec\s*\(", "exec"),
    (r"__import__", "__import__"),
    (r"compile\s*\(", "compile"),
]


def _is_traversal_token(token: str) -> bool:
    """Check if token is a path traversal pattern.

    Args:
        token: Token to check.

    Returns:
        True if it's a path traversal pattern.
    """
    if token in ("..", "./..", ".\\.."):
        return True
    if token.endswith("/..") or token.endswith("\\.."):
        return True
    if "/../" in token or "\\..\\" in token:
        return True
    return False


def _check_absolute_paths(tokens: list[str]) -> tuple[bool, str]:
    """Check if absolute paths in tokens are safe.

    Args:
        tokens: Command tokens.

    Returns:
        (is_blocked, reason) tuple.
    """
    for token in tokens:
        if token.startswith("/"):
            if token == "/repo" or token.startswith("/repo/"):  # nosec B105
                continue
            # Block access to system directories
            return True, f"Absolute path outside /repo not allowed: {token}"
    return False, ""


def _check_blocked_patterns(command: str) -> tuple[bool, str]:
    """Check for dangerous patterns in command (pipe, redirect, command substitution, etc.).

    Args:
        command: Command string to check.

    Returns:
        (is_blocked, reason) tuple.
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
    """Check path traversal and absolute path safety.

    Args:
        command: Original command string.
        tokens: Command tokens.

    Returns:
        (is_blocked, reason) tuple.
    """
    # Check path traversal
    if "../" in command or "..\\" in command:
        return True, "Path traversal pattern detected"

    if any(_is_traversal_token(t) for t in tokens):
        return True, "Path traversal pattern detected"

    # Check absolute paths
    return _check_absolute_paths(tokens)


def _check_git_subcommand(tokens: list[str], base_cmd: str) -> tuple[bool, str]:
    """Check if git subcommand is in whitelist.

    Args:
        tokens: Command tokens.
        base_cmd: Base command (should be 'git').

    Returns:
        (is_blocked, reason) tuple.
    """
    if base_cmd != "git":
        return False, ""

    # Special handling for git (whitelist strategy: only allow explicit read-only subcommands)
    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        if token not in GIT_ALLOWED_SUBCOMMANDS:
            return True, f"Git subcommand not in allowlist: {token}"
        # Found first non-flag token which is the subcommand, check complete
        break

    return False, ""


def _check_python_code(tokens: list[str], base_cmd: str) -> tuple[bool, str]:
    """Check for dangerous operations in python -c code.

    Args:
        tokens: Command tokens.
        base_cmd: Base command (should be 'python' or 'python3').

    Returns:
        (is_blocked, reason) tuple.
    """
    if base_cmd not in ("python", "python3"):
        return False, ""

    # Special handling for python (only allow -c, and check dangerous patterns)
    if len(tokens) < 3 or tokens[1] != "-c":
        return True, "Python without -c flag is not allowed (prevents script execution)"

    # Check dangerous patterns in -c code (covers all possible file modification and network operations)
    python_code = " ".join(tokens[2:])
    for pattern, desc in PYTHON_DANGEROUS_PATTERNS:
        if re.search(pattern, python_code, re.IGNORECASE):
            return True, f"Blocked Python pattern: {desc}"

    return False, ""


def _check_command_in_arguments(tokens: list[str]) -> tuple[bool, str]:
    """Check if dangerous commands are hidden in arguments.

    Args:
        tokens: Command tokens.

    Returns:
        (is_blocked, reason) tuple.
    """
    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        token_base = os.path.basename(token)
        if token_base in BASH_BLOCKED_COMMANDS:
            return True, f"Blocked command in arguments: {token_base}"

    return False, ""


def _parse_command_tokens(command: str) -> list[str]:
    """Parse command into tokens.

    Args:
        command: Command string.

    Returns:
        Token list.
    """
    import shlex

    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _validate_command_base(base_cmd: str) -> tuple[bool, str]:
    """Validate command base security (blacklist/whitelist).

    Args:
        base_cmd: Base command name.

    Returns:
        (is_blocked, reason) tuple.
    """
    if base_cmd in BASH_BLOCKED_COMMANDS:
        return True, f"Blocked command: {base_cmd}"

    if base_cmd not in BASH_SAFE_COMMANDS:
        return True, f"Command not in allowlist: {base_cmd}"

    return False, ""


def _validate_specialized_commands(tokens: list[str], base_cmd: str) -> tuple[bool, str]:
    """Validate specialized commands (git, python) and arguments.

    Args:
        tokens: Command tokens.
        base_cmd: Base command name.

    Returns:
        (is_blocked, reason) tuple.
    """
    blocked, reason = _check_git_subcommand(tokens, base_cmd)
    if blocked:
        return blocked, reason

    blocked, reason = _check_python_code(tokens, base_cmd)
    if blocked:
        return blocked, reason

    return _check_command_in_arguments(tokens)


def _is_blocked_command(command: str, base_dir: str) -> tuple[bool, str]:
    """Check if command violates security rules.

    Args:
        command: Bash command to execute.
        base_dir: Base directory for command execution.

    Returns:
        (is_blocked, reason) tuple.
    """
    command_stripped = command.strip()
    if not command_stripped:
        return True, "Empty command"

    # Check dangerous patterns
    blocked, reason = _check_blocked_patterns(command)
    if blocked:
        return blocked, reason

    # Parse command tokens
    tokens = _parse_command_tokens(command)
    if not tokens:
        return True, "Empty command after parsing"

    # Check path safety
    blocked, reason = _check_path_safety(command, tokens)
    if blocked:
        return blocked, reason

    # Validate base command
    base_cmd = os.path.basename(tokens[0])
    blocked, reason = _validate_command_base(base_cmd)
    if blocked:
        return blocked, reason

    # Validate specialized commands
    return _validate_specialized_commands(tokens, base_cmd)


def _format_bash_result(result: subprocess.CompletedProcess) -> str:
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
                translated.append(
                    resolve_repo_path(token, base_dir, allow_relative=False, allow_absolute=False)
                )
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
        result = subprocess.run(  # nosec B603 B602 B607
            ["bash", "-c", translated_command],
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
