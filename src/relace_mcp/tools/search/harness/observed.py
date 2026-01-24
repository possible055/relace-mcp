import logging
import re
from typing import TYPE_CHECKING, Any

from ....utils import resolve_repo_path

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ....config import RelaceConfig


class ObservedFilesMixin:
    _config: "RelaceConfig"
    _observed_files: dict[str, list[list[int]]]
    _view_line_re: re.Pattern[str]

    def _record_grep_results(self, grep_output: str) -> None:
        """Parse grep output and record to observed_files.

        Grep output format: path:line:content
        Note: grep output paths are relative to base_dir, converted to absolute paths.
        Handles filenames containing colons by parsing from the end of path segment.
        """
        for line in grep_output.split("\n"):
            if not line:
                continue

            # Find the pattern ":line_number:" from the right side to handle colons in filenames
            # We look for the last occurrence of :digits: pattern
            match = None
            search_pos = len(line) - 1

            while search_pos > 0:
                # Find the last colon
                colon_pos = line.rfind(":", 0, search_pos)
                if colon_pos <= 0:
                    break

                # Check if there's a number before this colon
                prev_colon = line.rfind(":", 0, colon_pos)
                if prev_colon < 0:
                    break

                potential_num = line[prev_colon + 1 : colon_pos]
                if potential_num.isdigit():
                    # Found :digits: pattern, path is everything before prev_colon
                    rel_path = line[:prev_colon]
                    line_num = int(potential_num)
                    match = (rel_path, line_num)
                    break

                search_pos = colon_pos

            if not match:
                # Fallback to original pattern for compatibility
                m = re.match(r"^([^:]+):(\d+):", line)
                if m:
                    match = (m.group(1), int(m.group(2)))

            if match:
                rel_path, line_num = match
                # Normalize path format: remove ./ prefix
                if rel_path.startswith("./"):
                    rel_path = rel_path[2:]
                # Convert to absolute path
                abs_path = self._to_absolute_path(rel_path)
                if not abs_path:
                    # Defense-in-depth: ignore any path that escapes base_dir.
                    continue

                if abs_path not in self._observed_files:
                    self._observed_files[abs_path] = []
                # Record single-line range
                self._observed_files[abs_path].append([line_num, line_num])

    def _merge_observed_ranges(self) -> dict[str, list[list[int]]]:
        """Merge and deduplicate ranges in observed_files.

        Adjacent or overlapping ranges are merged, max 20 segments per file.
        """
        max_ranges_per_file = 20
        max_total_files = 50
        merged: dict[str, list[list[int]]] = {}

        # Sort by number of ranges, prioritize files with more ranges
        sorted_files = sorted(
            self._observed_files.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )[:max_total_files]

        for path, ranges in sorted_files:
            if not ranges:
                continue

            # Sort and merge adjacent/overlapping ranges
            sorted_ranges = sorted(ranges, key=lambda r: r[0])
            merged_ranges: list[list[int]] = []

            for r in sorted_ranges:
                if not merged_ranges:
                    merged_ranges.append(r[:])
                else:
                    last = merged_ranges[-1]
                    # Merge if adjacent or overlapping (allow 1-line gap)
                    if r[0] <= last[1] + 2:
                        last[1] = max(last[1], r[1])
                    else:
                        merged_ranges.append(r[:])

            # Limit ranges per file
            merged[path] = merged_ranges[:max_ranges_per_file]

        return merged

    def _extract_view_file_range(self, output: str) -> list[int] | None:
        """Parse actual line range from view_file output.

        view_file_handler output starts each line with "<line_number> <content>".
        Returns None if parsing fails (e.g., view_range out of file bounds produces no numbered lines).
        """
        start: int | None = None
        end: int | None = None
        for line in output.splitlines():
            match = self._view_line_re.match(line)
            if not match:
                continue
            line_no = int(match.group(1))
            if start is None:
                start = line_no
            end = line_no
        if start is None or end is None:
            return None
        return [start, end]

    def _to_absolute_path(self, path: str) -> str | None:
        """Convert any path format to absolute filesystem path.

        Handles: /repo/..., relative paths, and already-absolute paths.
        """
        base_dir = self._config.base_dir
        if base_dir is None:
            return None
        try:
            return resolve_repo_path(
                path,
                base_dir,
                require_within_base_dir=True,
            )
        except ValueError:
            # Invalid or escaping paths are ignored by callers
            return None

    def _normalize_view_path(self, raw_path: Any) -> str | None:
        """Convert /repo/... path to absolute filesystem path.

        Used to record observed files with absolute paths for the final report.
        Returns None if the path format is invalid or escapes base_dir.
        """
        if not isinstance(raw_path, str):
            return None
        if not raw_path.startswith("/repo"):
            return None
        base_dir = self._config.base_dir
        if base_dir is None:
            return None
        try:
            return resolve_repo_path(raw_path, base_dir, allow_relative=False, allow_absolute=False)
        except ValueError:
            return None

    def _normalize_report_files(
        self, files: dict[str, list[list[int]]]
    ) -> dict[str, list[list[int]]]:
        """Normalize report_back file paths to absolute paths."""

        def _normalize_ranges(raw: Any) -> list[list[int]]:
            if not isinstance(raw, list):
                return []
            normalized_ranges: list[list[int]] = []
            for r in raw:
                if (
                    isinstance(r, (list, tuple))
                    and len(r) == 2
                    and isinstance(r[0], int)
                    and isinstance(r[1], int)
                ):
                    start, end = r[0], r[1]
                    if start > 0 and end >= start:
                        normalized_ranges.append([start, end])
            return normalized_ranges

        if not isinstance(files, dict):
            return {}
        normalized: dict[str, list[list[int]]] = {}
        for path, ranges in files.items():
            resolved = self._to_absolute_path(path)
            if not resolved:
                logger.warning("Filtered out invalid path from report_back: %s", path)
                continue
            validated_ranges = _normalize_ranges(ranges)
            if not validated_ranges:
                continue
            normalized.setdefault(resolved, []).extend(validated_ranges)
        return normalized

    def _maybe_record_observed(
        self, name: str, args: dict[str, Any], result: str | dict[str, Any]
    ) -> None:
        """Accumulate observed_files based on tool results (for partial report use)."""
        if not isinstance(result, str) or result.startswith("Error:"):
            return

        if name == "view_file":
            normalized_path = self._normalize_view_path(args.get("path"))
            if not normalized_path:
                return
            line_range = self._extract_view_file_range(result)
            if not line_range:
                return
            self._observed_files.setdefault(normalized_path, []).append(line_range)
            return

        if name == "grep_search":
            self._record_grep_results(result)
