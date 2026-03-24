"""Tests for ExperimentMetadata and related domain models."""

from pathlib import Path

import pytest

from benchmark.domain.experiment import (
    DatasetInfo,
    EnvironmentInfo,
    ExperimentMetadata,
    ExperimentStatus,
    SamplingConfig,
    SearchConfig,
)


class TestExperimentStatus:
    def test_is_terminal_completed(self):
        assert ExperimentStatus.COMPLETED.is_terminal() is True

    def test_is_terminal_failed(self):
        assert ExperimentStatus.FAILED.is_terminal() is True

    def test_is_terminal_cancelled(self):
        assert ExperimentStatus.CANCELLED.is_terminal() is True

    def test_is_terminal_running(self):
        assert ExperimentStatus.RUNNING.is_terminal() is False

    def test_is_terminal_pending(self):
        assert ExperimentStatus.PENDING.is_terminal() is False


class TestSamplingConfig:
    def test_default_values(self):
        config = SamplingConfig()
        assert config.strategy == "full"
        assert config.limit is None
        assert config.seed is None
        assert config.excluded_repos == []

    def test_to_dict(self):
        config = SamplingConfig(
            strategy="stratified",
            limit=50,
            seed=42,
            excluded_repos=["repo1", "repo2"],
        )
        d = config.to_dict()
        assert d["strategy"] == "stratified"
        assert d["limit"] == 50
        assert d["seed"] == 42
        assert d["excluded_repos"] == ["repo1", "repo2"]

    def test_from_dict(self):
        data = {
            "strategy": "random",
            "limit": 100,
            "seed": 123,
            "excluded_repos": ["a", "b"],
        }
        config = SamplingConfig.from_dict(data)
        assert config.strategy == "random"
        assert config.limit == 100
        assert config.seed == 123
        assert config.excluded_repos == ["a", "b"]


class TestDatasetInfo:
    def test_default_values(self):
        info = DatasetInfo(name="test")
        assert info.name == "test"
        assert info.path is None
        assert info.sha256 is None
        assert info.case_count == 0
        assert info.sampling.strategy == "full"

    def test_to_dict(self):
        info = DatasetInfo(
            name="locbench_v1",
            path="/data/locbench.jsonl",
            sha256="abc123",
            case_count=50,
            sampling=SamplingConfig(strategy="stratified", seed=42),
        )
        d = info.to_dict()
        assert d["name"] == "locbench_v1"
        assert d["path"] == "/data/locbench.jsonl"
        assert d["sha256"] == "abc123"
        assert d["case_count"] == 50
        assert d["sampling"]["strategy"] == "stratified"

    def test_from_dict(self):
        data = {
            "name": "test_dataset",
            "path": "/path/to/data.jsonl",
            "case_count": 25,
        }
        info = DatasetInfo.from_dict(data)
        assert info.name == "test_dataset"
        assert info.case_count == 25


class TestEnvironmentInfo:
    def test_to_dict(self):
        info = EnvironmentInfo(
            python_version="3.12.0",
            platform="Linux-6.1.0",
            relace_mcp_version="0.1.0",
            relace_mcp_commit="abc123",
            git_branch="main",
        )
        d = info.to_dict()
        assert d["python_version"] == "3.12.0"
        assert d["platform"] == "Linux-6.1.0"
        assert d["relace_mcp_version"] == "0.1.0"
        assert d["relace_mcp_commit"] == "abc123"
        assert d["git_branch"] == "main"

    def test_from_dict(self):
        data = {
            "python_version": "3.11.0",
            "platform": "Darwin",
        }
        info = EnvironmentInfo.from_dict(data)
        assert info.python_version == "3.11.0"
        assert info.platform == "Darwin"
        assert info.relace_mcp_version is None

    def test_capture(self):
        info = EnvironmentInfo.capture()
        assert info.python_version != ""
        assert info.platform != ""


class TestSearchConfig:
    def test_to_dict(self):
        config = SearchConfig(
            provider="openai",
            model="gpt-4",
            max_turns=5,
            temperature=0.5,
        )
        d = config.to_dict()
        assert d["provider"] == "openai"
        assert d["model"] == "gpt-4"
        assert d["max_turns"] == 5
        assert d["temperature"] == 0.5

    def test_from_dict(self):
        data = {
            "provider": "anthropic",
            "model": "claude-3",
            "base_url": "https://api.anthropic.com",
        }
        config = SearchConfig.from_dict(data)
        assert config.provider == "anthropic"
        assert config.model == "claude-3"
        assert config.base_url == "https://api.anthropic.com"


class TestExperimentMetadata:
    @pytest.fixture
    def sample_metadata(self, tmp_path: Path) -> ExperimentMetadata:
        return ExperimentMetadata(
            experiment_id="run--test--fast--openai--20260325_120000",
            name="Test Experiment",
            status=ExperimentStatus.PENDING,
            config_snapshot={"mode": "fast"},
            dataset_info=DatasetInfo(name="test", case_count=10),
            search_config=SearchConfig(provider="openai", model="gpt-4"),
            environment=EnvironmentInfo(python_version="3.12", platform="Linux"),
            experiment_root=tmp_path / "experiment",
            checkpoint_path=tmp_path / "experiment" / "checkpoint.json",
            tags=["test", "baseline"],
        )

    def test_can_resume_pending_with_checkpoint(self, sample_metadata: ExperimentMetadata):
        sample_metadata.experiment_root.mkdir(parents=True, exist_ok=True)
        sample_metadata.checkpoint_path.write_text("{}")
        assert sample_metadata.can_resume() is True

    def test_can_resume_completed(self, sample_metadata: ExperimentMetadata):
        sample_metadata.status = ExperimentStatus.COMPLETED
        assert sample_metadata.can_resume() is False

    def test_can_resume_no_checkpoint(self, sample_metadata: ExperimentMetadata):
        sample_metadata.checkpoint_path = None
        assert sample_metadata.can_resume() is False

    def test_update_status(self, sample_metadata: ExperimentMetadata):
        old_updated = sample_metadata.updated_at
        sample_metadata.update_status(ExperimentStatus.RUNNING)
        assert sample_metadata.status == ExperimentStatus.RUNNING
        assert sample_metadata.updated_at > old_updated

    def test_get_artifact_path(self, sample_metadata: ExperimentMetadata):
        path = sample_metadata.get_artifact_path("results/results.jsonl")
        expected = sample_metadata.experiment_root / "results/results.jsonl"
        assert path == expected

    def test_to_dict_and_from_dict(self, sample_metadata: ExperimentMetadata):
        d = sample_metadata.to_dict()
        restored = ExperimentMetadata.from_dict(d)
        assert restored.experiment_id == sample_metadata.experiment_id
        assert restored.name == sample_metadata.name
        assert restored.status == sample_metadata.status
        assert restored.tags == sample_metadata.tags
        assert restored.dataset_info.name == sample_metadata.dataset_info.name

    def test_save_and_load(self, sample_metadata: ExperimentMetadata):
        sample_metadata.experiment_root.mkdir(parents=True, exist_ok=True)
        path = sample_metadata.save()
        assert path.exists()

        loaded = ExperimentMetadata.load(path)
        assert loaded.experiment_id == sample_metadata.experiment_id
        assert loaded.status == sample_metadata.status
