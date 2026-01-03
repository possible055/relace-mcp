from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class BenchmarkResult:
    case_id: str
    repo: str
    success: bool
    returned_files_count: int
    ground_truth_files_count: int
    file_recall: float
    file_precision: float
    file_f1: float
    line_coverage: float
    line_precision: float
    line_f1: float
    line_precision_matched: float
    line_iou_matched: float
    function_hit_rate: float
    functions_hit: int
    functions_total: int
    turns_used: int
    latency_ms: float
    repo_prep_ms: float = 0.0
    repo_cached: bool = False
    partial: bool = False
    error: str | None = None


@dataclass
class BenchmarkSummary:
    metadata: dict[str, Any]
    total_cases: int
    success_rate: float
    avg_returned_files: float
    avg_ground_truth_files: float
    avg_file_recall: float
    avg_file_precision: float
    avg_file_f1: float
    avg_line_coverage: float
    avg_line_precision: float
    avg_line_f1: float
    avg_line_precision_matched: float
    avg_line_iou_matched: float
    function_cases: int
    avg_function_hit_rate: float
    avg_turns: float
    avg_latency_ms: float
    avg_repo_prep_ms: float
    results: list[BenchmarkResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata,
            "total_cases": self.total_cases,
            "success_rate": self.success_rate,
            "avg_returned_files": self.avg_returned_files,
            "avg_ground_truth_files": self.avg_ground_truth_files,
            "avg_file_recall": self.avg_file_recall,
            "avg_file_precision": self.avg_file_precision,
            "avg_file_f1": self.avg_file_f1,
            "avg_line_coverage": self.avg_line_coverage,
            "avg_line_precision": self.avg_line_precision,
            "avg_line_f1": self.avg_line_f1,
            "avg_line_precision_matched": self.avg_line_precision_matched,
            "avg_line_iou_matched": self.avg_line_iou_matched,
            "function_cases": self.function_cases,
            "avg_function_hit_rate": self.avg_function_hit_rate,
            "avg_turns": self.avg_turns,
            "avg_latency_ms": self.avg_latency_ms,
            "avg_repo_prep_ms": self.avg_repo_prep_ms,
            "results": [asdict(r) for r in self.results],
        }
