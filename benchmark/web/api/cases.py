"""Cases API router."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from benchmark.analysis.bundle import load_search_map_bundle
from benchmark.analysis.metrics import LayeredMetrics
from benchmark.analysis.traces import load_trace_meta, load_trace_turns, trace_meta_path_for_case
from benchmark.experiments.index import ExperimentIndex
from benchmark.experiments.layout import traces_dir
from benchmark.experiments.store import ExperimentStore
from benchmark.web.api.deps import get_index, get_store
from benchmark.web.api.schemas import (
    CaseAnalysisModel,
    CaseDetailModel,
    CaseSummaryModel,
    CaseTraceModel,
    PaginatedResponse,
    TraceEventModel,
)

router = APIRouter(prefix="/api/experiments/{experiment_id}/cases", tags=["cases"])

ExperimentIndexDep = Annotated[ExperimentIndex, Depends(get_index)]
ExperimentStoreDep = Annotated[ExperimentStore, Depends(get_store)]


@router.get("", response_model=PaginatedResponse)
def list_cases(
    experiment_id: str,
    index: ExperimentIndexDep,
    completed: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse:
    items = [
        CaseSummaryModel(
            case_id=item.case_id,
            repo=item.repo,
            completed=item.completed,
            partial=item.partial,
            file_recall=item.file_recall,
            file_precision=item.file_precision,
            turns_used=item.turns_used,
            latency_s=item.latency_s,
        )
        for item in index.list_cases(experiment_id, completed=completed, limit=limit, offset=offset)
    ]
    total = index.count_cases(experiment_id, completed=completed)
    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{case_id}", response_model=CaseDetailModel)
def get_case(
    experiment_id: str,
    case_id: str,
    index: ExperimentIndexDep,
) -> CaseDetailModel:
    indexed = index.get_case(experiment_id, case_id)
    if indexed is None:
        raise HTTPException(status_code=404, detail="Case not found")
    payload = json.loads(indexed.result_json)
    return CaseDetailModel(
        case_id=payload["case_id"],
        repo=payload["repo"],
        completed=payload.get("completed", False),
        partial=payload.get("partial", False),
        file_recall=payload.get("file_recall", 0.0),
        file_precision=payload.get("file_precision", 0.0),
        line_coverage=payload.get("line_coverage", 0.0),
        line_precision_matched=payload.get("line_precision_matched", 0.0),
        function_hit_rate=payload.get("function_hit_rate", 0.0),
        turns_used=payload.get("turns_used", 0),
        latency_s=payload.get("latency_s", 0.0),
        returned_files=payload.get("returned_files", {}),
        error=payload.get("error"),
    )


@router.get("/{case_id}/trace", response_model=CaseTraceModel)
def get_case_trace(
    experiment_id: str,
    case_id: str,
    store: ExperimentStoreDep,
) -> CaseTraceModel:
    manifest = store.get(experiment_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    trace_path = traces_dir(manifest.experiment_root) / f"{case_id}.jsonl"
    meta_path = trace_meta_path_for_case(traces_dir(manifest.experiment_root), case_id)
    turns, _ = load_trace_turns(trace_path)
    metadata, _ = load_trace_meta(meta_path)
    events = [
        TraceEventModel(
            event="search_turn",
            timestamp=item.get("timestamp") if isinstance(item, dict) else None,
            data=item if isinstance(item, dict) else {},
        )
        for item in turns
    ]
    return CaseTraceModel(case_id=case_id, events=events, metadata=metadata)


@router.get("/{case_id}/analysis", response_model=CaseAnalysisModel)
def get_case_analysis(
    experiment_id: str,
    case_id: str,
    store: ExperimentStoreDep,
) -> CaseAnalysisModel:
    manifest = store.get(experiment_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    bundle = load_search_map_bundle(manifest.experiment_root)
    cases = bundle.get("cases") if isinstance(bundle, dict) else []
    case_payload = next(
        (item for item in cases if isinstance(item, dict) and item.get("case_id") == case_id),
        None,
    )
    if case_payload is None:
        raise HTTPException(status_code=404, detail="Case analysis not found")

    layered_metrics = case_payload.get("layered_metrics")
    if not isinstance(layered_metrics, dict):
        layered_metrics = {}
    metrics_model = LayeredMetrics.from_dict(layered_metrics)
    explanations = {
        "precision": metrics_model.explain_low_precision(),
        "recall": metrics_model.explain_low_recall(),
    }

    return CaseAnalysisModel(
        case_id=case_id,
        layered_metrics=layered_metrics,
        search_map=case_payload,
        journey_graph=case_payload.get("journey_graph", {}),
        explanations=explanations,
    )
