import json
from dataclasses import asdict, dataclass
from pathlib import Path
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
    file_f_beta: float
    line_f_beta: float
    joint_f: float
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
    avg_file_f_beta: float
    avg_line_f_beta: float
    avg_joint_f: float
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
            "avg_file_f_beta": self.avg_file_f_beta,
            "avg_line_f_beta": self.avg_line_f_beta,
            "avg_joint_f": self.avg_joint_f,
            "function_cases": self.function_cases,
            "avg_function_hit_rate": self.avg_function_hit_rate,
            "avg_turns": self.avg_turns,
            "avg_latency_ms": self.avg_latency_ms,
            "avg_repo_prep_ms": self.avg_repo_prep_ms,
            "results": [asdict(r) for r in self.results],
        }

    def save(self, output_path: Path) -> None:
        """Save results to JSONL and summary to .report.json."""
        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Save results to .jsonl
        # If output_path is already .jsonl, use it. Otherwise, use .jsonl extension.
        jsonl_path = (
            output_path if output_path.suffix == ".jsonl" else output_path.with_suffix(".jsonl")
        )

        with jsonl_path.open("w", encoding="utf-8") as f:
            for r in self.results:
                f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")

        # 2. Save summary to .report.json (exclude full results list)
        summary_dict = self.to_dict()
        del summary_dict["results"]

        report_path = jsonl_path.with_suffix(".report.json")
        with report_path.open("w", encoding="utf-8") as f:
            json.dump(summary_dict, f, indent=2, ensure_ascii=False)
