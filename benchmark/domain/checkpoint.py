"""Checkpoint mechanism for experiment resume capability.

Provides atomic checkpoint save/load operations to enable
experiment interruption and recovery.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, Self

from benchmark.runner.results import BenchmarkResult


@dataclass
class Checkpoint:
    """Experiment checkpoint for resume capability.

    Attributes:
        experiment_id: Associated experiment identifier
        completed_cases: Set of completed case IDs
        pending_cases: Ordered list of pending case IDs
        partial_results: Results collected so far
        last_case_id: ID of the last completed case
        created_at: Checkpoint creation timestamp
    """

    experiment_id: str
    completed_cases: set[str]
    pending_cases: list[str]
    partial_results: list[BenchmarkResult]
    last_case_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def progress(self) -> float:
        """Calculate completion progress as a percentage."""
        total = len(self.completed_cases) + len(self.pending_cases)
        if total == 0:
            return 0.0
        return len(self.completed_cases) / total * 100

    @property
    def is_complete(self) -> bool:
        """Check if all cases have been completed."""
        return len(self.pending_cases) == 0

    def mark_completed(self, case_id: str, result: BenchmarkResult) -> None:
        """Mark a case as completed and record its result."""
        self.completed_cases.add(case_id)
        if case_id in self.pending_cases:
            self.pending_cases.remove(case_id)
        self.partial_results.append(result)
        self.last_case_id = case_id
        self.created_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return {
            "experiment_id": self.experiment_id,
            "completed_cases": sorted(self.completed_cases),
            "pending_cases": self.pending_cases,
            "partial_results": [asdict(r) for r in self.partial_results],
            "last_case_id": self.last_case_id,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        from benchmark.analysis.trace_artifacts import ArtifactStatus

        partial_results = []
        for r in data.get("partial_results", []):
            artifact_status: ArtifactStatus = r.get("artifact_status", {})
            partial_results.append(
                BenchmarkResult(
                    case_id=r["case_id"],
                    repo=r["repo"],
                    completed=r["completed"],
                    returned_files_count=r["returned_files_count"],
                    ground_truth_files_count=r["ground_truth_files_count"],
                    file_recall=r["file_recall"],
                    file_precision=r["file_precision"],
                    line_coverage=r["line_coverage"],
                    line_precision_matched=r["line_precision_matched"],
                    context_line_coverage=r["context_line_coverage"],
                    context_line_precision_matched=r["context_line_precision_matched"],
                    function_hit_rate=r["function_hit_rate"],
                    functions_hit=r["functions_hit"],
                    functions_total=r["functions_total"],
                    turns_used=r["turns_used"],
                    latency_s=r["latency_s"],
                    partial=r.get("partial", False),
                    error=r.get("error"),
                    returned_files=r.get("returned_files", {}),
                    trace_path=r.get("trace_path"),
                    trace_meta_path=r.get("trace_meta_path"),
                    artifact_status=artifact_status,
                    hints_used=r.get("hints_used", 0),
                    search_mode=r.get("search_mode", "agentic"),
                    retrieval_backend=r.get("retrieval_backend"),
                    retrieval_latency_s=r.get("retrieval_latency_s"),
                    reindex_action=r.get("reindex_action"),
                )
            )

        return cls(
            experiment_id=data["experiment_id"],
            completed_cases=set(data.get("completed_cases", [])),
            pending_cases=data.get("pending_cases", []),
            partial_results=partial_results,
            last_case_id=data.get("last_case_id"),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else datetime.now(UTC),
        )


class CheckpointRepository(Protocol):
    """Protocol for checkpoint persistence."""

    def save(self, checkpoint: Checkpoint) -> Path:
        """Save checkpoint atomically."""
        ...

    def load(self, experiment_id: str) -> Checkpoint | None:
        """Load checkpoint for an experiment."""
        ...

    def exists(self, experiment_id: str) -> bool:
        """Check if a checkpoint exists."""
        ...

    def delete(self, experiment_id: str) -> bool:
        """Delete checkpoint after successful completion."""
        ...


class FileCheckpointRepository:
    """File-based checkpoint repository with atomic writes."""

    CHECKPOINT_FILENAME = "checkpoint.json"

    def __init__(self, experiments_dir: Path):
        self.experiments_dir = experiments_dir

    def _checkpoint_path(self, experiment_id: str) -> Path:
        return self.experiments_dir / experiment_id / self.CHECKPOINT_FILENAME

    def save(self, checkpoint: Checkpoint) -> Path:
        """Save checkpoint atomically using write-then-rename."""
        path = self._checkpoint_path(checkpoint.experiment_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(checkpoint.to_dict(), f, indent=2, ensure_ascii=False)

        tmp_path.rename(path)
        return path

    def load(self, experiment_id: str) -> Checkpoint | None:
        """Load checkpoint for an experiment."""
        path = self._checkpoint_path(experiment_id)
        if not path.exists():
            return None

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return Checkpoint.from_dict(data)

    def exists(self, experiment_id: str) -> bool:
        """Check if a checkpoint exists."""
        return self._checkpoint_path(experiment_id).exists()

    def delete(self, experiment_id: str) -> bool:
        """Delete checkpoint after successful completion."""
        path = self._checkpoint_path(experiment_id)
        if path.exists():
            path.unlink()
            return True
        return False


class CheckpointManager:
    """High-level checkpoint management with auto-save."""

    def __init__(
        self,
        repository: CheckpointRepository,
        auto_save_interval: int = 1,
    ):
        self.repository = repository
        self.auto_save_interval = auto_save_interval
        self._pending_saves = 0

    def create(
        self,
        experiment_id: str,
        all_case_ids: list[str],
    ) -> Checkpoint:
        """Create a new checkpoint for an experiment."""
        checkpoint = Checkpoint(
            experiment_id=experiment_id,
            completed_cases=set(),
            pending_cases=list(all_case_ids),
            partial_results=[],
        )
        self.repository.save(checkpoint)
        return checkpoint

    def load_or_create(
        self,
        experiment_id: str,
        all_case_ids: list[str],
    ) -> Checkpoint:
        """Load existing checkpoint or create new one.

        If a checkpoint exists but has different case IDs, creates a new one.
        """
        existing = self.repository.load(experiment_id)
        if existing is not None:
            existing_all = existing.completed_cases | set(existing.pending_cases)
            if existing_all == set(all_case_ids):
                return existing
        return self.create(experiment_id, all_case_ids)

    def update(
        self,
        checkpoint: Checkpoint,
        case_id: str,
        result: BenchmarkResult,
    ) -> None:
        """Update checkpoint with a completed case."""
        checkpoint.mark_completed(case_id, result)
        self._pending_saves += 1

        if self._pending_saves >= self.auto_save_interval:
            self.repository.save(checkpoint)
            self._pending_saves = 0

    def finalize(self, checkpoint: Checkpoint) -> None:
        """Finalize checkpoint after experiment completion."""
        if self._pending_saves > 0:
            self.repository.save(checkpoint)
            self._pending_saves = 0

    def cleanup(self, experiment_id: str) -> bool:
        """Remove checkpoint after successful completion."""
        return self.repository.delete(experiment_id)

    def can_resume(self, experiment_id: str) -> bool:
        """Check if an experiment can be resumed."""
        return self.repository.exists(experiment_id)
