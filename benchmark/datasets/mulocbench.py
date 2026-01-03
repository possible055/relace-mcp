import ast
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..paths import get_benchmark_dir

DEFAULT_DATASET_PATH = "data/mulocbench.jsonl"


@dataclass(frozen=True)
class FunctionTarget:
    path: str
    container: str | None
    name: str
    start_line: int
    ranges: list[tuple[int, int]]


@dataclass
class BenchmarkCase:
    id: str
    query: str
    repo: str
    base_commit: str
    ground_truth_files: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    ground_truth_functions: list[FunctionTarget] = field(default_factory=list)
    issue_url: str | None = None
    pr_url: str | None = None


@dataclass(frozen=True)
class _LocScope:
    container: str | None
    function_name: str | None
    start_line: int | None


def _resolve_dataset_path(dataset_path: str) -> Path:
    path = Path(dataset_path)
    if path.is_absolute():
        return path
    # CLI semantics: dataset paths are relative to benchmark/
    return get_benchmark_dir() / path


def _parse_scope(raw: str) -> _LocScope | None:
    try:
        parsed = ast.literal_eval(raw)
    except Exception:
        return None

    if not (isinstance(parsed, tuple) and len(parsed) == 3):
        return None

    container, function_name, start_line = parsed
    if container is not None and not isinstance(container, str):
        return None
    if function_name is not None and not isinstance(function_name, str):
        return None
    if start_line is not None and not isinstance(start_line, int):
        return None

    return _LocScope(
        container=container,
        function_name=function_name,
        start_line=start_line,
    )


def _lines_to_ranges(lines: set[int]) -> list[tuple[int, int]]:
    if not lines:
        return []

    sorted_lines = sorted({line for line in lines if isinstance(line, int) and line > 0})
    if not sorted_lines:
        return []

    ranges: list[tuple[int, int]] = []
    start = prev = sorted_lines[0]

    for line in sorted_lines[1:]:
        if line == prev + 1:
            prev = line
            continue
        ranges.append((start, prev))
        start = prev = line

    ranges.append((start, prev))
    return ranges


def _make_case_id(repo: str, issue_url: str | None, *, index: int) -> str:
    if issue_url:
        match = re.search(r"/(issues|pull)/(\d+)", issue_url)
        if match:
            prefix = "#" if match.group(1) == "issues" else "!"
            return f"{repo}{prefix}{match.group(2)}"
    return f"{repo}:{index}"


def _parse_file_loc(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = ast.literal_eval(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_lines(change: Any) -> set[int]:
    if not isinstance(change, dict):
        return set()

    lines: set[int] = set()
    for key in ("add", "mod"):
        values = change.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, int) and value > 0:
                lines.add(value)
    return lines


def load_mulocbench(
    *,
    dataset_path: str = DEFAULT_DATASET_PATH,
    limit: int = 50,
    shuffle: bool = True,
    seed: int = 0,
    include_added_files: bool = False,
    require_function_scopes: bool = True,
) -> list[BenchmarkCase]:
    """Load MULocBench jsonl and convert rows to BenchmarkCase objects."""
    path = _resolve_dataset_path(dataset_path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    cases: list[BenchmarkCase] = []
    with path.open("r", encoding="utf-8") as f:
        for index, line in enumerate(f):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            org = row.get("organization")
            repo_name = row.get("repo_name")
            if (
                not isinstance(org, str)
                or not isinstance(repo_name, str)
                or not org
                or not repo_name
            ):
                continue

            repo = f"{org}/{repo_name}"
            issue_url = (
                row.get("iss_html_url") if isinstance(row.get("iss_html_url"), str) else None
            )
            pr_url = row.get("pr_html_url") if isinstance(row.get("pr_html_url"), str) else None
            title = row.get("title") if isinstance(row.get("title"), str) else ""
            body = row.get("body") if isinstance(row.get("body"), str) else ""
            query = (title + "\n\n" + body).strip()

            file_loc = _parse_file_loc(row.get("file_loc"))
            if not file_loc:
                continue

            base_commit = file_loc.get("base_commit") or row.get("base_commit")
            if not isinstance(base_commit, str) or not base_commit:
                continue

            files = file_loc.get("files")
            if not isinstance(files, list):
                continue

            ground_truth_files: dict[str, list[tuple[int, int]]] = {}
            function_targets: list[FunctionTarget] = []

            for file_entry in files:
                if not isinstance(file_entry, dict):
                    continue
                status = file_entry.get("status")
                if status == "added" and not include_added_files:
                    continue

                file_path = file_entry.get("path")
                if not isinstance(file_path, str) or not file_path:
                    continue

                loc = file_entry.get("Loc")
                if not isinstance(loc, dict):
                    continue

                file_lines: set[int] = set()

                for raw_scope, change in loc.items():
                    if not isinstance(raw_scope, str):
                        continue
                    lines = _extract_lines(change)
                    if not lines:
                        continue
                    file_lines |= lines

                    scope = _parse_scope(raw_scope)
                    if not scope or not scope.function_name or not scope.start_line:
                        continue
                    ranges = _lines_to_ranges(lines)
                    if not ranges:
                        continue
                    function_targets.append(
                        FunctionTarget(
                            path=file_path,
                            container=scope.container,
                            name=scope.function_name,
                            start_line=scope.start_line,
                            ranges=ranges,
                        )
                    )

                ranges = _lines_to_ranges(file_lines)
                if not ranges:
                    continue
                ground_truth_files.setdefault(file_path, []).extend(ranges)

            if not ground_truth_files:
                continue
            if require_function_scopes and not function_targets:
                continue

            cases.append(
                BenchmarkCase(
                    id=_make_case_id(repo, issue_url, index=index),
                    query=query,
                    repo=repo,
                    base_commit=base_commit,
                    ground_truth_files=ground_truth_files,
                    ground_truth_functions=function_targets,
                    issue_url=issue_url,
                    pr_url=pr_url,
                )
            )

    if shuffle:
        rng = random.Random(seed)
        rng.shuffle(cases)

    return cases[:limit]
