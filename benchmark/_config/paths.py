from pathlib import Path

# Directory paths
BENCHMARK_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = BENCHMARK_DIR / "artifacts"

DATA_DIR = ARTIFACTS_DIR / "data"
CACHE_DIR = ARTIFACTS_DIR / "cache"
REPOS_DIR = ARTIFACTS_DIR / "repos"
RESULTS_DIR = ARTIFACTS_DIR / "results"
REPORTS_DIR = ARTIFACTS_DIR / "reports"
TRACES_DIR = ARTIFACTS_DIR / "traces"
EVENTS_DIR = ARTIFACTS_DIR / "events"
EXPERIMENTS_DIR = ARTIFACTS_DIR / "experiments"

# Subdirectory structure
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

# Default dataset path
DEFAULT_LOCBENCH_PATH = str(RAW_DATA_DIR / "locbench_v1.jsonl")


def get_benchmark_dir() -> Path:
    return BENCHMARK_DIR


def get_repos_dir() -> Path:
    return REPOS_DIR


def get_results_dir() -> Path:
    return RESULTS_DIR


def get_raw_data_dir() -> Path:
    return RAW_DATA_DIR


def get_processed_data_dir() -> Path:
    return PROCESSED_DATA_DIR


def get_reports_dir() -> Path:
    return REPORTS_DIR


def get_traces_dir() -> Path:
    return TRACES_DIR


def get_events_dir() -> Path:
    return EVENTS_DIR


def get_experiments_dir() -> Path:
    return EXPERIMENTS_DIR
