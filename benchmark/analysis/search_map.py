import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .trace_artifacts import collect_trace_artifacts, load_trace_meta, load_trace_turns

_GREP_LINE_RE = re.compile(r"^(?P<path>.+?):(?P<line>\d+):")
_LSP_SYMBOL_RE = re.compile(
    r"^\[(?P<kind>[^\]]+)\]\s+(?P<path>.+?):(?P<line>\d+):(?P<column>\d+)(?:\s|$)"
)
_VIEW_LINE_RE = re.compile(r"^(?P<line>\d+)\s")


@dataclass
class FileAccessEvent:
    turn: int
    tool_name: str
    access_type: str  # read | discover | grep_hit | select | lsp_nav | lsp_search
    path: str
    lines: tuple[int, int] | None = None
    is_success: bool = True
    latency_ms: float = 0.0


@dataclass
class SearchMap:
    case_id: str
    total_turns: int
    events: list[FileAccessEvent] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def semantic_hints(self) -> list[dict[str, Any]]:
        raw_hints = self.meta.get("semantic_hints")
        if not isinstance(raw_hints, list):
            return []

        hints: list[dict[str, Any]] = []
        for item in raw_hints:
            if not isinstance(item, dict):
                continue
            filename = _normalize_repo_path(item.get("filename", ""))
            if filename == ".":
                continue
            raw_score = item.get("score", 0.0)
            try:
                score = float(raw_score)
            except (TypeError, ValueError):
                score = 0.0
            hints.append({"filename": filename, "score": score})
        return hints

    @property
    def semantic_hints_files(self) -> list[str]:
        return [item["filename"] for item in self.semantic_hints]

    @property
    def semantic_hints_count(self) -> int:
        return len(self.semantic_hints)

    @property
    def unique_files(self) -> set[str]:
        return {e.path for e in self.events if _is_file_path(e.path)}

    @property
    def files_by_tool(self) -> dict[str, set[str]]:
        result: dict[str, set[str]] = {}
        for e in self.events:
            result.setdefault(e.tool_name, set()).add(e.path)
        return result

    @property
    def files_by_access_type(self) -> dict[str, set[str]]:
        result: dict[str, set[str]] = {}
        for e in self.events:
            result.setdefault(e.access_type, set()).add(e.path)
        return result

    @property
    def selected_files(self) -> set[str]:
        return {e.path for e in self.events if e.access_type == "select" and _is_file_path(e.path)}

    def incremental_recall(self, ground_truth_files: set[str]) -> list[tuple[int, float]]:
        if not ground_truth_files:
            return []

        seen: set[str] = set()
        recall_curve: list[tuple[int, float]] = []
        last_turn = 0
        for e in self.events:
            if e.turn != last_turn:
                if last_turn > 0:
                    hit = len(seen & ground_truth_files)
                    recall_curve.append((last_turn, hit / len(ground_truth_files)))
                last_turn = e.turn
            if _is_file_path(e.path):
                seen.add(e.path)
        if last_turn > 0:
            hit = len(seen & ground_truth_files)
            recall_curve.append((last_turn, hit / len(ground_truth_files)))
        return recall_curve

    def first_hit_turns(self, ground_truth_files: set[str]) -> dict[str, int]:
        result: dict[str, int] = {}
        for e in self.events:
            if e.path in ground_truth_files and e.path not in result:
                result[e.path] = e.turn
        return result

    def wasted_reads(self) -> set[str]:
        read_files = {
            e.path for e in self.events if e.access_type == "read" and _is_file_path(e.path)
        }
        return read_files - self.selected_files

    def files_per_turn(self) -> dict[int, int]:
        seen_before: set[str] = set()
        turn_new: dict[int, int] = {}
        for e in self.events:
            if not _is_file_path(e.path):
                continue
            if e.path not in seen_before:
                turn_new[e.turn] = turn_new.get(e.turn, 0) + 1
                seen_before.add(e.path)
        return turn_new

    def tool_transition_sequence(self) -> list[str]:
        return [e.tool_name for e in self.events]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "total_turns": self.total_turns,
            "unique_files_count": len(self.unique_files),
            "events_count": len(self.events),
            "files_by_tool": {k: sorted(v) for k, v in self.files_by_tool.items()},
            "files_by_access_type": {k: sorted(v) for k, v in self.files_by_access_type.items()},
            "selected_files": sorted(self.selected_files),
            "wasted_reads": sorted(self.wasted_reads()),
            "files_per_turn": self.files_per_turn(),
            "semantic_hints_count": self.semantic_hints_count,
            "semantic_hints_files": self.semantic_hints_files,
            "semantic_hints": self.semantic_hints,
            "meta": self.meta,
        }


# ---------------------------------------------------------------------------
# Path normalization helpers
# ---------------------------------------------------------------------------


def _is_file_path(path: str) -> bool:
    return bool(path) and path != "." and not path.endswith("/")


def _normalize_repo_path(path: Any) -> str:
    if not isinstance(path, str):
        return "."

    normalized = path.strip().replace("\\", "/")
    if not normalized:
        return "."

    dir_suffix = normalized.endswith("/")
    while normalized.startswith("./"):
        normalized = normalized[2:]

    if normalized == "/repo":
        normalized = ""
    elif normalized.startswith("/repo/"):
        normalized = normalized[6:]
    elif normalized.startswith("/repo"):
        normalized = normalized[5:].lstrip("/")

    while normalized.startswith("./"):
        normalized = normalized[2:]

    if not normalized:
        return "."

    if not normalized.startswith("/"):
        normalized = normalized.strip("/")
    if not normalized:
        return "."
    if dir_suffix and normalized != "/":
        return normalized.rstrip("/") + "/"
    return normalized


def _join_repo_path(base_path: Any, child_path: Any) -> str:
    child_raw = child_path if isinstance(child_path, str) else ""
    if child_raw.startswith("/repo"):
        return _normalize_repo_path(child_raw)

    base_norm = _normalize_repo_path(base_path)
    child_norm = _normalize_repo_path(child_path)
    if child_norm == ".":
        return base_norm
    if base_norm == ".":
        return child_norm

    child_is_dir = child_norm.endswith("/")
    joined = str(PurePosixPath(base_norm.rstrip("/")) / child_norm.rstrip("/"))
    if child_is_dir:
        return joined.rstrip("/") + "/"
    return joined


def _extract_view_file_lines(result: Any) -> tuple[int, int] | None:
    if not isinstance(result, str) or result.startswith("Error"):
        return None

    start: int | None = None
    end: int | None = None
    for line in result.splitlines():
        match = _VIEW_LINE_RE.match(line)
        if not match:
            continue
        value = int(match.group("line"))
        if start is None:
            start = value
        end = value
    if start is None or end is None:
        return None
    return (start, end)


# ---------------------------------------------------------------------------
# Per-tool parsers
# ---------------------------------------------------------------------------


def _parse_view_file(
    turn: int, args: dict[str, Any], result: Any, **kw: Any
) -> list[FileAccessEvent]:
    path = _normalize_repo_path(args.get("path", ""))
    if path == ".":
        return []
    lines = _extract_view_file_lines(result)
    return [
        FileAccessEvent(
            turn=turn,
            tool_name="view_file",
            access_type="read",
            path=path,
            lines=lines,
            **kw,
        )
    ]


def _parse_view_directory(
    turn: int, args: dict[str, Any], result: Any, **kw: Any
) -> list[FileAccessEvent]:
    if not isinstance(result, str) or result.startswith("Error"):
        return []

    base_path = args.get("path", ".")
    events: list[FileAccessEvent] = []
    for raw_line in result.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("..."):
            continue
        path = _join_repo_path(base_path, line)
        if path == ".":
            continue
        events.append(
            FileAccessEvent(
                turn=turn,
                tool_name="view_directory",
                access_type="discover",
                path=path,
                **kw,
            )
        )
    return events


def _parse_grep_search(
    turn: int, args: dict[str, Any], result: Any, **kw: Any
) -> list[FileAccessEvent]:
    if not isinstance(result, str) or result.startswith("Error"):
        return []

    events: list[FileAccessEvent] = []
    seen: set[str] = set()
    for line in result.splitlines():
        match = _GREP_LINE_RE.match(line)
        if not match:
            continue
        path = _normalize_repo_path(match.group("path"))
        if path == "." or path in seen:
            continue
        seen.add(path)
        line_no = int(match.group("line"))
        events.append(
            FileAccessEvent(
                turn=turn,
                tool_name="grep_search",
                access_type="grep_hit",
                path=path,
                lines=(line_no, line_no),
                **kw,
            )
        )
    return events


def _parse_glob(turn: int, args: dict[str, Any], result: Any, **kw: Any) -> list[FileAccessEvent]:
    if not isinstance(result, str) or result.startswith(("Error", "No matches")):
        return []

    base_path = args.get("path", ".")
    events: list[FileAccessEvent] = []
    for raw_line in result.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("..."):
            continue
        path = _join_repo_path(base_path, line)
        if path == ".":
            continue
        events.append(
            FileAccessEvent(
                turn=turn,
                tool_name="glob",
                access_type="discover",
                path=path,
                **kw,
            )
        )
    return events


def _parse_report_back(
    turn: int, args: dict[str, Any], result: Any, **kw: Any
) -> list[FileAccessEvent]:
    files = args.get("files", {})
    if not isinstance(files, dict):
        return []

    events: list[FileAccessEvent] = []
    for raw_path, ranges in files.items():
        path = _normalize_repo_path(raw_path)
        if path == ".":
            continue
        lines: tuple[int, int] | None = None
        if isinstance(ranges, list) and ranges:
            first = ranges[0]
            if (
                isinstance(first, list)
                and len(first) >= 2
                and isinstance(first[0], int)
                and isinstance(first[1], int)
            ):
                lines = (first[0], first[1])
        events.append(
            FileAccessEvent(
                turn=turn,
                tool_name="report_back",
                access_type="select",
                path=path,
                lines=lines,
                **kw,
            )
        )
    return events


def _parse_find_symbol(
    turn: int, args: dict[str, Any], result: Any, **kw: Any
) -> list[FileAccessEvent]:
    events: list[FileAccessEvent] = []

    src_path = _normalize_repo_path(args.get("file", ""))
    src_line = args.get("line")
    if src_path != ".":
        lines = (src_line, src_line) if isinstance(src_line, int) else None
        events.append(
            FileAccessEvent(
                turn=turn,
                tool_name="find_symbol",
                access_type="lsp_nav",
                path=src_path,
                lines=lines,
                **kw,
            )
        )

    if not isinstance(result, str) or result.startswith(("Error", "No results")):
        return events

    seen = {event.path for event in events}
    for line in result.splitlines():
        match = _GREP_LINE_RE.match(line)
        if not match:
            continue
        path = _normalize_repo_path(match.group("path"))
        if path == "." or path in seen:
            continue
        seen.add(path)
        line_no = int(match.group("line"))
        events.append(
            FileAccessEvent(
                turn=turn,
                tool_name="find_symbol",
                access_type="lsp_nav",
                path=path,
                lines=(line_no, line_no),
                **kw,
            )
        )
    return events


def _parse_search_symbol(
    turn: int, args: dict[str, Any], result: Any, **kw: Any
) -> list[FileAccessEvent]:
    if not isinstance(result, str) or result.startswith(("Error", "No symbols", "No results")):
        return []

    events: list[FileAccessEvent] = []
    seen: set[str] = set()
    for line in result.splitlines():
        symbol_match = _LSP_SYMBOL_RE.match(line)
        if symbol_match:
            path = _normalize_repo_path(symbol_match.group("path"))
            if path == "." or path in seen:
                continue
            seen.add(path)
            line_no = int(symbol_match.group("line"))
            events.append(
                FileAccessEvent(
                    turn=turn,
                    tool_name="search_symbol",
                    access_type="lsp_search",
                    path=path,
                    lines=(line_no, line_no),
                    **kw,
                )
            )
            continue

        grep_match = _GREP_LINE_RE.match(line)
        if not grep_match:
            continue
        path = _normalize_repo_path(grep_match.group("path"))
        if path == "." or path in seen:
            continue
        seen.add(path)
        line_no = int(grep_match.group("line"))
        events.append(
            FileAccessEvent(
                turn=turn,
                tool_name="search_symbol",
                access_type="lsp_search",
                path=path,
                lines=(line_no, line_no),
                **kw,
            )
        )
    return events


_TOOL_PARSERS: dict[str, Any] = {
    "view_file": _parse_view_file,
    "view_directory": _parse_view_directory,
    "grep_search": _parse_grep_search,
    "glob": _parse_glob,
    "report_back": _parse_report_back,
    "find_symbol": _parse_find_symbol,
    "search_symbol": _parse_search_symbol,
}


# ---------------------------------------------------------------------------
# Main extraction entry point
# ---------------------------------------------------------------------------


def _parse_tool_results(
    turn: int,
    tool_calls_raw: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
) -> list[FileAccessEvent]:
    args_by_id: dict[str, dict[str, Any]] = {}
    for tc in tool_calls_raw:
        tc_id = tc.get("id", "")
        func = tc.get("function", {})
        raw_args = func.get("arguments", "{}")
        try:
            parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except (json.JSONDecodeError, TypeError):
            parsed = {}
        args_by_id[tc_id] = parsed if isinstance(parsed, dict) else {}

    events: list[FileAccessEvent] = []
    for tr in tool_results:
        name = tr.get("name", "")
        parser = _TOOL_PARSERS.get(name)
        if parser is None:
            continue
        tc_id = tr.get("id", "")
        result = tr.get("result", "")
        success = bool(tr.get("success", True))
        latency_ms = float(tr.get("latency_ms", 0.0) or 0.0)
        args = args_by_id.get(tc_id, {})
        events.extend(
            parser(
                turn,
                args,
                result,
                is_success=success,
                latency_ms=latency_ms,
            )
        )
    return events


def extract_search_map(
    trace_path: Path | None,
    case_id: str | None = None,
    *,
    meta_path: Path | None = None,
) -> SearchMap:
    if case_id:
        cid = case_id
    elif trace_path is not None:
        cid = trace_path.stem
    elif meta_path is not None:
        cid = meta_path.name[: -len(".meta.json")]
    else:
        cid = ""

    turns, _ = load_trace_turns(trace_path)
    meta, _ = load_trace_meta(meta_path if meta_path is not None else None)
    if not meta and trace_path is not None and meta_path is None:
        meta, _ = load_trace_meta(trace_path.with_suffix(".meta.json"))

    sm = SearchMap(case_id=cid, total_turns=len(turns), meta=meta)
    for entry in turns:
        turn = entry.get("turn", 0)
        if not isinstance(turn, int) or turn <= 0:
            continue
        tool_calls_raw = entry.get("tool_calls_raw", [])
        tool_results = entry.get("tool_results", [])
        if not isinstance(tool_calls_raw, list) or not isinstance(tool_results, list):
            continue
        sm.events.extend(_parse_tool_results(turn, tool_calls_raw, tool_results))
    return sm


def extract_batch(traces_dir: Path) -> list[SearchMap]:
    return [
        extract_search_map(artifact.trace_path, artifact.case_id, meta_path=artifact.meta_path)
        for artifact in collect_trace_artifacts(traces_dir)
    ]


# ---------------------------------------------------------------------------
# Batch aggregation
# ---------------------------------------------------------------------------


def aggregate_search_maps(maps: list[SearchMap]) -> dict[str, Any]:
    if not maps:
        return {
            "cases": 0,
            "total_events": 0,
            "avg_events_per_case": 0.0,
            "avg_unique_files_per_case": 0.0,
            "avg_selected_files_per_case": 0.0,
            "avg_wasted_reads_per_case": 0.0,
            "avg_semantic_hints_per_case": 0.0,
            "cases_with_semantic_hints": 0,
            "tool_event_counts": {},
            "access_type_counts": {},
        }

    total_events = sum(len(m.events) for m in maps)
    total_unique = sum(len(m.unique_files) for m in maps)
    total_selected = sum(len(m.selected_files) for m in maps)
    total_wasted = sum(len(m.wasted_reads()) for m in maps)
    total_semantic_hints = sum(m.semantic_hints_count for m in maps)
    cases_with_semantic_hints = sum(1 for m in maps if m.semantic_hints_count > 0)

    tool_counts: dict[str, int] = {}
    access_type_counts: dict[str, int] = {}
    for m in maps:
        for e in m.events:
            tool_counts[e.tool_name] = tool_counts.get(e.tool_name, 0) + 1
            access_type_counts[e.access_type] = access_type_counts.get(e.access_type, 0) + 1

    return {
        "cases": len(maps),
        "total_events": total_events,
        "avg_events_per_case": round(total_events / len(maps), 1),
        "avg_unique_files_per_case": round(total_unique / len(maps), 1),
        "avg_selected_files_per_case": round(total_selected / len(maps), 1),
        "avg_wasted_reads_per_case": round(total_wasted / len(maps), 1),
        "avg_semantic_hints_per_case": round(total_semantic_hints / len(maps), 1),
        "cases_with_semantic_hints": cases_with_semantic_hints,
        "tool_event_counts": dict(sorted(tool_counts.items(), key=lambda x: -x[1])),
        "access_type_counts": dict(sorted(access_type_counts.items(), key=lambda x: -x[1])),
    }


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_search_map_report(maps: list[SearchMap]) -> str:
    if not maps:
        return "No search maps to report."

    agg = aggregate_search_maps(maps)
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("Search Map Report")
    lines.append("=" * 60)
    lines.append(f"Cases analyzed: {agg['cases']}")
    lines.append(f"Total file-access events: {agg['total_events']}")
    lines.append(f"Avg events/case: {agg['avg_events_per_case']}")
    lines.append(f"Avg unique files/case: {agg['avg_unique_files_per_case']}")
    lines.append(f"Avg selected files/case: {agg['avg_selected_files_per_case']}")
    lines.append(f"Avg wasted reads/case: {agg['avg_wasted_reads_per_case']}")
    lines.append("")
    lines.append("Retrieval hints:")
    lines.append(f"  Avg semantic_hints/case: {agg['avg_semantic_hints_per_case']}")
    lines.append(f"  Cases with semantic_hints: {agg['cases_with_semantic_hints']}/{agg['cases']}")
    lines.append("")
    lines.append("Tool event distribution:")
    for tool, count in agg["tool_event_counts"].items():
        pct = count / agg["total_events"] * 100 if agg["total_events"] else 0.0
        lines.append(f"  {tool:20s} {count:5d}  ({pct:.1f}%)")
    lines.append("")
    lines.append("Access type distribution:")
    for access_type, count in agg["access_type_counts"].items():
        pct = count / agg["total_events"] * 100 if agg["total_events"] else 0.0
        lines.append(f"  {access_type:20s} {count:5d}  ({pct:.1f}%)")

    lines.append("")
    lines.append("-" * 76)
    lines.append(
        f"{'Case':<30s} {'Events':>7s} {'Unique':>7s} {'Select':>7s} {'Hints':>7s} {'Waste':>7s}"
    )
    lines.append("-" * 76)
    for m in maps:
        lines.append(
            f"{m.case_id:<30s} {len(m.events):>7d} {len(m.unique_files):>7d} "
            f"{len(m.selected_files):>7d} {m.semantic_hints_count:>7d} {len(m.wasted_reads()):>7d}"
        )
    lines.append("-" * 76)

    return "\n".join(lines)
