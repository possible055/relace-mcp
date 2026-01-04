"""Loader for filtered dataset (dual-track ground truth format)."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import get_benchmark_dir

DEFAULT_FILTERED_PATH = "data/filtered.jsonl"


@dataclass
class FilteredCase:
    """A case from the filtered dataset with dual-track ground truth."""

    id: str
    query: str
    repo: str
    base_commit: str
    solvability: dict[str, Any]
    hard_gt: list[dict[str, Any]]
    soft_context: list[dict[str, Any]]
    issue_url: str | None = None
    pr_url: str | None = None

    @property
    def hard_gt_files(self) -> dict[str, list[tuple[int, int]]]:
        """Convert hard_gt to file -> ranges format."""
        files: dict[str, list[tuple[int, int]]] = {}
        for gt in self.hard_gt:
            path = gt.get("path", "")
            range_data = gt.get("range", [])
            if path and len(range_data) == 2:
                if path not in files:
                    files[path] = []
                files[path].append((range_data[0], range_data[1]))
        return files

    @property
    def soft_context_files(self) -> dict[str, list[tuple[int, int]]]:
        """Convert soft_context to file -> ranges format."""
        files: dict[str, list[tuple[int, int]]] = {}
        for ctx in self.soft_context:
            path = ctx.get("path", "")
            range_data = ctx.get("range", [])
            if path and len(range_data) == 2:
                if path not in files:
                    files[path] = []
                files[path].append((range_data[0], range_data[1]))
        return files


def load_filtered_dataset(
    dataset_path: str = DEFAULT_FILTERED_PATH,
    *,
    limit: int | None = None,
    min_confidence: float = 0.0,
) -> list[FilteredCase]:
    """Load filtered dataset.

    Args:
        dataset_path: Path to filtered.jsonl (relative to benchmark/ if not absolute).
        limit: Maximum cases to load.
        min_confidence: Minimum solvability confidence to include.

    Returns:
        List of FilteredCase objects.
    """
    path = Path(dataset_path)
    if not path.is_absolute():
        path = get_benchmark_dir() / path

    if not path.exists():
        raise FileNotFoundError(f"Filtered dataset not found: {path}")

    cases: list[FilteredCase] = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue

            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                continue

            # Filter by confidence
            solvability = data.get("solvability", {})
            confidence = solvability.get("confidence", 0.0)
            if confidence < min_confidence:
                continue

            case = FilteredCase(
                id=data.get("id", ""),
                query=data.get("query", ""),
                repo=data.get("repo", ""),
                base_commit=data.get("base_commit", ""),
                solvability=solvability,
                hard_gt=data.get("hard_gt", []),
                soft_context=data.get("soft_context", []),
                issue_url=data.get("issue_url"),
                pr_url=data.get("pr_url"),
            )
            cases.append(case)

            if limit is not None and len(cases) >= limit:
                break

    return cases
