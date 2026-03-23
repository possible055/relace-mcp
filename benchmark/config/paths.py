from pathlib import Path

# Directory paths
BENCHMARK_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BENCHMARK_DIR.parent
DATA_DIR = BENCHMARK_DIR / ".data"

DATASETS_DIR = DATA_DIR / "datasets"
CACHE_DIR = DATA_DIR / "cache"
REPOS_DIR = PROJECT_ROOT / ".bench-repos"
RESULTS_DIR = DATA_DIR / "results"
REPORTS_DIR = DATA_DIR / "reports"
TRACES_DIR = DATA_DIR / "traces"
EVENTS_DIR = DATA_DIR / "events"
EXPERIMENTS_DIR = DATA_DIR / "experiments"

# Subdirectory structure
RAW_DATA_DIR = DATASETS_DIR / "raw"
PROCESSED_DATA_DIR = DATASETS_DIR / "processed"

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
