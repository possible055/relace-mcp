import os
from functools import lru_cache
from pathlib import Path

from ....utils import validate_file_path
from .constants import MAX_GLOB_DEPTH, MAX_GLOB_MATCHES
from .paths import map_repo_path


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
