from pathlib import Path

from .config import get_experiments_dir

RESULTS_DIRNAME = "results"
REPORTS_DIRNAME = "reports"
TRACES_DIRNAME = "traces"
EVENTS_DIRNAME = "events"
RUNS_DIRNAME = "runs"

RESULTS_FILENAME = "results.jsonl"
REPORT_FILENAME = "summary.report.json"
GRID_REPORT_FILENAME = "grid.report.json"
EVENTS_FILENAME = "events.jsonl"


def resolve_experiment_root(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return get_experiments_dir() / candidate


def experiment_results_dir(experiment_root: Path) -> Path:
    return experiment_root / RESULTS_DIRNAME


def experiment_reports_dir(experiment_root: Path) -> Path:
    return experiment_root / REPORTS_DIRNAME


def experiment_traces_dir(experiment_root: Path) -> Path:
    return experiment_root / TRACES_DIRNAME


def experiment_events_dir(experiment_root: Path) -> Path:
    return experiment_root / EVENTS_DIRNAME


def experiment_results_path(experiment_root: Path) -> Path:
    return experiment_results_dir(experiment_root) / RESULTS_FILENAME


def experiment_report_path(experiment_root: Path) -> Path:
    return experiment_reports_dir(experiment_root) / REPORT_FILENAME


def experiment_grid_report_path(experiment_root: Path) -> Path:
    return experiment_reports_dir(experiment_root) / GRID_REPORT_FILENAME


def experiment_events_path(experiment_root: Path) -> Path:
    return experiment_events_dir(experiment_root) / EVENTS_FILENAME


def grid_runs_dir(experiment_root: Path) -> Path:
    return experiment_root / RUNS_DIRNAME


def collect_trace_dirs(experiments_dir: Path | None = None) -> list[Path]:
    root = experiments_dir or get_experiments_dir()
    if not root.exists():
        return []
    return sorted(
        [path for path in root.rglob(TRACES_DIRNAME) if path.is_dir()],
        key=lambda path: str(path),
    )


def find_latest_traces_dir(experiments_dir: Path | None = None) -> Path | None:
    trace_dirs = collect_trace_dirs(experiments_dir)
    if not trace_dirs:
        return None
    return max(trace_dirs, key=lambda path: str(path))


def infer_experiment_root_from_traces(traces_dir: Path) -> Path | None:
    if traces_dir.name != TRACES_DIRNAME:
        return None
    return traces_dir.parent
