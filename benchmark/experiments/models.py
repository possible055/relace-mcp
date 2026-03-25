import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self

from ..analysis.traces import ArtifactStatus
from .layout import manifest_path, results_path, state_path, summary_path

ExperimentKind = Literal["run", "grid", "trial"]
ExperimentStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


@dataclass
class ExperimentManifest:
    experiment_id: str
    kind: ExperimentKind
    name: str
    experiment_root: Path
    created_at: datetime
    dataset: dict[str, Any] = field(default_factory=dict)
    search: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    parent_experiment_id: str | None = None
    tags: list[str] = field(default_factory=list)
    config_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "kind": self.kind,
            "name": self.name,
            "experiment_root": str(self.experiment_root),
            "created_at": self.created_at.isoformat(),
            "dataset": self.dataset,
            "search": self.search,
            "environment": self.environment,
            "artifacts": self.artifacts,
            "parent_experiment_id": self.parent_experiment_id,
            "tags": self.tags,
            "config_snapshot": self.config_snapshot,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            experiment_id=str(data["experiment_id"]),
            kind=data.get("kind", "run"),
            name=str(data.get("name", data["experiment_id"])),
            experiment_root=Path(data["experiment_root"]),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else datetime.now(UTC),
            dataset=data.get("dataset", {}),
            search=data.get("search", {}),
            environment=data.get("environment", {}),
            artifacts=data.get("artifacts", {}),
            parent_experiment_id=data.get("parent_experiment_id"),
            tags=list(data.get("tags", [])),
            config_snapshot=data.get("config_snapshot", {}),
        )

    def save(self) -> Path:
        path = manifest_path(self.experiment_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", "utf-8")
        return path

    @classmethod
    def load(cls, experiment_root: Path) -> Self:
        return cls.from_dict(json.loads(manifest_path(experiment_root).read_text("utf-8")))


@dataclass
class ExperimentStateModel:
    status: ExperimentStatus
    total_cases: int
    completed_cases: int
    failed_cases: int
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def pending_cases(self) -> int:
        return max(self.total_cases - self.completed_cases - self.failed_cases, 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "total_cases": self.total_cases,
            "completed_cases": self.completed_cases,
            "failed_cases": self.failed_cases,
            "pending_cases": self.pending_cases,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            status=data.get("status", "pending"),
            total_cases=int(data.get("total_cases", 0)),
            completed_cases=int(data.get("completed_cases", 0)),
            failed_cases=int(data.get("failed_cases", 0)),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else datetime.now(UTC),
        )

    def save(self, experiment_root: Path) -> Path:
        path = state_path(experiment_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", "utf-8")
        return path

    @classmethod
    def load(cls, experiment_root: Path) -> Self:
        return cls.from_dict(json.loads(state_path(experiment_root).read_text("utf-8")))


@dataclass
class CaseResult:
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
    trace_path: str | None = None
    trace_meta_path: str | None = None
    artifact_status: ArtifactStatus = field(default_factory=dict)
    hints_used: int = 0
    search_mode: str = "agentic"
    retrieval_backend: str | None = None
    retrieval_latency_s: float | None = None
    reindex_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            case_id=str(data["case_id"]),
            repo=str(data["repo"]),
            completed=bool(data.get("completed", False)),
            returned_files_count=int(data.get("returned_files_count", 0)),
            ground_truth_files_count=int(data.get("ground_truth_files_count", 0)),
            file_recall=float(data.get("file_recall", 0.0)),
            file_precision=float(data.get("file_precision", 0.0)),
            line_coverage=float(data.get("line_coverage", 0.0)),
            line_precision_matched=float(data.get("line_precision_matched", 0.0)),
            context_line_coverage=float(data.get("context_line_coverage", 0.0)),
            context_line_precision_matched=float(data.get("context_line_precision_matched", 0.0)),
            function_hit_rate=float(data.get("function_hit_rate", 0.0)),
            functions_hit=int(data.get("functions_hit", 0)),
            functions_total=int(data.get("functions_total", 0)),
            turns_used=int(data.get("turns_used", 0)),
            latency_s=float(data.get("latency_s", 0.0)),
            partial=bool(data.get("partial", False)),
            error=data.get("error"),
            returned_files=data.get("returned_files", {}),
            trace_path=data.get("trace_path"),
            trace_meta_path=data.get("trace_meta_path"),
            artifact_status=data.get("artifact_status", {}),
            hints_used=int(data.get("hints_used", 0)),
            search_mode=str(data.get("search_mode", "agentic")),
            retrieval_backend=data.get("retrieval_backend"),
            retrieval_latency_s=data.get("retrieval_latency_s"),
            reindex_action=data.get("reindex_action"),
        )


@dataclass
class RunSummary:
    manifest: ExperimentManifest
    state: ExperimentStateModel
    stats: dict[str, float]
    results: list[CaseResult]

    @property
    def total_cases(self) -> int:
        return self.state.total_cases

    @property
    def metadata(self) -> dict[str, Any]:
        dataset_payload = dict(self.manifest.dataset)
        if "path" in dataset_payload and "dataset_path" not in dataset_payload:
            dataset_payload["dataset_path"] = dataset_payload["path"]
        if "sha256" in dataset_payload and "dataset_sha256" not in dataset_payload:
            dataset_payload["dataset_sha256"] = dataset_payload["sha256"]
        return {
            "experiment": {
                "id": self.manifest.experiment_id,
                "type": self.manifest.kind,
                "name": self.manifest.name,
                "root": str(self.manifest.experiment_root),
                "parent_id": self.manifest.parent_experiment_id,
                "parent_root": self.manifest.config_snapshot.get("parent_experiment_root"),
            },
            "dataset": dataset_payload,
            "search": self.manifest.search,
            "environment": self.manifest.environment,
            "artifacts": self.manifest.artifacts,
            "config_snapshot": self.manifest.config_snapshot,
            "state": self.state.to_dict(),
        }

    def summary_payload(self) -> dict[str, Any]:
        return {
            "experiment_id": self.manifest.experiment_id,
            "kind": self.manifest.kind,
            "name": self.manifest.name,
            "total_cases": self.total_cases,
            "metadata": self.metadata,
            "manifest": self.manifest.to_dict(),
            "state": self.state.to_dict(),
            "stats": self.stats,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata,
            "total_cases": self.total_cases,
            **self.stats,
            "results": [result.to_dict() for result in self.results],
        }

    def save(self, output_path: Path, report_path: Path | None = None) -> None:
        experiment_root = (
            output_path.parent.parent if output_path.name.endswith(".jsonl") else output_path
        )
        experiment_root.mkdir(parents=True, exist_ok=True)

        self.manifest.experiment_root = experiment_root
        self.manifest.save()
        self.state.save(experiment_root)

        results_file = (
            output_path if output_path.suffix == ".jsonl" else results_path(experiment_root)
        )
        results_file.parent.mkdir(parents=True, exist_ok=True)
        with results_file.open("w", encoding="utf-8") as handle:
            for result in self.results:
                handle.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")

        summary_file = report_path or summary_path(experiment_root)
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        summary_file.write_text(
            json.dumps(self.summary_payload(), ensure_ascii=False, indent=2) + "\n",
            "utf-8",
        )


# Compatibility aliases while the rest of the codebase completes the rename.
BenchmarkResult = CaseResult
BenchmarkSummary = RunSummary
ExperimentState = ExperimentStateModel
