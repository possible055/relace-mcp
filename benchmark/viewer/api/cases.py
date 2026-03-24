"""Cases API router.

Provides endpoints for accessing individual benchmark cases within experiments.
"""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/experiments/{experiment_id}/cases", tags=["cases"])


class CaseSummary(BaseModel):
    """Summary view of a benchmark case."""

    case_id: str
    repo: str
    completed: bool
    file_recall: float
    file_precision: float
    turns_used: int
    latency_s: float


class CaseDetail(BaseModel):
    """Detailed view of a benchmark case."""

    case_id: str
    repo: str
    completed: bool
    file_recall: float
    file_precision: float
    line_coverage: float
    function_hit_rate: float
    turns_used: int
    latency_s: float
    returned_files: dict[str, list[list[int]]]
    error: str | None = None


class CaseListResponse(BaseModel):
    """Paginated case list response."""

    items: list[CaseSummary]
    total: int
    limit: int
    offset: int


class TraceEvent(BaseModel):
    """Single event in a case trace."""

    event: str
    timestamp: str | None = None
    data: dict[str, Any] = {}


class CaseTraceResponse(BaseModel):
    """Trace data for a case."""

    case_id: str
    events: list[TraceEvent]
    metadata: dict[str, Any]


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


@router.get("", response_model=CaseListResponse)
def list_cases(
    request: Request,
    experiment_id: str,
    completed: bool | None = Query(None, description="Filter by completion status"),
    limit: int = Query(50, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> CaseListResponse:
    """List cases in an experiment with optional filtering."""
    experiments_root = _get_experiments_root(request)
    exp_dir = experiments_root / experiment_id

    if not exp_dir.exists():
        raise HTTPException(status_code=404, detail="Experiment not found")

    results = _load_results_jsonl(exp_dir)

    if completed is not None:
        results = [r for r in results if r.get("completed") == completed]

    total = len(results)
    paginated = results[offset : offset + limit]

    items = [
        CaseSummary(
            case_id=r.get("case_id", ""),
            repo=r.get("repo", ""),
            completed=r.get("completed", False),
            file_recall=r.get("file_recall", 0.0),
            file_precision=r.get("file_precision", 0.0),
            turns_used=r.get("turns_used", 0),
            latency_s=r.get("latency_s", 0.0),
        )
        for r in paginated
    ]

    return CaseListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(
    request: Request,
    experiment_id: str,
    case_id: str,
) -> CaseDetail:
    """Get detailed case information."""
    experiments_root = _get_experiments_root(request)
    exp_dir = experiments_root / experiment_id

    if not exp_dir.exists():
        raise HTTPException(status_code=404, detail="Experiment not found")

    results = _load_results_jsonl(exp_dir)
    case_result = next((r for r in results if r.get("case_id") == case_id), None)

    if not case_result:
        raise HTTPException(status_code=404, detail="Case not found")

    return CaseDetail(
        case_id=case_result.get("case_id", ""),
        repo=case_result.get("repo", ""),
        completed=case_result.get("completed", False),
        file_recall=case_result.get("file_recall", 0.0),
        file_precision=case_result.get("file_precision", 0.0),
        line_coverage=case_result.get("line_coverage", 0.0),
        function_hit_rate=case_result.get("function_hit_rate", 0.0),
        turns_used=case_result.get("turns_used", 0),
        latency_s=case_result.get("latency_s", 0.0),
        returned_files=case_result.get("returned_files", {}),
        error=case_result.get("error"),
    )


@router.get("/{case_id}/trace", response_model=CaseTraceResponse)
def get_case_trace(
    request: Request,
    experiment_id: str,
    case_id: str,
) -> CaseTraceResponse:
    """Get trace data for a case."""
    experiments_root = _get_experiments_root(request)
    exp_dir = experiments_root / experiment_id

    if not exp_dir.exists():
        raise HTTPException(status_code=404, detail="Experiment not found")

    trace_path = exp_dir / "traces" / f"{case_id}.jsonl"
    meta_path = exp_dir / "traces" / f"{case_id}.meta.json"

    events: list[TraceEvent] = []
    if trace_path.exists():
        with trace_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    events.append(
                        TraceEvent(
                            event=data.get("event", "unknown"),
                            timestamp=data.get("timestamp"),
                            data={k: v for k, v in data.items() if k not in ("event", "timestamp")},
                        )
                    )

    metadata: dict[str, Any] = {}
    if meta_path.exists():
        with meta_path.open("r", encoding="utf-8") as f:
            metadata = json.load(f)

    return CaseTraceResponse(
        case_id=case_id,
        events=events,
        metadata=metadata,
    )
