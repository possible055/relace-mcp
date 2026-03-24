"""Experiments API router.

Provides endpoints for experiment CRUD and listing operations.
"""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


class ExperimentSummary(BaseModel):
    """Summary view of an experiment."""

    experiment_id: str
    name: str
    status: str
    dataset_name: str
    case_count: int
    created_at: str
    file_recall: float
    file_precision: float


class ExperimentDetail(BaseModel):
    """Detailed view of an experiment."""

    experiment_id: str
    name: str
    status: str
    metadata: dict[str, Any]
    stats: dict[str, float]
    case_count: int


class ExperimentListResponse(BaseModel):
    """Paginated experiment list response."""

    items: list[ExperimentSummary]
    total: int
    limit: int
    offset: int


def _load_experiment_report(experiment_dir: Path) -> dict[str, Any] | None:
    """Load experiment report from directory."""
    report_path = experiment_dir / "reports" / "summary.report.json"
    if not report_path.exists():
        return None
    with report_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _get_experiments_root(request: Request) -> Path:
    """Get experiments root directory from app state."""
    return request.app.state.experiments_root


@router.get("", response_model=ExperimentListResponse)
def list_experiments(
    request: Request,
    status: str | None = Query(None, description="Filter by status"),
    dataset: str | None = Query(None, description="Filter by dataset name"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> ExperimentListResponse:
    """List experiments with optional filtering and pagination."""
    experiments_root = _get_experiments_root(request)
    if not experiments_root.exists():
        return ExperimentListResponse(items=[], total=0, limit=limit, offset=offset)

    all_experiments: list[ExperimentSummary] = []

    for exp_dir in experiments_root.iterdir():
        if not exp_dir.is_dir():
            continue

        report = _load_experiment_report(exp_dir)
        if not report:
            continue

        metadata = report.get("metadata", {})
        run_info = metadata.get("run", {})
        dataset_info = metadata.get("dataset", {})
        dataset_path = dataset_info.get("dataset_path", "")
        dataset_name = (
            dataset_path.split("/")[-1].replace(".jsonl", "") if dataset_path else "unknown"
        )

        if dataset and dataset_name != dataset:
            continue

        summary = ExperimentSummary(
            experiment_id=exp_dir.name,
            name=exp_dir.name,
            status="completed",
            dataset_name=dataset_name,
            case_count=report.get("total_cases", 0),
            created_at=run_info.get("started_at_utc", ""),
            file_recall=report.get("avg_file_recall", 0.0),
            file_precision=report.get("avg_file_precision", 0.0),
        )

        if status and summary.status != status:
            continue

        all_experiments.append(summary)

    all_experiments.sort(key=lambda x: x.created_at, reverse=True)
    total = len(all_experiments)
    paginated = all_experiments[offset : offset + limit]

    return ExperimentListResponse(
        items=paginated,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{experiment_id}", response_model=ExperimentDetail)
def get_experiment(request: Request, experiment_id: str) -> ExperimentDetail:
    """Get detailed experiment information."""
    experiments_root = _get_experiments_root(request)
    exp_dir = experiments_root / experiment_id

    if not exp_dir.exists():
        raise HTTPException(status_code=404, detail="Experiment not found")

    report = _load_experiment_report(exp_dir)
    if not report:
        raise HTTPException(status_code=404, detail="Experiment report not found")

    metadata = report.get("metadata", {})
    stats = {
        k: v
        for k, v in report.items()
        if k not in ("metadata", "results") and isinstance(v, (int, float))
    }

    return ExperimentDetail(
        experiment_id=experiment_id,
        name=experiment_id,
        status="completed",
        metadata=metadata,
        stats=stats,
        case_count=report.get("total_cases", 0),
    )


@router.delete("/{experiment_id}")
def delete_experiment(request: Request, experiment_id: str) -> dict[str, str]:
    """Delete an experiment and all its artifacts."""
    experiments_root = _get_experiments_root(request)
    exp_dir = experiments_root / experiment_id

    if not exp_dir.exists():
        raise HTTPException(status_code=404, detail="Experiment not found")

    import shutil

    shutil.rmtree(exp_dir)
    return {"status": "deleted", "experiment_id": experiment_id}
