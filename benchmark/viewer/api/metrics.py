"""Metrics API router.

Provides endpoints for querying and aggregating metrics.
"""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/experiments/{experiment_id}/metrics", tags=["metrics"])


class MetricsSummary(BaseModel):
    """Aggregated metrics for an experiment."""

    total_cases: int
    completed_cases: int
    avg_file_recall: float
    avg_file_precision: float
    avg_line_coverage: float
    avg_function_hit_rate: float
    avg_turns_used: float
    avg_latency_s: float


class ToolMetrics(BaseModel):
    """Metrics grouped by tool."""

    tool_name: str
    total_uses: int
    avg_files_found: float


class TurnMetrics(BaseModel):
    """Metrics for a specific turn."""

    turn_index: int
    case_count: int
    avg_file_recall: float
    avg_file_precision: float


class MetricsByGroup(BaseModel):
    """Metrics grouped by a dimension."""

    group_by: str
    groups: list[dict[str, Any]]


def _get_experiments_root(request: Request) -> Path:
    """Get experiments root directory from app state."""
    return request.app.state.experiments_root


def _load_results_jsonl(experiment_dir: Path) -> list[dict[str, Any]]:
    """Load results from JSONL file."""
    results_path = experiment_dir / "results" / "results.jsonl"
    if not results_path.exists():
        return []

    results = []
    with results_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return results


@router.get("", response_model=MetricsSummary)
def get_metrics_summary(
    request: Request,
    experiment_id: str,
) -> MetricsSummary:
    """Get aggregated metrics for an experiment."""
    experiments_root = _get_experiments_root(request)
    exp_dir = experiments_root / experiment_id

    if not exp_dir.exists():
        raise HTTPException(status_code=404, detail="Experiment not found")

    results = _load_results_jsonl(exp_dir)
    if not results:
        raise HTTPException(status_code=404, detail="No results found")

    completed = [r for r in results if r.get("completed", False)]

    def avg(key: str, data: list[dict]) -> float:
        values = [r.get(key, 0.0) for r in data]
        return sum(values) / len(values) if values else 0.0

    return MetricsSummary(
        total_cases=len(results),
        completed_cases=len(completed),
        avg_file_recall=avg("file_recall", completed),
        avg_file_precision=avg("file_precision", completed),
        avg_line_coverage=avg("line_coverage", completed),
        avg_function_hit_rate=avg("function_hit_rate", completed),
        avg_turns_used=avg("turns_used", completed),
        avg_latency_s=avg("latency_s", completed),
    )


@router.get("/by-turn", response_model=MetricsByGroup)
def get_metrics_by_turn(
    request: Request,
    experiment_id: str,
) -> MetricsByGroup:
    """Get metrics grouped by turn count."""
    experiments_root = _get_experiments_root(request)
    exp_dir = experiments_root / experiment_id

    if not exp_dir.exists():
        raise HTTPException(status_code=404, detail="Experiment not found")

    results = _load_results_jsonl(exp_dir)
    completed = [r for r in results if r.get("completed", False)]

    by_turn: dict[int, list[dict]] = {}
    for r in completed:
        turns = r.get("turns_used", 0)
        by_turn.setdefault(turns, []).append(r)

    groups = []
    for turn_count, cases in sorted(by_turn.items()):
        recalls = [c.get("file_recall", 0.0) for c in cases]
        precisions = [c.get("file_precision", 0.0) for c in cases]
        groups.append(
            {
                "turn_count": turn_count,
                "case_count": len(cases),
                "avg_file_recall": sum(recalls) / len(recalls) if recalls else 0.0,
                "avg_file_precision": sum(precisions) / len(precisions) if precisions else 0.0,
            }
        )

    return MetricsByGroup(group_by="turn_count", groups=groups)


@router.get("/by-repo", response_model=MetricsByGroup)
def get_metrics_by_repo(
    request: Request,
    experiment_id: str,
    limit: int = Query(20, ge=1, le=100),
) -> MetricsByGroup:
    """Get metrics grouped by repository."""
    experiments_root = _get_experiments_root(request)
    exp_dir = experiments_root / experiment_id

    if not exp_dir.exists():
        raise HTTPException(status_code=404, detail="Experiment not found")

    results = _load_results_jsonl(exp_dir)
    completed = [r for r in results if r.get("completed", False)]

    by_repo: dict[str, list[dict]] = {}
    for r in completed:
        repo = r.get("repo", "unknown")
        by_repo.setdefault(repo, []).append(r)

    groups = []
    for repo, cases in sorted(by_repo.items(), key=lambda x: -len(x[1])):
        recalls = [c.get("file_recall", 0.0) for c in cases]
        precisions = [c.get("file_precision", 0.0) for c in cases]
        groups.append(
            {
                "repo": repo,
                "case_count": len(cases),
                "avg_file_recall": sum(recalls) / len(recalls) if recalls else 0.0,
                "avg_file_precision": sum(precisions) / len(precisions) if precisions else 0.0,
            }
        )

    return MetricsByGroup(group_by="repo", groups=groups[:limit])


@router.get("/distribution")
def get_metrics_distribution(
    request: Request,
    experiment_id: str,
    metric: str = Query("file_recall", description="Metric to analyze"),
    bins: int = Query(10, ge=5, le=50, description="Number of histogram bins"),
) -> dict[str, Any]:
    """Get distribution of a metric across cases."""
    experiments_root = _get_experiments_root(request)
    exp_dir = experiments_root / experiment_id

    if not exp_dir.exists():
        raise HTTPException(status_code=404, detail="Experiment not found")

    results = _load_results_jsonl(exp_dir)
    completed = [r for r in results if r.get("completed", False)]

    values = [r.get(metric, 0.0) for r in completed]
    if not values:
        return {"metric": metric, "bins": [], "counts": []}

    min_val = min(values)
    max_val = max(values)
    if max_val == min_val:
        return {
            "metric": metric,
            "bins": [min_val],
            "counts": [len(values)],
            "min": min_val,
            "max": max_val,
            "mean": min_val,
        }

    bin_width = (max_val - min_val) / bins
    bin_edges = [min_val + i * bin_width for i in range(bins + 1)]
    counts = [0] * bins

    for v in values:
        bin_idx = min(int((v - min_val) / bin_width), bins - 1)
        counts[bin_idx] += 1

    return {
        "metric": metric,
        "bins": bin_edges,
        "counts": counts,
        "min": min_val,
        "max": max_val,
        "mean": sum(values) / len(values),
    }
