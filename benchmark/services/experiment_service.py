"""Experiment lifecycle service.

Provides high-level operations for experiment management including
creation, resumption, status tracking, and result aggregation.
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmark.config.paths import get_experiments_dir
from benchmark.domain.checkpoint import (
    Checkpoint,
    CheckpointManager,
    FileCheckpointRepository,
)
from benchmark.domain.experiment import (
    DatasetInfo,
    EnvironmentInfo,
    ExperimentMetadata,
    ExperimentStatus,
    SamplingConfig,
    SearchConfig,
)
from benchmark.runner.experiment_paths import build_experiment_name
from benchmark.runner.results import BenchmarkResult
from benchmark.schemas import DatasetCase


class ExperimentFilters:
    """Filters for experiment queries."""

    def __init__(
        self,
        *,
        status: ExperimentStatus | list[ExperimentStatus] | None = None,
        dataset: str | None = None,
        tags: list[str] | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ):
        self.status = status
        self.dataset = dataset
        self.tags = tags
        self.created_after = created_after
        self.created_before = created_before

    def matches(self, metadata: ExperimentMetadata) -> bool:
        """Check if an experiment matches the filters."""
        if self.status is not None:
            statuses = self.status if isinstance(self.status, list) else [self.status]
            if metadata.status not in statuses:
                return False

        if self.dataset is not None:
            if metadata.dataset_info.name != self.dataset:
                return False

        if self.tags is not None:
            if not all(tag in metadata.tags for tag in self.tags):
                return False

        if self.created_after is not None:
            if metadata.created_at < self.created_after:
                return False

        if self.created_before is not None:
            if metadata.created_at > self.created_before:
                return False

        return True


class ExperimentService:
    """Service for experiment lifecycle management.

    Provides operations for creating, resuming, querying, and
    updating experiments with integrated checkpoint support.
    """

    METADATA_FILENAME = "experiment.meta.json"

    def __init__(
        self,
        experiments_dir: Path | None = None,
        checkpoint_auto_save_interval: int = 1,
    ):
        self.experiments_dir = experiments_dir or get_experiments_dir()
        self._checkpoint_repo = FileCheckpointRepository(self.experiments_dir)
        self._checkpoint_manager = CheckpointManager(
            self._checkpoint_repo,
            auto_save_interval=checkpoint_auto_save_interval,
        )

    def create(
        self,
        *,
        cases: list[DatasetCase],
        dataset_path: Path | None = None,
        dataset_name: str | None = None,
        search_config: SearchConfig,
        config_snapshot: dict[str, Any] | None = None,
        sampling: SamplingConfig | None = None,
        tags: list[str] | None = None,
        experiment_name_override: str | None = None,
    ) -> ExperimentMetadata:
        """Create a new experiment with metadata and checkpoint.

        Args:
            cases: List of benchmark cases to run
            dataset_path: Path to the dataset file
            dataset_name: Dataset name (derived from path if not provided)
            search_config: Search execution configuration
            config_snapshot: Full configuration for reproducibility
            sampling: Sampling configuration used
            tags: User-defined tags

        Returns:
            Created ExperimentMetadata with initialized checkpoint
        """
        now = datetime.now(UTC)

        name = dataset_name or (dataset_path.stem if dataset_path else "unknown")
        experiment_id = experiment_name_override or build_experiment_name(
            experiment_type="run",
            dataset_id=name,
            search_mode=search_config.retrieval_backend or "agentic",
            provider=search_config.provider,
            timestamp=now,
        )

        experiment_root = self.experiments_dir / experiment_id
        experiment_root.mkdir(parents=True, exist_ok=True)

        dataset_info = (
            DatasetInfo.from_path(
                dataset_path,
                case_count=len(cases),
                sampling=sampling,
            )
            if dataset_path
            else DatasetInfo(
                name=name,
                case_count=len(cases),
                sampling=sampling or SamplingConfig(),
            )
        )

        metadata = ExperimentMetadata(
            experiment_id=experiment_id,
            name=experiment_id,
            status=ExperimentStatus.PENDING,
            config_snapshot=config_snapshot or {},
            dataset_info=dataset_info,
            search_config=search_config,
            environment=EnvironmentInfo.capture(),
            experiment_root=experiment_root,
            checkpoint_path=experiment_root / "checkpoint.json",
            created_at=now,
            updated_at=now,
            tags=tags or [],
        )

        metadata.save()

        case_ids = [c.id for c in cases]
        self._checkpoint_manager.create(experiment_id, case_ids)

        return metadata

    def resume(self, experiment_id: str) -> tuple[ExperimentMetadata, Checkpoint] | None:
        """Resume an experiment from its last checkpoint.

        Args:
            experiment_id: ID of the experiment to resume

        Returns:
            Tuple of (metadata, checkpoint) if resumable, None otherwise
        """
        metadata = self.get(experiment_id)
        if metadata is None:
            return None

        if not metadata.can_resume():
            return None

        checkpoint = self._checkpoint_repo.load(experiment_id)
        if checkpoint is None:
            return None

        metadata.update_status(ExperimentStatus.RUNNING)
        metadata.save()

        return metadata, checkpoint

    def get(self, experiment_id: str) -> ExperimentMetadata | None:
        """Get experiment metadata by ID."""
        metadata_path = self.experiments_dir / experiment_id / self.METADATA_FILENAME
        if not metadata_path.exists():
            return None

        return ExperimentMetadata.load(metadata_path)

    def list(
        self,
        filters: ExperimentFilters | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ExperimentMetadata]:
        """List experiments with optional filtering and pagination."""
        experiments = []

        for metadata in self._iter_experiments():
            if filters is not None and not filters.matches(metadata):
                continue
            experiments.append(metadata)

        experiments.sort(key=lambda m: m.created_at, reverse=True)

        if offset > 0:
            experiments = experiments[offset:]
        if limit is not None:
            experiments = experiments[:limit]

        return experiments

    def update_status(
        self,
        experiment_id: str,
        status: ExperimentStatus,
    ) -> ExperimentMetadata | None:
        """Update experiment status."""
        metadata = self.get(experiment_id)
        if metadata is None:
            return None

        metadata.update_status(status)
        metadata.save()
        return metadata

    def add_result(
        self,
        experiment_id: str,
        result: BenchmarkResult,
    ) -> bool:
        """Add a result and update checkpoint.

        Returns:
            True if successful, False if experiment not found
        """
        checkpoint = self._checkpoint_repo.load(experiment_id)
        if checkpoint is None:
            return False

        self._checkpoint_manager.update(checkpoint, result.case_id, result)
        return True

    def finalize(
        self,
        experiment_id: str,
        success: bool = True,
    ) -> ExperimentMetadata | None:
        """Finalize experiment after completion.

        Args:
            experiment_id: ID of the experiment
            success: Whether the experiment completed successfully

        Returns:
            Updated metadata, or None if not found
        """
        metadata = self.get(experiment_id)
        if metadata is None:
            return None

        checkpoint = self._checkpoint_repo.load(experiment_id)
        if checkpoint is not None:
            self._checkpoint_manager.finalize(checkpoint)

        new_status = ExperimentStatus.COMPLETED if success else ExperimentStatus.FAILED
        metadata.update_status(new_status)
        metadata.save()

        return metadata

    def get_checkpoint(self, experiment_id: str) -> Checkpoint | None:
        """Get the current checkpoint for an experiment."""
        return self._checkpoint_repo.load(experiment_id)

    def can_resume(self, experiment_id: str) -> bool:
        """Check if an experiment can be resumed."""
        metadata = self.get(experiment_id)
        if metadata is None:
            return False
        return metadata.can_resume()

    def delete(self, experiment_id: str, *, force: bool = False) -> bool:
        """Delete an experiment and all its artifacts.

        Args:
            experiment_id: ID of the experiment to delete
            force: If True, delete even if experiment is running

        Returns:
            True if deleted, False if not found or protected
        """
        metadata = self.get(experiment_id)
        if metadata is None:
            return False

        if not force and metadata.status == ExperimentStatus.RUNNING:
            return False

        import shutil

        shutil.rmtree(metadata.experiment_root, ignore_errors=True)
        return True

    def _iter_experiments(self) -> Iterator[ExperimentMetadata]:
        """Iterate over all experiments in the experiments directory."""
        if not self.experiments_dir.exists():
            return

        for entry in self.experiments_dir.iterdir():
            if not entry.is_dir():
                continue

            metadata_path = entry / self.METADATA_FILENAME
            if not metadata_path.exists():
                legacy_report = entry / "reports" / "summary.report.json"
                if legacy_report.exists():
                    metadata = self._migrate_legacy_experiment(entry, legacy_report)
                    if metadata is not None:
                        yield metadata
                continue

            try:
                yield ExperimentMetadata.load(metadata_path)
            except (json.JSONDecodeError, KeyError):
                continue

    def _migrate_legacy_experiment(
        self,
        experiment_dir: Path,
        report_path: Path,
    ) -> ExperimentMetadata | None:
        """Migrate a legacy experiment to the new metadata format.

        Reads the summary.report.json and creates an experiment.meta.json.
        """
        try:
            with report_path.open("r", encoding="utf-8") as f:
                report = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        legacy_meta = report.get("metadata", {})
        experiment_id = experiment_dir.name

        run_info = legacy_meta.get("run", {})
        search_info = legacy_meta.get("search", {})
        env_info = legacy_meta.get("environment", {})
        dataset_info = legacy_meta.get("dataset", {})

        created_at_str = run_info.get("started_at_utc")
        created_at = (
            datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            if created_at_str
            else datetime.now(UTC)
        )

        updated_at_str = run_info.get("completed_at_utc")
        updated_at = (
            datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
            if updated_at_str
            else created_at
        )

        metadata = ExperimentMetadata(
            experiment_id=experiment_id,
            name=experiment_id,
            status=ExperimentStatus.COMPLETED,
            config_snapshot=legacy_meta,
            dataset_info=DatasetInfo(
                name=dataset_info.get("dataset_path", "").split("/")[-1].replace(".jsonl", "")
                if dataset_info.get("dataset_path")
                else "unknown",
                path=dataset_info.get("dataset_path"),
                sha256=dataset_info.get("dataset_sha256"),
                case_count=len(dataset_info.get("cases", [])),
            ),
            search_config=SearchConfig(
                provider=search_info.get("provider", ""),
                model=search_info.get("model", ""),
                base_url=search_info.get("base_url"),
                max_turns=search_info.get("max_turns", 10),
                temperature=search_info.get("temperature", 0.7),
                timeout_seconds=search_info.get("timeout_seconds", 120),
                prompt_file=search_info.get("prompt_file"),
                retrieval_backend=legacy_meta.get("retrieval", {}).get("backend"),
            ),
            environment=EnvironmentInfo(
                python_version=env_info.get("python", ""),
                platform=env_info.get("platform", ""),
                relace_mcp_version=env_info.get("relace_mcp_version"),
                relace_mcp_commit=env_info.get("relace_mcp_git_commit"),
            ),
            experiment_root=experiment_dir,
            created_at=created_at,
            updated_at=updated_at,
        )

        try:
            metadata.save()
        except OSError:
            pass

        return metadata
