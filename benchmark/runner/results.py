import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BenchmarkResult:
    case_id: str
    repo: str
    completed: bool
    returned_files_count: int
    ground_truth_files_count: int
    file_recall: float
    file_precision: float
    line_coverage: float
    line_precision_matched: float
    context_line_coverage: float
    context_line_precision_matched: float
    function_hit_rate: float
    functions_hit: int
    functions_total: int
    turns_used: int
    latency_s: float
    partial: bool = False
    error: str | None = None
    returned_files: dict[str, list[list[int]]] = field(default_factory=dict)
    raw_result: dict[str, Any] = field(default_factory=dict)
    trace_path: str | None = None
    hints_used: int = 0
    search_mode: str = "agentic"
    retrieval_backend: str | None = None
    retrieval_latency_s: float | None = None
    reindex_action: str | None = None


@dataclass
class BenchmarkSummary:
    metadata: dict[str, Any]
    total_cases: int
    stats: dict[str, float]
    results: list[BenchmarkResult]

    def to_dict(self) -> dict[str, Any]:
        d = {
            "metadata": self.metadata,
            "total_cases": self.total_cases,
            **self.stats,
            "results": [asdict(r) for r in self.results],
        }
        return d

    def save(self, output_path: Path, report_path: Path | None = None) -> None:
        """Save results to JSONL and summary to a report JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        jsonl_path = (
            output_path if output_path.suffix == ".jsonl" else output_path.with_suffix(".jsonl")
        )

        with jsonl_path.open("w", encoding="utf-8") as f:
            for r in self.results:
                f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")

        summary_dict = self.to_dict()
        del summary_dict["results"]

        resolved_report_path = report_path or jsonl_path.with_suffix(".report.json")
        resolved_report_path.parent.mkdir(parents=True, exist_ok=True)
        with resolved_report_path.open("w", encoding="utf-8") as f:
            json.dump(summary_dict, f, indent=2, ensure_ascii=False)
