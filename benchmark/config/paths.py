from pathlib import Path

BENCHMARK_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BENCHMARK_DIR.parent
DATA_DIR = BENCHMARK_DIR / ".data"

DATASETS_DIR = DATA_DIR / "datasets"
RAW_DATA_DIR = DATASETS_DIR / "raw"
CURATED_DATA_DIR = DATASETS_DIR / "curated"
EXPERIMENTS_DIR = DATA_DIR / "experiments"
INDEX_DB_PATH = DATA_DIR / "index.sqlite3"

REPOS_DIR = PROJECT_ROOT / ".bench-repos"

DEFAULT_LOCBENCH_PATH = str(RAW_DATA_DIR / "locbench_v1.jsonl")


def get_benchmark_dir() -> Path:
    return BENCHMARK_DIR


def get_data_dir() -> Path:
    return DATA_DIR


def get_repos_dir() -> Path:
    return REPOS_DIR


def get_datasets_dir() -> Path:
    return DATASETS_DIR


def get_raw_data_dir() -> Path:
    return RAW_DATA_DIR


def get_curated_data_dir() -> Path:
    return CURATED_DATA_DIR


def get_processed_data_dir() -> Path:
    return CURATED_DATA_DIR


def get_experiments_dir() -> Path:
    return EXPERIMENTS_DIR


def get_index_db_path() -> Path:
    return INDEX_DB_PATH
