from typing import Any

from pydantic import BaseModel


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    limit: int
    offset: int


class ExperimentSummaryModel(BaseModel):
    experiment_id: str
    kind: str
    name: str
    status: str
    dataset_name: str
    case_count: int
    created_at: str
    completion_rate: float
    avg_file_recall: float
    avg_file_precision: float


class ExperimentDetailModel(BaseModel):
    experiment_id: str
    kind: str
    name: str
    manifest: dict[str, Any]
    state: dict[str, Any]
    summary: dict[str, Any]


class CaseSummaryModel(BaseModel):
    case_id: str
    repo: str
    completed: bool
    partial: bool
    file_recall: float
    file_precision: float
    turns_used: int
    latency_s: float


class CaseDetailModel(BaseModel):
    case_id: str
    repo: str
    completed: bool
    partial: bool
    file_recall: float
    file_precision: float
    line_coverage: float
    line_precision_matched: float
    function_hit_rate: float
    turns_used: int
    latency_s: float
    returned_files: dict[str, list[list[int]]]
    error: str | None = None


class TraceEventModel(BaseModel):
    event: str
    timestamp: str | None = None
    data: dict[str, Any]


class CaseTraceModel(BaseModel):
    case_id: str
    events: list[TraceEventModel]
    metadata: dict[str, Any]


class CaseAnalysisModel(BaseModel):
    case_id: str
    layered_metrics: dict[str, Any]
    search_map: dict[str, Any]
    journey_graph: dict[str, Any]
    explanations: dict[str, list[str]]


class MetricsSummaryModel(BaseModel):
    total_cases: int
    completed_cases: int
    failed_cases: int
    avg_file_recall: float
    avg_file_precision: float
    avg_line_coverage: float
    avg_function_hit_rate: float
    avg_turns_used: float
    avg_latency_s: float
