"""Tests for ExperimentService."""

from pathlib import Path

import pytest

from benchmark.domain.experiment import (
    ExperimentStatus,
    SearchConfig,
)
from benchmark.schemas import DatasetCase, GroundTruthEntry
from benchmark.services.experiment_service import (
    ExperimentFilters,
    ExperimentService,
)


@pytest.fixture
def experiments_dir(tmp_path: Path) -> Path:
    return tmp_path / "experiments"


@pytest.fixture
def service(experiments_dir: Path) -> ExperimentService:
    return ExperimentService(experiments_dir=experiments_dir)


@pytest.fixture
def sample_cases() -> list[DatasetCase]:
    return [
        DatasetCase(
            id="case_001",
            query="Find the login function",
            repo="test/repo",
            base_commit="abc123",
            hard_gt=[
                GroundTruthEntry(
                    path="src/auth.py",
                    function="login",
                    range=(10, 30),
                )
            ],
        ),
        DatasetCase(
            id="case_002",
            query="Find the logout function",
            repo="test/repo",
            base_commit="abc123",
            hard_gt=[
                GroundTruthEntry(
                    path="src/auth.py",
                    function="logout",
                    range=(35, 50),
                )
            ],
        ),
    ]


@pytest.fixture
def sample_search_config() -> SearchConfig:
    return SearchConfig(
        provider="openai",
        model="gpt-4",
        max_turns=5,
        temperature=0.7,
    )


class TestExperimentFilters:
    def test_matches_status(self, experiments_dir: Path):
        from benchmark.domain.experiment import (
            DatasetInfo,
            EnvironmentInfo,
            ExperimentMetadata,
        )

        metadata = ExperimentMetadata(
            experiment_id="test",
            name="test",
            status=ExperimentStatus.COMPLETED,
            config_snapshot={},
            dataset_info=DatasetInfo(name="test"),
            search_config=SearchConfig(provider="openai", model="gpt-4"),
            environment=EnvironmentInfo(python_version="3.12", platform="Linux"),
            experiment_root=experiments_dir / "test",
        )

        filters = ExperimentFilters(status=ExperimentStatus.COMPLETED)
        assert filters.matches(metadata) is True

        filters = ExperimentFilters(status=ExperimentStatus.RUNNING)
        assert filters.matches(metadata) is False

    def test_matches_dataset(self, experiments_dir: Path):
        from benchmark.domain.experiment import (
            DatasetInfo,
            EnvironmentInfo,
            ExperimentMetadata,
        )

        metadata = ExperimentMetadata(
            experiment_id="test",
            name="test",
            status=ExperimentStatus.COMPLETED,
            config_snapshot={},
            dataset_info=DatasetInfo(name="locbench_v1"),
            search_config=SearchConfig(provider="openai", model="gpt-4"),
            environment=EnvironmentInfo(python_version="3.12", platform="Linux"),
            experiment_root=experiments_dir / "test",
        )

        filters = ExperimentFilters(dataset="locbench_v1")
        assert filters.matches(metadata) is True

        filters = ExperimentFilters(dataset="other_dataset")
        assert filters.matches(metadata) is False

    def test_matches_tags(self, experiments_dir: Path):
        from benchmark.domain.experiment import (
            DatasetInfo,
            EnvironmentInfo,
            ExperimentMetadata,
        )

        metadata = ExperimentMetadata(
            experiment_id="test",
            name="test",
            status=ExperimentStatus.COMPLETED,
            config_snapshot={},
            dataset_info=DatasetInfo(name="test"),
            search_config=SearchConfig(provider="openai", model="gpt-4"),
            environment=EnvironmentInfo(python_version="3.12", platform="Linux"),
            experiment_root=experiments_dir / "test",
            tags=["baseline", "fast"],
        )

        filters = ExperimentFilters(tags=["baseline"])
        assert filters.matches(metadata) is True

        filters = ExperimentFilters(tags=["baseline", "fast"])
        assert filters.matches(metadata) is True

        filters = ExperimentFilters(tags=["slow"])
        assert filters.matches(metadata) is False


class TestExperimentService:
    def test_create_experiment(
        self,
        service: ExperimentService,
        sample_cases: list[DatasetCase],
        sample_search_config: SearchConfig,
    ):
        metadata = service.create(
            cases=sample_cases,
            search_config=sample_search_config,
            dataset_name="test_dataset",
            tags=["test"],
        )

        assert metadata.experiment_id is not None
        assert metadata.status == ExperimentStatus.PENDING
        assert metadata.dataset_info.name == "test_dataset"
        assert metadata.dataset_info.case_count == 2
        assert metadata.tags == ["test"]
        assert metadata.experiment_root.exists()

        checkpoint = service.get_checkpoint(metadata.experiment_id)
        assert checkpoint is not None
        assert len(checkpoint.pending_cases) == 2

    def test_get_experiment(
        self,
        service: ExperimentService,
        sample_cases: list[DatasetCase],
        sample_search_config: SearchConfig,
    ):
        created = service.create(
            cases=sample_cases,
            search_config=sample_search_config,
        )

        fetched = service.get(created.experiment_id)
        assert fetched is not None
        assert fetched.experiment_id == created.experiment_id

    def test_get_nonexistent(self, service: ExperimentService):
        result = service.get("nonexistent_id")
        assert result is None

    def test_list_experiments(
        self,
        service: ExperimentService,
        sample_cases: list[DatasetCase],
        sample_search_config: SearchConfig,
    ):
        service.create(cases=sample_cases, search_config=sample_search_config, dataset_name="ds1")
        service.create(cases=sample_cases, search_config=sample_search_config, dataset_name="ds2")

        experiments = service.list()
        assert len(experiments) == 2

    def test_list_with_filters(
        self,
        service: ExperimentService,
        sample_cases: list[DatasetCase],
        sample_search_config: SearchConfig,
    ):
        exp1 = service.create(
            cases=sample_cases,
            search_config=sample_search_config,
            dataset_name="locbench",
        )
        service.create(
            cases=sample_cases,
            search_config=sample_search_config,
            dataset_name="other",
        )

        filters = ExperimentFilters(dataset="locbench")
        experiments = service.list(filters=filters)
        assert len(experiments) == 1
        assert experiments[0].experiment_id == exp1.experiment_id

    def test_update_status(
        self,
        service: ExperimentService,
        sample_cases: list[DatasetCase],
        sample_search_config: SearchConfig,
    ):
        created = service.create(cases=sample_cases, search_config=sample_search_config)
        assert created.status == ExperimentStatus.PENDING

        updated = service.update_status(created.experiment_id, ExperimentStatus.RUNNING)
        assert updated is not None
        assert updated.status == ExperimentStatus.RUNNING

        fetched = service.get(created.experiment_id)
        assert fetched.status == ExperimentStatus.RUNNING

    def test_finalize_success(
        self,
        service: ExperimentService,
        sample_cases: list[DatasetCase],
        sample_search_config: SearchConfig,
    ):
        created = service.create(cases=sample_cases, search_config=sample_search_config)

        finalized = service.finalize(created.experiment_id, success=True)
        assert finalized is not None
        assert finalized.status == ExperimentStatus.COMPLETED

    def test_finalize_failure(
        self,
        service: ExperimentService,
        sample_cases: list[DatasetCase],
        sample_search_config: SearchConfig,
    ):
        created = service.create(cases=sample_cases, search_config=sample_search_config)

        finalized = service.finalize(created.experiment_id, success=False)
        assert finalized is not None
        assert finalized.status == ExperimentStatus.FAILED

    def test_can_resume(
        self,
        service: ExperimentService,
        sample_cases: list[DatasetCase],
        sample_search_config: SearchConfig,
    ):
        created = service.create(cases=sample_cases, search_config=sample_search_config)
        assert service.can_resume(created.experiment_id) is True

        service.finalize(created.experiment_id, success=True)
        assert service.can_resume(created.experiment_id) is False

    def test_delete_experiment(
        self,
        service: ExperimentService,
        sample_cases: list[DatasetCase],
        sample_search_config: SearchConfig,
    ):
        created = service.create(cases=sample_cases, search_config=sample_search_config)
        assert service.get(created.experiment_id) is not None

        result = service.delete(created.experiment_id)
        assert result is True
        assert service.get(created.experiment_id) is None

    def test_delete_running_blocked(
        self,
        service: ExperimentService,
        sample_cases: list[DatasetCase],
        sample_search_config: SearchConfig,
    ):
        created = service.create(cases=sample_cases, search_config=sample_search_config)
        service.update_status(created.experiment_id, ExperimentStatus.RUNNING)

        result = service.delete(created.experiment_id, force=False)
        assert result is False
        assert service.get(created.experiment_id) is not None

    def test_delete_running_forced(
        self,
        service: ExperimentService,
        sample_cases: list[DatasetCase],
        sample_search_config: SearchConfig,
    ):
        created = service.create(cases=sample_cases, search_config=sample_search_config)
        service.update_status(created.experiment_id, ExperimentStatus.RUNNING)

        result = service.delete(created.experiment_id, force=True)
        assert result is True
        assert service.get(created.experiment_id) is None
