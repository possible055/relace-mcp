"""Experiment storage and query helpers."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmark.config.paths import get_experiments_dir
from benchmark.schemas import DatasetCase

from .layout import (
    MANIFEST_FILENAME,
    manifest_path,
    results_path,
    state_path,
    summary_path,
)
from .metadata import build_experiment_manifest, build_initial_state
from .models import (
    BenchmarkResult,
    BenchmarkSummary,
    ExperimentManifest,
    ExperimentState,
)


class ExperimentFilters:
    def __init__(
        self,
        *,
        status: str | list[str] | None = None,
        dataset: str | None = None,
        kind: str | list[str] | None = None,
        tags: list[str] | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ):
        self.status = status
        self.dataset = dataset
        self.kind = kind
        self.tags = tags
        self.created_after = created_after
        self.created_before = created_before

    def matches(self, manifest: ExperimentManifest, state: ExperimentState | None) -> bool:
        if self.status is not None:
            statuses = self.status if isinstance(self.status, list) else [self.status]
            if state is None or state.status not in statuses:
                return False
        if self.dataset is not None and manifest.dataset.get("name") != self.dataset:
            return False
        if self.kind is not None:
            kinds = self.kind if isinstance(self.kind, list) else [self.kind]
            if manifest.kind not in kinds:
                return False
        if self.tags is not None and not all(tag in manifest.tags for tag in self.tags):
            return False
        if self.created_after is not None and manifest.created_at < self.created_after:
            return False
        if self.created_before is not None and manifest.created_at > self.created_before:
            return False
        return True


class ExperimentStore:
    def __init__(self, experiments_dir: Path | None = None):
        self.experiments_dir = experiments_dir or get_experiments_dir()

    def _resolve_root(self, experiment_root: str | Path) -> Path:
        candidate = Path(experiment_root)
        if candidate.is_absolute():
            return candidate
        return self.experiments_dir / candidate

    def create(
        self,
        *,
        experiment_root: str | Path,
        kind: str,
        cases: list[DatasetCase],
        config: Any,
        run_config: dict[str, Any] | None = None,
    ) -> ExperimentManifest:
        root = self._resolve_root(experiment_root)
        root.mkdir(parents=True, exist_ok=True)
        manifest = build_experiment_manifest(
            config=config,
            experiment_id=root.name,
            kind=kind,
            experiment_root=root,
            cases=cases,
            run_config=run_config,
            created_at=datetime.now(UTC),
        )
        manifest.save()
        build_initial_state(len(cases)).save(root)
        return manifest

    def get(self, experiment_id: str) -> ExperimentManifest | None:
        root = self.experiments_dir / experiment_id
        path = manifest_path(root)
        if not path.exists():
            return None
        return ExperimentManifest.load(root)

    def get_state(self, experiment_id: str) -> ExperimentState | None:
        root = self.experiments_dir / experiment_id
        path = state_path(root)
        if not path.exists():
            return None
        return ExperimentState.load(root)

    def get_summary(self, experiment_id: str) -> dict[str, Any] | None:
        root = self.experiments_dir / experiment_id
        path = summary_path(root)
        if not path.exists():
            return None
        return json.loads(path.read_text("utf-8"))

    def load_results(self, experiment_id: str) -> list[BenchmarkResult]:
        root = self.experiments_dir / experiment_id
        path = results_path(root)
        if not path.exists():
            return []
        results: list[BenchmarkResult] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                payload = json.loads(stripped)
                if isinstance(payload, dict):
                    results.append(BenchmarkResult.from_dict(payload))
        return results

    def list(
        self,
        filters: ExperimentFilters | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[tuple[ExperimentManifest, ExperimentState | None]]:
        items: list[tuple[ExperimentManifest, ExperimentState | None]] = []
        for manifest in self._iter_manifests():
            state = self._load_state_for_root(manifest.experiment_root)
            if filters is not None and not filters.matches(manifest, state):
                continue
            items.append((manifest, state))
        items.sort(key=lambda item: item[0].created_at, reverse=True)
        if offset > 0:
            items = items[offset:]
        if limit is not None:
            items = items[:limit]
        return items

    def save_summary(self, summary: BenchmarkSummary) -> None:
        summary.manifest.save()
        summary.state.save(summary.manifest.experiment_root)
        summary.save(
            results_path(summary.manifest.experiment_root),
            summary_path(summary.manifest.experiment_root),
        )

    def append_result(self, experiment_id: str, result: BenchmarkResult) -> None:
        root = self.experiments_dir / experiment_id
        path = results_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")
        self.refresh_state(experiment_id)

    def refresh_state(self, experiment_id: str) -> ExperimentState | None:
        manifest = self.get(experiment_id)
        if manifest is None:
            return None
        results = self.load_results(experiment_id)
        total_cases = int(manifest.dataset.get("case_count", 0))
        state = ExperimentState(
            status="completed",
            total_cases=total_cases,
            completed_cases=sum(1 for result in results if result.completed),
            failed_cases=sum(1 for result in results if not result.completed),
            updated_at=datetime.now(UTC),
        )
        if len(results) < total_cases:
            state.status = "running"
        state.save(manifest.experiment_root)
        return state

    def delete(self, experiment_id: str, *, force: bool = False) -> bool:
        manifest = self.get(experiment_id)
        if manifest is None:
            return False
        state = self.get_state(experiment_id)
        if not force and state is not None and state.status == "running":
            return False
        import shutil

        shutil.rmtree(manifest.experiment_root, ignore_errors=True)
        return True

    def _iter_manifests(self) -> Iterator[ExperimentManifest]:
        if not self.experiments_dir.exists():
            return
        for entry in self.experiments_dir.iterdir():
            if not entry.is_dir():
                continue
            if not (entry / MANIFEST_FILENAME).exists():
                continue
            try:
                yield ExperimentManifest.load(entry)
            except (json.JSONDecodeError, KeyError, OSError):
                continue

    def _load_state_for_root(self, experiment_root: Path) -> ExperimentState | None:
        path = state_path(experiment_root)
        if not path.exists():
            return None
        try:
            return ExperimentState.load(experiment_root)
        except (json.JSONDecodeError, KeyError, OSError):
            return None


ExperimentService = ExperimentStore
