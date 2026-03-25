import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmark.config.paths import (
    get_curated_data_dir,
    get_data_dir,
    get_experiments_dir,
    get_index_db_path,
    get_raw_data_dir,
)
from relace_mcp.config import RelaceConfig

from .index import ExperimentIndex
from .metadata import build_experiment_manifest, build_initial_state
from .store import ExperimentStore


@dataclass
class MigrationSummary:
    dataset_dirs_moved: int = 0
    experiments_migrated: int = 0
    index_rebuilt: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_dirs_moved": self.dataset_dirs_moved,
            "experiments_migrated": self.experiments_migrated,
            "index_rebuilt": self.index_rebuilt,
        }


def migrate_dataset_dirs() -> int:
    data_dir = get_data_dir()
    moved = 0
    legacy_raw = data_dir / "raw"
    legacy_processed = data_dir / "processed"
    if legacy_raw.exists() and not get_raw_data_dir().exists():
        get_raw_data_dir().parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_raw), str(get_raw_data_dir()))
        moved += 1
    if legacy_processed.exists() and not get_curated_data_dir().exists():
        get_curated_data_dir().parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_processed), str(get_curated_data_dir()))
        moved += 1
    return moved


def migrate_experiment_layout(experiment_root: Path) -> bool:
    if (experiment_root / "manifest.json").exists():
        return False

    report_path = experiment_root / "reports" / "summary.report.json"
    results_path = experiment_root / "results" / "results.jsonl"
    if not report_path.exists() and not results_path.exists():
        return False

    report: dict[str, Any] = {}
    if report_path.exists():
        report = json.loads(report_path.read_text("utf-8"))

    metadata = report.get("metadata", {}) if isinstance(report, dict) else {}
    config = RelaceConfig(api_key="migration", base_dir=None)
    manifest = build_experiment_manifest(
        config=config,
        experiment_id=experiment_root.name,
        kind=(
            (metadata.get("experiment") or {}).get("type") if isinstance(metadata, dict) else None
        )
        or "run",
        experiment_root=experiment_root,
        cases=[],
        run_config=((metadata.get("run") if isinstance(metadata, dict) else {}) or {}),
        created_at=datetime.now(UTC),
        artifacts=(metadata.get("artifacts") if isinstance(metadata, dict) else {}) or {},
    )
    if isinstance(metadata, dict):
        manifest.dataset = (
            metadata.get("dataset", {}) if isinstance(metadata.get("dataset"), dict) else {}
        )
        manifest.search = (
            metadata.get("search", {}) if isinstance(metadata.get("search"), dict) else {}
        )
        manifest.environment = (
            metadata.get("environment", {}) if isinstance(metadata.get("environment"), dict) else {}
        )
    manifest.save()

    if results_path.exists():
        target_results = experiment_root / "results.jsonl"
        if not target_results.exists():
            shutil.copyfile(results_path, target_results)

    state = build_initial_state(int(manifest.dataset.get("case_count", 0) or 0))
    if report:
        total_cases = int(report.get("total_cases", 0) or 0)
        completion_rate = float(report.get("completion_rate", 0.0) or 0.0)
        state.total_cases = total_cases
        state.completed_cases = int(round(total_cases * completion_rate)) if total_cases else 0
        state.failed_cases = max(total_cases - state.completed_cases, 0)
        state.status = "completed"
    else:
        results = (
            (experiment_root / "results.jsonl").read_text("utf-8").strip().splitlines()
            if (experiment_root / "results.jsonl").exists()
            else []
        )
        state.total_cases = len(results)
        state.completed_cases = len(results)
        state.failed_cases = 0
        state.status = "completed"
    state.save(experiment_root)

    target_summary = experiment_root / "summary.json"
    if not target_summary.exists():
        payload = {
            "metadata": metadata,
            "manifest": manifest.to_dict(),
            "state": state.to_dict(),
            "stats": {
                key: value
                for key, value in report.items()
                if key not in {"metadata", "results", "grid"}
            },
            "grid": report.get("grid") if isinstance(report, dict) else None,
        }
        target_summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")

    analysis_dir = experiment_root / "analysis"
    reports_dir = experiment_root / "reports"
    if reports_dir.exists():
        bundle_path = reports_dir / "search-map.bundle.json"
        if bundle_path.exists():
            analysis_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(bundle_path, analysis_dir / bundle_path.name)
    return True


def migrate_all() -> MigrationSummary:
    summary = MigrationSummary()
    summary.dataset_dirs_moved = migrate_dataset_dirs()
    for child in get_experiments_dir().iterdir() if get_experiments_dir().exists() else []:
        if child.is_dir() and migrate_experiment_layout(child):
            summary.experiments_migrated += 1
    index = ExperimentIndex(get_index_db_path())
    index.rebuild(ExperimentStore(get_experiments_dir()))
    index.close()
    summary.index_rebuilt = True
    return summary
