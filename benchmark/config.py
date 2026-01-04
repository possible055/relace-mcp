from pathlib import Path

# Directory paths
BENCHMARK_DIR = Path(__file__).resolve().parent
DATA_DIR = BENCHMARK_DIR / "data"
CACHE_DIR = BENCHMARK_DIR / "cache"
REPOS_DIR = BENCHMARK_DIR / "repos"
RESULTS_DIR = BENCHMARK_DIR / "results"

# Default dataset paths
DEFAULT_MULOCBENCH_PATH = "data/mulocbench.jsonl"
DEFAULT_FILTERED_PATH = "data/filtered.jsonl"

# Large repos that are excluded by default to avoid slow cloning
EXCLUDED_REPOS: frozenset[str] = frozenset(
    {
        "home-assistant/core",
        "kubernetes/kubernetes",
        "torvalds/linux",
        "chromium/chromium",
        "python/cpython",
        "pytorch/pytorch",
        "pandas-dev/pandas",
        "odoo/odoo",
        "huggingface/transformers",
    }
)


def get_benchmark_dir() -> Path:
    return BENCHMARK_DIR


def get_repos_dir() -> Path:
    return REPOS_DIR


def get_data_dir() -> Path:
    return DATA_DIR


def get_cache_dir() -> Path:
    return CACHE_DIR


def get_results_dir() -> Path:
    return RESULTS_DIR
