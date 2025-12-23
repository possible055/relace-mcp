import re
import subprocess  # nosec B404
from collections.abc import Iterator
from contextlib import AbstractContextManager
from pathlib import Path

from ....tools.apply.file_io import decode_text_best_effort, get_project_encoding
from ..schemas import GrepSearchParams
from .constants import GREP_TIMEOUT_SECONDS, MAX_GREP_DEPTH, MAX_GREP_MATCHES


def _timeout_context(seconds: int) -> "AbstractContextManager[None]":
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
    def timeout_impl() -> Iterator[None]:
        if is_main_thread and hasattr(signal, "SIGALRM"):
            # Main thread on Unix: use signal.alarm
            def handler(signum: int, frame: object) -> None:
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


def _compile_search_pattern(query: str, case_sensitive: bool) -> re.Pattern[str] | str:
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
) -> Iterator[tuple[Path, Path]]:
    """Generate file paths matching filter conditions.

    Args:
        base_path: Search starting point.
        include_pattern: Filename include pattern (fnmatch).
        exclude_pattern: Filename exclude pattern (fnmatch).

    Yields:
        (filepath, rel_path) tuple.
    """
    import os

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


def _read_file_with_encoding(filepath: Path) -> str | None:
    """Read file content with project encoding support.

    Args:
        filepath: File path.

    Returns:
        File content as string, or None if read fails.
    """
    try:
        raw = filepath.read_bytes()
    except OSError:
        return None

    project_enc = get_project_encoding()
    return decode_text_best_effort(
        raw,
        path=filepath,
        preferred_encoding=project_enc,
        errors="ignore",
    )


def _search_in_file(
    filepath: Path,
    pattern: re.Pattern[str],
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

    content = _read_file_with_encoding(filepath)
    if content is None:
        return []

    matches: list[str] = []
    for line_num, line in enumerate(content.splitlines(), 1):
        if pattern.search(line):
            matches.append(f"{rel_path}:{line_num}:{line}")
            if len(matches) >= limit:
                break

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
    cmd.append("--")
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
    project_enc = get_project_encoding()
    if project_enc and project_enc.lower() not in {"utf-8", "utf-8-sig", "ascii", "us-ascii"}:
        # For regional-encoding projects (e.g., GBK/Big5), force rg to decode correctly.
        cmd.insert(1, f"--encoding={project_enc.lower()}")
    elif params.query.isascii():
        # For ASCII queries, allow searching through non-UTF-8 files safely.
        cmd.insert(1, "--text")

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
        # Non-ASCII patterns cannot be reliably matched across unknown legacy encodings via rg.
        # Fall back to per-file decoding to support GBK/Big5 mixed repos.
        if get_project_encoding() is None and not params.query.isascii():
            return _grep_search_python_fallback(params)
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
