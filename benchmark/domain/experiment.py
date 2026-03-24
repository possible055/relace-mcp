"""Experiment domain models.

Defines the core entities for experiment lifecycle management,
providing a unified structure for tracking benchmark runs with
full reproducibility metadata.
"""

import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Self


class ExperimentStatus(StrEnum):
    """Experiment lifecycle status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def is_terminal(self) -> bool:
        """Check if this status represents a terminal state."""
        return self in (
            ExperimentStatus.COMPLETED,
            ExperimentStatus.FAILED,
            ExperimentStatus.CANCELLED,
        )


@dataclass
class SamplingConfig:
    """Dataset sampling configuration for reproducibility."""

    strategy: str = "full"
    limit: int | None = None
    seed: int | None = None
    excluded_repos: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "limit": self.limit,
            "seed": self.seed,
            "excluded_repos": self.excluded_repos,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            strategy=data.get("strategy", "full"),
            limit=data.get("limit"),
            seed=data.get("seed"),
            excluded_repos=data.get("excluded_repos", []),
        )


@dataclass
class DatasetInfo:
    """Dataset version and statistics for reproducibility."""

    name: str
    path: str | None = None
    sha256: str | None = None
    case_count: int = 0
    sampling: SamplingConfig = field(default_factory=SamplingConfig)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "sha256": self.sha256,
            "case_count": self.case_count,
            "sampling": self.sampling.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        sampling_data = data.get("sampling", {})
        return cls(
            name=data.get("name", ""),
            path=data.get("path"),
            sha256=data.get("sha256"),
            case_count=data.get("case_count", 0),
            sampling=SamplingConfig.from_dict(sampling_data) if sampling_data else SamplingConfig(),
        )

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        case_count: int = 0,
        sampling: SamplingConfig | None = None,
    ) -> Self:
        """Create DatasetInfo from a dataset file path."""
        sha256 = None
        if path.is_file():
            sha256 = _sha256_file(path)
        return cls(
            name=path.stem,
            path=str(path),
            sha256=sha256,
            case_count=case_count,
            sampling=sampling or SamplingConfig(),
        )


@dataclass
class EnvironmentInfo:
    """Runtime environment information for reproducibility."""

    python_version: str
    platform: str
    relace_mcp_version: str | None = None
    relace_mcp_commit: str | None = None
    git_branch: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "python_version": self.python_version,
            "platform": self.platform,
            "relace_mcp_version": self.relace_mcp_version,
            "relace_mcp_commit": self.relace_mcp_commit,
            "git_branch": self.git_branch,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            python_version=data.get("python_version", ""),
            platform=data.get("platform", ""),
            relace_mcp_version=data.get("relace_mcp_version"),
            relace_mcp_commit=data.get("relace_mcp_commit"),
            git_branch=data.get("git_branch"),
        )

    @classmethod
    def capture(cls) -> Self:
        """Capture current runtime environment information."""
        relace_mcp_version = None
        try:
            relace_mcp_version = importlib_metadata.version("relace-mcp")
        except importlib_metadata.PackageNotFoundError:
            pass

        relace_mcp_commit = None
        git_branch = None
        try:
            project_root = Path(__file__).resolve().parents[2]
            result = subprocess.run(
                ["git", "-C", str(project_root), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
            relace_mcp_commit = result.stdout.strip() or None

            result = subprocess.run(
                ["git", "-C", str(project_root), "rev-parse", "--abbrev-ref", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
            git_branch = result.stdout.strip() or None
        except Exception:
            pass

        return cls(
            python_version=sys.version,
            platform=platform.platform(),
            relace_mcp_version=relace_mcp_version,
            relace_mcp_commit=relace_mcp_commit,
            git_branch=git_branch,
        )


@dataclass
class SearchConfig:
    """Search execution configuration snapshot."""

    provider: str
    model: str
    base_url: str | None = None
    max_turns: int = 10
    temperature: float = 0.7
    timeout_seconds: int = 120
    prompt_file: str | None = None
    retrieval_backend: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "max_turns": self.max_turns,
            "temperature": self.temperature,
            "timeout_seconds": self.timeout_seconds,
            "prompt_file": self.prompt_file,
            "retrieval_backend": self.retrieval_backend,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            provider=data.get("provider", ""),
            model=data.get("model", ""),
            base_url=data.get("base_url"),
            max_turns=data.get("max_turns", 10),
            temperature=data.get("temperature", 0.7),
            timeout_seconds=data.get("timeout_seconds", 120),
            prompt_file=data.get("prompt_file"),
            retrieval_backend=data.get("retrieval_backend"),
        )


@dataclass
class ExperimentMetadata:
    """Unified experiment metadata for lifecycle tracking.

    This is the canonical representation of a benchmark experiment,
    containing all information needed for reproducibility and resume.

    Attributes:
        experiment_id: Unique identifier (format: run--{dataset}--{mode}--{provider}--{timestamp})
        name: Human-readable experiment name
        status: Current lifecycle status
        config_snapshot: Complete configuration at experiment creation time
        dataset_info: Dataset version and sampling configuration
        search_config: Search execution parameters
        environment: Runtime environment information
        experiment_root: Path to experiment output directory
        checkpoint_path: Path to checkpoint file (if resumable)
        created_at: Experiment creation timestamp (UTC)
        updated_at: Last update timestamp (UTC)
        tags: User-defined tags for filtering
    """

    experiment_id: str
    name: str
    status: ExperimentStatus
    config_snapshot: dict[str, Any]
    dataset_info: DatasetInfo
    search_config: SearchConfig
    environment: EnvironmentInfo
    experiment_root: Path
    checkpoint_path: Path | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    tags: list[str] = field(default_factory=list)

    def can_resume(self) -> bool:
        """Check if this experiment can be resumed."""
        if self.status.is_terminal():
            return False
        if self.checkpoint_path is None:
            return False
        return self.checkpoint_path.exists()

    def update_status(self, new_status: ExperimentStatus) -> None:
        """Update experiment status with timestamp."""
        self.status = new_status
        self.updated_at = datetime.now(UTC)

    def get_artifact_path(self, name: str) -> Path:
        """Get path to a named artifact within this experiment."""
        return self.experiment_root / name

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "status": self.status.value,
            "config_snapshot": self.config_snapshot,
            "dataset_info": self.dataset_info.to_dict(),
            "search_config": self.search_config.to_dict(),
            "environment": self.environment.to_dict(),
            "experiment_root": str(self.experiment_root),
            "checkpoint_path": str(self.checkpoint_path) if self.checkpoint_path else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            experiment_id=data["experiment_id"],
            name=data.get("name", data["experiment_id"]),
            status=ExperimentStatus(data.get("status", "pending")),
            config_snapshot=data.get("config_snapshot", {}),
            dataset_info=DatasetInfo.from_dict(data.get("dataset_info", {})),
            search_config=SearchConfig.from_dict(data.get("search_config", {})),
            environment=EnvironmentInfo.from_dict(data.get("environment", {})),
            experiment_root=Path(data["experiment_root"]),
            checkpoint_path=Path(data["checkpoint_path"]) if data.get("checkpoint_path") else None,
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else datetime.now(UTC),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else datetime.now(UTC),
            tags=data.get("tags", []),
        )

    def save(self, path: Path | None = None) -> Path:
        """Save experiment metadata to JSON file."""
        target = path or (self.experiment_root / "experiment.meta.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        return target

    @classmethod
    def load(cls, path: Path) -> Self:
        """Load experiment metadata from JSON file."""
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


def _sha256_file(path: Path) -> str:
    """Compute SHA256 hash of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
