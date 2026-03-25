"""Experiments API router."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from benchmark.experiments.index import ExperimentIndex
from benchmark.experiments.store import ExperimentStore
from benchmark.web.api.deps import get_index, get_store
from benchmark.web.api.schemas import (
    ExperimentDetailModel,
    ExperimentSummaryModel,
    PaginatedResponse,
)

router = APIRouter(prefix="/api/experiments", tags=["experiments"])

ExperimentIndexDep = Annotated[ExperimentIndex, Depends(get_index)]
ExperimentStoreDep = Annotated[ExperimentStore, Depends(get_store)]


@router.get("", response_model=PaginatedResponse)
def list_experiments(
    index: ExperimentIndexDep,
    status: str | None = Query(None),
    dataset: str | None = Query(None),
    kind: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse:
    kinds = [kind] if kind else ["run", "grid"]
    items = [
        ExperimentSummaryModel(
            experiment_id=item.experiment_id,
            kind=item.kind,
            name=item.name,
            status=item.status,
            dataset_name=item.dataset_name,
            case_count=item.case_count,
            created_at=item.created_at,
            completion_rate=item.completion_rate,
            avg_file_recall=item.avg_file_recall,
            avg_file_precision=item.avg_file_precision,
        )
        for item in index.list_experiments(
            kinds=kinds,
            status=status,
            dataset=dataset,
            limit=limit,
            offset=offset,
        )
    ]
    total = index.count_experiments(kinds=kinds, status=status, dataset=dataset)
    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{experiment_id}", response_model=ExperimentDetailModel)
def get_experiment(
    experiment_id: str,
    index: ExperimentIndexDep,
    store: ExperimentStoreDep,
) -> ExperimentDetailModel:
    indexed = index.get_experiment(experiment_id)
    if indexed is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    summary = store.get_summary(experiment_id) or {}
    return ExperimentDetailModel(
        experiment_id=indexed.experiment_id,
        kind=indexed.kind,
        name=indexed.name,
        manifest=json.loads(indexed.manifest_json),
        state=json.loads(indexed.state_json),
        summary=summary if isinstance(summary, dict) else {},
    )


@router.delete("/{experiment_id}")
def delete_experiment(
    experiment_id: str,
    store: ExperimentStoreDep,
    index: ExperimentIndexDep,
) -> dict[str, str]:
    deleted = store.delete(experiment_id, force=True)
    if not deleted:
        raise HTTPException(status_code=404, detail="Experiment not found")
    index.invalidate(experiment_id)
    return {"status": "deleted", "experiment_id": experiment_id}
