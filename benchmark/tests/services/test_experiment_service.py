"""Tests for ExperimentStore."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from benchmark.experiments.models import BenchmarkResult, ExperimentManifest, ExperimentState
from benchmark.experiments.store import ExperimentFilters, ExperimentService
from benchmark.schemas import DatasetCase, GroundTruthEntry
from relace_mcp.config import RelaceConfig


@pytest.fixture
def experiments_dir(tmp_path: Path) -> Path:
    return tmp_path / "experiments"


@pytest.fixture
def service(experiments_dir: Path) -> ExperimentService:
    return ExperimentService(experiments_dir=experiments_dir)


@pytest.fixture
def config() -> RelaceConfig:
    return RelaceConfig(api_key="rlc-test", base_dir=None)


@pytest.fixture
def sample_cases() -> list[DatasetCase]:
    return [
        DatasetCase(
            id="case_001",
            query="Find the login function",
            repo="test/repo",
            base_commit="abc123",
            hard_gt=[GroundTruthEntry(path="src/auth.py", function="login", range=(10, 30))],
        ),
        DatasetCase(
            id="case_002",
            query="Find the logout function",
            repo="test/repo",
            base_commit="abc123",
            hard_gt=[GroundTruthEntry(path="src/auth.py", function="logout", range=(35, 50))],
        ),
    ]


def test_filters_match_manifest_and_state(experiments_dir: Path) -> None:
    manifest = ExperimentManifest(
        experiment_id="exp-1",
        kind="run",
        name="exp-1",
        experiment_root=experiments_dir / "exp-1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        dataset={"name": "locbench_v1"},
        tags=["baseline", "fast"],
    )
    state = ExperimentState(status="completed", total_cases=2, completed_cases=2, failed_cases=0)

    assert ExperimentFilters(status="completed").matches(manifest, state) is True
    assert ExperimentFilters(status="failed").matches(manifest, state) is False
    assert ExperimentFilters(dataset="locbench_v1").matches(manifest, state) is True
    assert ExperimentFilters(kind="run").matches(manifest, state) is True
    assert ExperimentFilters(tags=["baseline"]).matches(manifest, state) is True


def test_create_and_get_experiment(
    service: ExperimentService,
    config: RelaceConfig,
    sample_cases: list[DatasetCase],
) -> None:
    manifest = service.create(
        experiment_root="run-a",
        kind="run",
        cases=sample_cases,
        config=config,
        run_config={"dataset": "test_dataset", "dataset_path": "/tmp/test_dataset.jsonl"},
    )

    assert manifest.experiment_id == "run-a"
    assert manifest.kind == "run"
    assert manifest.dataset["name"] == "test_dataset"
    assert manifest.dataset["case_count"] == 2

    fetched = service.get("run-a")
    assert fetched is not None
    assert fetched.experiment_id == "run-a"

    state = service.get_state("run-a")
    assert state is not None
    assert state.status == "pending"
    assert state.total_cases == 2


def test_list_with_filters(
    service: ExperimentService,
    config: RelaceConfig,
    sample_cases: list[DatasetCase],
) -> None:
    service.create(
        experiment_root="run-a",
        kind="run",
        cases=sample_cases,
        config=config,
        run_config={"dataset": "locbench"},
    )
    service.create(
        experiment_root="grid-a",
        kind="grid",
        cases=[],
        config=config,
        run_config={"dataset": "locbench"},
    )

    runs = service.list(filters=ExperimentFilters(kind="run"))
    assert len(runs) == 1
    assert runs[0][0].experiment_id == "run-a"


def test_append_result_refreshes_state(
    service: ExperimentService,
    config: RelaceConfig,
    sample_cases: list[DatasetCase],
) -> None:
    manifest = service.create(
        experiment_root="run-a",
        kind="run",
        cases=sample_cases,
        config=config,
        run_config={"dataset": "locbench"},
    )
    service.append_result(
        manifest.experiment_id,
        BenchmarkResult(
            case_id="case_001",
            repo="test/repo",
            completed=True,
            returned_files_count=1,
            ground_truth_files_count=1,
            file_recall=1.0,
            file_precision=1.0,
            line_coverage=1.0,
            line_precision_matched=1.0,
            context_line_coverage=1.0,
            context_line_precision_matched=1.0,
            function_hit_rate=1.0,
            functions_hit=1,
            functions_total=1,
            turns_used=2,
            latency_s=0.5,
        ),
    )

    state = service.get_state(manifest.experiment_id)
    assert state is not None
    assert state.status == "running"
    assert state.completed_cases == 1


def test_delete_experiment(service: ExperimentService, config: RelaceConfig) -> None:
    manifest = service.create(
        experiment_root="run-a",
        kind="run",
        cases=[],
        config=config,
        run_config={"dataset": "locbench"},
    )
    assert service.get(manifest.experiment_id) is not None

    assert service.delete(manifest.experiment_id) is True
    assert service.get(manifest.experiment_id) is None
