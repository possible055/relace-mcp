"""Metrics API router."""

from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from benchmark.experiments.store import ExperimentStore
from benchmark.web.api.deps import get_store
from benchmark.web.api.schemas import MetricsSummaryModel

router = APIRouter(prefix="/api/experiments/{experiment_id}/metrics", tags=["metrics"])

ExperimentStoreDep = Annotated[ExperimentStore, Depends(get_store)]


@router.get("", response_model=MetricsSummaryModel)
def get_metrics_summary(
    experiment_id: str,
    store: ExperimentStoreDep,
) -> MetricsSummaryModel:
    manifest = store.get(experiment_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    state = store.get_state(experiment_id)
    summary = store.get_summary(experiment_id) or {}
    stats = summary.get("stats", {}) if isinstance(summary, dict) else {}
    completed_cases = state.completed_cases if state else 0
    failed_cases = state.failed_cases if state else 0
    total_cases = state.total_cases if state else int(manifest.dataset.get("case_count", 0))
    return MetricsSummaryModel(
        total_cases=total_cases,
        completed_cases=completed_cases,
        failed_cases=failed_cases,
        avg_file_recall=float(stats.get("avg_file_recall", 0.0)),
        avg_file_precision=float(stats.get("avg_file_precision", 0.0)),
        avg_line_coverage=float(stats.get("avg_line_coverage", 0.0)),
        avg_function_hit_rate=float(stats.get("avg_function_hit_rate", 0.0)),
        avg_turns_used=float(stats.get("avg_turns", 0.0)),
        avg_latency_s=float(stats.get("avg_latency_s", 0.0)),
    )


@router.get("/by-turn")
def get_metrics_by_turn(
    experiment_id: str,
    store: ExperimentStoreDep,
) -> dict[str, object]:
    results = [result for result in store.load_results(experiment_id) if result.completed]
    by_turn: dict[int, list[object]] = defaultdict(list)
    for result in results:
        by_turn[result.turns_used].append(result)
    groups = []
    for turn_count, cases in sorted(by_turn.items()):
        groups.append(
            {
                "turn_count": turn_count,
                "case_count": len(cases),
                "avg_file_recall": sum(case.file_recall for case in cases) / len(cases),
                "avg_file_precision": sum(case.file_precision for case in cases) / len(cases),
            }
        )
    return {"group_by": "turn_count", "groups": groups}


@router.get("/by-repo")
def get_metrics_by_repo(
    experiment_id: str,
    store: ExperimentStoreDep,
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, object]:
    results = [result for result in store.load_results(experiment_id) if result.completed]
    by_repo: dict[str, list[object]] = defaultdict(list)
    for result in results:
        by_repo[result.repo].append(result)
    groups = []
    for repo, cases in sorted(by_repo.items(), key=lambda item: -len(item[1]))[:limit]:
        groups.append(
            {
                "repo": repo,
                "case_count": len(cases),
                "avg_file_recall": sum(case.file_recall for case in cases) / len(cases),
                "avg_file_precision": sum(case.file_precision for case in cases) / len(cases),
            }
        )
    return {"group_by": "repo", "groups": groups}


@router.get("/distribution")
def get_metrics_distribution(
    experiment_id: str,
    store: ExperimentStoreDep,
    metric: str = Query("file_recall"),
    bins: int = Query(10, ge=5, le=50),
) -> dict[str, object]:
    results = [result for result in store.load_results(experiment_id) if result.completed]
    values = [float(getattr(result, metric, 0.0)) for result in results]
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
    for value in values:
        bin_idx = min(int((value - min_val) / bin_width), bins - 1)
        counts[bin_idx] += 1
    return {
        "metric": metric,
        "bins": bin_edges,
        "counts": counts,
        "min": min_val,
        "max": max_val,
        "mean": sum(values) / len(values),
    }
