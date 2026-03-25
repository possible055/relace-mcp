import re
from datetime import UTC, datetime
from pathlib import Path

from ..config.paths import get_experiments_dir

TRACES_DIRNAME = "traces"
ANALYSIS_DIRNAME = "analysis"
TRIALS_DIRNAME = "trials"
EVENTS_FILENAME = "events.jsonl"

MANIFEST_FILENAME = "manifest.json"
STATE_FILENAME = "state.json"
RESULTS_FILENAME = "results.jsonl"
SUMMARY_FILENAME = "summary.json"
SEARCH_MAP_BUNDLE_FILENAME = "search-map.bundle.json"

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_DASH_RE = re.compile(r"-+")


def slugify_experiment_segment(value: str) -> str:
    lowered = value.strip().lower()
    ascii_only = lowered.encode("ascii", errors="ignore").decode("ascii")
    normalized = _NON_ALNUM_RE.sub("-", ascii_only)
    collapsed = _DASH_RE.sub("-", normalized).strip("-")
    return collapsed or "unknown"


def format_experiment_timestamp(timestamp: datetime | None = None) -> str:
    ts = timestamp or datetime.now(UTC)
    return ts.strftime("%Y%m%d-%H%M%S")


def format_temperature_segment(value: float) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    if text == "-0":
        text = "0"
    return text.replace(".", "p")


def build_experiment_name(
    experiment_type: str,
    dataset_id: str,
    search_mode: str,
    provider: str,
    *,
    objective: str | None = None,
    timestamp: datetime | None = None,
) -> str:
    parts = [
        slugify_experiment_segment(experiment_type),
        slugify_experiment_segment(dataset_id),
        slugify_experiment_segment(search_mode),
        slugify_experiment_segment(provider),
    ]
    if objective:
        parts.append(slugify_experiment_segment(objective))
    parts.append(format_experiment_timestamp(timestamp))
    return "--".join(parts)


def build_trial_name(max_turns: int, temperature: float) -> str:
    return "--".join(
        [
            "trial",
            slugify_experiment_segment(f"turns-{max_turns}"),
            slugify_experiment_segment(f"temp-{format_temperature_segment(temperature)}"),
        ]
    )


def resolve_experiment_root(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return get_experiments_dir() / candidate


def manifest_path(experiment_root: Path) -> Path:
    return experiment_root / MANIFEST_FILENAME


def state_path(experiment_root: Path) -> Path:
    return experiment_root / STATE_FILENAME


def results_path(experiment_root: Path) -> Path:
    return experiment_root / RESULTS_FILENAME


def summary_path(experiment_root: Path) -> Path:
    return experiment_root / SUMMARY_FILENAME


def traces_dir(experiment_root: Path) -> Path:
    return experiment_root / TRACES_DIRNAME


def events_path(experiment_root: Path) -> Path:
    return traces_dir(experiment_root) / EVENTS_FILENAME


def analysis_dir(experiment_root: Path) -> Path:
    return experiment_root / ANALYSIS_DIRNAME


def search_map_bundle_path(experiment_root: Path) -> Path:
    return analysis_dir(experiment_root) / SEARCH_MAP_BUNDLE_FILENAME


def trials_dir(experiment_root: Path) -> Path:
    return experiment_root / TRIALS_DIRNAME


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
    return max(trace_dirs, key=lambda path: (path.stat().st_mtime_ns, str(path)))


def infer_experiment_root_from_traces(traces_root: Path) -> Path | None:
    if traces_root.name != TRACES_DIRNAME:
        return None
    return traces_root.parent


# Legacy aliases kept only to minimize the refactor surface while callers migrate
experiment_results_path = results_path
experiment_report_path = summary_path
experiment_traces_dir = traces_dir
experiment_events_path = events_path
experiment_reports_dir = analysis_dir
grid_runs_dir = trials_dir
