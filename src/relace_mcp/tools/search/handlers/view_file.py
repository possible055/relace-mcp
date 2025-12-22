from pathlib import Path

from ....tools.apply.file_io import decode_text_best_effort, get_project_encoding
from ....utils import MAX_FILE_SIZE_BYTES, validate_file_path
from .paths import map_repo_path


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


def _read_file_with_encoding(resolved: Path) -> str | None:
    """Read file content with project encoding support.

    Args:
        resolved: Resolved file path.

    Returns:
        File content as string, or None if file is likely binary.
    """
    raw = resolved.read_bytes()
    project_enc = get_project_encoding()
    return decode_text_best_effort(
        raw,
        path=resolved,
        preferred_encoding=project_enc,
        errors="replace",
    )


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

    if result_lines and end_idx < len(lines):
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

        content = _read_file_with_encoding(resolved)
        if content is None:
            return "Error: File appears to be binary and cannot be viewed as text."
        lines = content.splitlines()

        start_idx, end_idx = _parse_view_range(view_range, len(lines))
        return _format_file_lines(lines, start_idx, end_idx)

    except Exception as exc:
        return f"Error reading file: {exc}"
