import ast
import json
import random
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import EXCLUDED_REPOS, get_benchmark_dir
from ..filters.query_type import classify_query_str

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
    ground_truth_files_raw: dict[str, list[int]] = field(default_factory=dict)
    ground_truth_files_soft: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    ground_truth_functions: list[FunctionTarget] = field(default_factory=list)
    query_type: str | None = None
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


def _stratified_sample(
    cases: list[BenchmarkCase], limit: int, rng: random.Random
) -> list[BenchmarkCase]:
    """Stratified sampling: ensure each repo has at least 1 case.

    If there are more repos than the limit, randomly select `limit` repos
    and pick one case from each. Otherwise, pick one case from each repo,
    then fill remaining quota from the pool.
    """
    by_repo: dict[str, list[BenchmarkCase]] = defaultdict(list)
    for c in cases:
        by_repo[c.repo].append(c)

    repos = list(by_repo.keys())

    # If more repos than limit, select a random subset of repos
    if len(repos) > limit:
        selected_repos = rng.sample(repos, limit)
        selected: list[BenchmarkCase] = []
        for repo in selected_repos:
            case = rng.choice(by_repo[repo])
            selected.append(case)
        rng.shuffle(selected)
        return selected

    # Otherwise: pick 1 from each repo, then fill remaining quota
    selected: list[BenchmarkCase] = []
    selected_set: set[str] = set()

    # Phase 1: pick 1 case from each repo
    for _repo, repo_cases in by_repo.items():
        case = rng.choice(repo_cases)
        selected.append(case)
        selected_set.add(case.id)

    # Phase 2: fill remaining quota proportionally
    remaining = limit - len(selected)
    if remaining > 0:
        pool = [c for c in cases if c.id not in selected_set]
        if len(pool) <= remaining:
            selected.extend(pool)
        else:
            selected.extend(rng.sample(pool, remaining))

    rng.shuffle(selected)
    return selected


def load_mulocbench(
    *,
    dataset_path: str = DEFAULT_DATASET_PATH,
    limit: int | None = None,
    shuffle: bool = True,
    seed: int = 0,
    include_added_files: bool = False,
    require_function_scopes: bool = True,
    stratified: bool = False,
    exclude_repos: frozenset[str] | None = None,
) -> list[BenchmarkCase]:
    """Load MULocBench jsonl and convert rows to BenchmarkCase objects.

    Args:
        exclude_repos: Repos to skip. Defaults to EXCLUDED_REPOS (large repos).
                       Pass frozenset() to include all repos.
    """
    if exclude_repos is None:
        exclude_repos = EXCLUDED_REPOS

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

            # Early skip for excluded repos (avoid clone)
            if repo.lower() in {r.lower() for r in exclude_repos}:
                continue

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
            ground_truth_files_raw: dict[str, list[int]] = {}
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
                file_lines_raw: list[int] = []

                for raw_scope, change in loc.items():
                    if not isinstance(raw_scope, str):
                        continue
                    lines = _extract_lines(change)
                    if not lines:
                        continue
                    file_lines |= lines
                    file_lines_raw.extend(sorted(lines))

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
                ground_truth_files_raw.setdefault(file_path, []).extend(sorted(file_lines))

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
                    ground_truth_files_raw=ground_truth_files_raw,
                    ground_truth_functions=function_targets,
                    query_type=classify_query_str(query),
                    issue_url=issue_url,
                    pr_url=pr_url,
                )
            )

    if shuffle:
        rng = random.Random(seed)
        rng.shuffle(cases)

    if stratified and limit is not None:
        rng = random.Random(seed)
        cases = _stratified_sample(cases, limit, rng)

    return cases if limit is None else cases[:limit]
