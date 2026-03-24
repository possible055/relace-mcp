"""Tests for Checkpoint and CheckpointManager."""

from pathlib import Path

import pytest

from benchmark.domain.checkpoint import (
    Checkpoint,
    CheckpointManager,
    FileCheckpointRepository,
)
from benchmark.runner.results import BenchmarkResult


@pytest.fixture
def sample_result() -> BenchmarkResult:
    return BenchmarkResult(
        case_id="case_001",
        repo="test/repo",
        completed=True,
        returned_files_count=5,
        ground_truth_files_count=3,
        file_recall=0.8,
        file_precision=0.6,
        line_coverage=0.5,
        line_precision_matched=0.7,
        context_line_coverage=0.4,
        context_line_precision_matched=0.6,
        function_hit_rate=0.75,
        functions_hit=3,
        functions_total=4,
        turns_used=3,
        latency_s=2.5,
    )


class TestCheckpoint:
    def test_progress_empty(self):
        checkpoint = Checkpoint(
            experiment_id="test",
            completed_cases=set(),
            pending_cases=["a", "b", "c"],
            partial_results=[],
        )
        assert checkpoint.progress == 0.0

    def test_progress_partial(self):
        checkpoint = Checkpoint(
            experiment_id="test",
            completed_cases={"a"},
            pending_cases=["b", "c"],
            partial_results=[],
        )
        assert abs(checkpoint.progress - 33.33) < 1

    def test_progress_complete(self):
        checkpoint = Checkpoint(
            experiment_id="test",
            completed_cases={"a", "b", "c"},
            pending_cases=[],
            partial_results=[],
        )
        assert checkpoint.progress == 100.0

    def test_is_complete(self):
        checkpoint = Checkpoint(
            experiment_id="test",
            completed_cases={"a", "b"},
            pending_cases=[],
            partial_results=[],
        )
        assert checkpoint.is_complete is True

    def test_is_not_complete(self):
        checkpoint = Checkpoint(
            experiment_id="test",
            completed_cases={"a"},
            pending_cases=["b"],
            partial_results=[],
        )
        assert checkpoint.is_complete is False

    def test_mark_completed(self, sample_result: BenchmarkResult):
        checkpoint = Checkpoint(
            experiment_id="test",
            completed_cases=set(),
            pending_cases=["case_001", "case_002"],
            partial_results=[],
        )
        checkpoint.mark_completed("case_001", sample_result)
        assert "case_001" in checkpoint.completed_cases
        assert "case_001" not in checkpoint.pending_cases
        assert len(checkpoint.partial_results) == 1
        assert checkpoint.last_case_id == "case_001"

    def test_to_dict_and_from_dict(self, sample_result: BenchmarkResult):
        checkpoint = Checkpoint(
            experiment_id="test_exp",
            completed_cases={"case_001"},
            pending_cases=["case_002"],
            partial_results=[sample_result],
            last_case_id="case_001",
        )
        d = checkpoint.to_dict()
        restored = Checkpoint.from_dict(d)
        assert restored.experiment_id == "test_exp"
        assert restored.completed_cases == {"case_001"}
        assert restored.pending_cases == ["case_002"]
        assert len(restored.partial_results) == 1
        assert restored.partial_results[0].case_id == "case_001"


class TestFileCheckpointRepository:
    @pytest.fixture
    def repo(self, tmp_path: Path) -> FileCheckpointRepository:
        return FileCheckpointRepository(tmp_path)

    def test_save_and_load(self, repo: FileCheckpointRepository, sample_result: BenchmarkResult):
        checkpoint = Checkpoint(
            experiment_id="exp_001",
            completed_cases={"a"},
            pending_cases=["b", "c"],
            partial_results=[sample_result],
        )
        path = repo.save(checkpoint)
        assert path.exists()

        loaded = repo.load("exp_001")
        assert loaded is not None
        assert loaded.experiment_id == "exp_001"
        assert loaded.completed_cases == {"a"}

    def test_load_nonexistent(self, repo: FileCheckpointRepository):
        result = repo.load("nonexistent")
        assert result is None

    def test_exists(self, repo: FileCheckpointRepository):
        checkpoint = Checkpoint(
            experiment_id="exp_002",
            completed_cases=set(),
            pending_cases=["a"],
            partial_results=[],
        )
        assert repo.exists("exp_002") is False
        repo.save(checkpoint)
        assert repo.exists("exp_002") is True

    def test_delete(self, repo: FileCheckpointRepository):
        checkpoint = Checkpoint(
            experiment_id="exp_003",
            completed_cases=set(),
            pending_cases=[],
            partial_results=[],
        )
        repo.save(checkpoint)
        assert repo.exists("exp_003") is True
        assert repo.delete("exp_003") is True
        assert repo.exists("exp_003") is False

    def test_delete_nonexistent(self, repo: FileCheckpointRepository):
        assert repo.delete("nonexistent") is False


class TestCheckpointManager:
    @pytest.fixture
    def manager(self, tmp_path: Path) -> CheckpointManager:
        repo = FileCheckpointRepository(tmp_path)
        return CheckpointManager(repo, auto_save_interval=2)

    def test_create(self, manager: CheckpointManager):
        checkpoint = manager.create("exp_001", ["a", "b", "c"])
        assert checkpoint.experiment_id == "exp_001"
        assert checkpoint.pending_cases == ["a", "b", "c"]
        assert len(checkpoint.completed_cases) == 0

    def test_load_or_create_new(self, manager: CheckpointManager):
        checkpoint = manager.load_or_create("exp_002", ["x", "y"])
        assert checkpoint.pending_cases == ["x", "y"]

    def test_load_or_create_existing(self, manager: CheckpointManager):
        manager.create("exp_003", ["a", "b"])
        checkpoint = manager.load_or_create("exp_003", ["a", "b"])
        assert checkpoint.experiment_id == "exp_003"

    def test_load_or_create_different_cases(self, manager: CheckpointManager):
        manager.create("exp_004", ["a", "b"])
        checkpoint = manager.load_or_create("exp_004", ["a", "b", "c"])
        assert checkpoint.pending_cases == ["a", "b", "c"]

    def test_update_auto_save(self, manager: CheckpointManager, sample_result: BenchmarkResult):
        checkpoint = manager.create("exp_005", ["case_001", "case_002", "case_003"])

        sample_result.case_id = "case_001"
        manager.update(checkpoint, "case_001", sample_result)
        assert manager._pending_saves == 1

        sample_result2 = BenchmarkResult(**{**sample_result.__dict__, "case_id": "case_002"})
        manager.update(checkpoint, "case_002", sample_result2)
        assert manager._pending_saves == 0

    def test_can_resume(self, manager: CheckpointManager):
        assert manager.can_resume("nonexistent") is False
        manager.create("exp_006", ["a"])
        assert manager.can_resume("exp_006") is True
