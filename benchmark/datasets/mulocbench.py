"""Loader for benchmark datasets.

Supports the unified DatasetCase format with hard_gt and soft_context.
"""

import json
import random
from collections import defaultdict
from pathlib import Path

from ..config import DEFAULT_MULOCBENCH_PATH, EXCLUDED_REPOS, get_benchmark_dir
from ..schemas import ContextEntry, DatasetCase, GroundTruthEntry, SolvabilityInfo


def _resolve_dataset_path(dataset_path: str) -> Path:
    path = Path(dataset_path)
    if path.is_absolute():
        return path
    return get_benchmark_dir() / path


def _stratified_sample(
    cases: list[DatasetCase], limit: int, rng: random.Random
) -> list[DatasetCase]:
    """Stratified sampling: ensure each repo has at least 1 case."""
    by_repo: dict[str, list[DatasetCase]] = defaultdict(list)
    for c in cases:
        by_repo[c.repo].append(c)

    repos = list(by_repo.keys())

    if len(repos) > limit:
        selected_repos = rng.sample(repos, limit)
        selected: list[DatasetCase] = []
        for repo in selected_repos:
            case = rng.choice(by_repo[repo])
            selected.append(case)
        rng.shuffle(selected)
        return selected

    selected = []
    selected_set: set[str] = set()

    for _repo, repo_cases in by_repo.items():
        case = rng.choice(repo_cases)
        selected.append(case)
        selected_set.add(case.id)

    remaining = limit - len(selected)
    if remaining > 0:
        pool = [c for c in cases if c.id not in selected_set]
        if len(pool) <= remaining:
            selected.extend(pool)
        else:
            selected.extend(rng.sample(pool, remaining))

    rng.shuffle(selected)
    return selected


def load_dataset(
    *,
    dataset_path: str = DEFAULT_MULOCBENCH_PATH,
    limit: int | None = None,
    shuffle: bool = True,
    seed: int = 0,
    stratified: bool = False,
    exclude_repos: frozenset[str] | None = None,
    min_confidence: float = 0.0,
) -> list[DatasetCase]:
    """Load benchmark dataset in unified format.

    This loader supports the new standardized schema with hard_gt and soft_context.

    Args:
        dataset_path: Path to JSONL file (relative to benchmark/ if not absolute).
        limit: Maximum cases to load.
        shuffle: Whether to shuffle cases.
        seed: Random seed for shuffling.
        stratified: If True with limit, ensure each repo has at least 1 case.
        exclude_repos: Repos to skip. Defaults to EXCLUDED_REPOS.
        min_confidence: Minimum solvability confidence to include (0.0 = include all).

    Returns:
        List of DatasetCase objects.
    """
    if exclude_repos is None:
        exclude_repos = EXCLUDED_REPOS

    path = _resolve_dataset_path(dataset_path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    excluded_lower = {r.lower() for r in exclude_repos}
    cases: list[DatasetCase] = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue

            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                continue

            repo = data.get("repo", "")
            if repo.lower() in excluded_lower:
                continue

            # Parse solvability if present
            solvability = None
            if "solvability" in data and data["solvability"]:
                solvability = SolvabilityInfo.from_dict(data["solvability"])
                if min_confidence > 0 and solvability.confidence < min_confidence:
                    continue

            # Parse hard_gt
            hard_gt: list[GroundTruthEntry] = []
            for gt in data.get("hard_gt", []):
                if not isinstance(gt, dict):
                    continue
                path_str = gt.get("path", "")
                range_data = gt.get("range", [])
                if not path_str or len(range_data) < 2:
                    continue
                hard_gt.append(
                    GroundTruthEntry(
                        path=path_str,
                        function=gt.get("function", ""),
                        range=(range_data[0], range_data[1]),
                        class_name=gt.get("class"),
                        signature=gt.get("signature"),
                    )
                )

            # Skip cases without ground truth
            if not hard_gt:
                continue

            # Parse soft_context
            soft_context: list[ContextEntry] = []
            for ctx in data.get("soft_context", []):
                if not isinstance(ctx, dict):
                    continue
                path_str = ctx.get("path", "")
                range_data = ctx.get("range", [])
                if not path_str or len(range_data) < 2:
                    continue
                soft_context.append(
                    ContextEntry(
                        path=path_str,
                        function=ctx.get("function", ""),
                        range=(range_data[0], range_data[1]),
                        signature=ctx.get("signature"),
                        relevance_score=ctx.get("relevance_score"),
                    )
                )

            cases.append(
                DatasetCase(
                    id=data.get("id", ""),
                    query=data.get("query", ""),
                    repo=repo,
                    base_commit=data.get("base_commit", ""),
                    hard_gt=hard_gt,
                    soft_context=soft_context,
                    solvability=solvability,
                    issue_url=data.get("issue_url"),
                    pr_url=data.get("pr_url"),
                )
            )

    if shuffle:
        rng = random.Random(seed)
        rng.shuffle(cases)

    if stratified and limit is not None:
        rng = random.Random(seed)
        cases = _stratified_sample(cases, limit, rng)

    return cases if limit is None else cases[:limit]


# Backwards compatibility alias
load_mulocbench = load_dataset
