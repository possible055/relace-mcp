from pathlib import Path

# Directory paths
BENCHMARK_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = BENCHMARK_DIR / "artifacts"

DATA_DIR = ARTIFACTS_DIR / "data"
CACHE_DIR = ARTIFACTS_DIR / "cache"
REPOS_DIR = ARTIFACTS_DIR / "repos"
RESULTS_DIR = ARTIFACTS_DIR / "results"
REPORTS_DIR = ARTIFACTS_DIR / "reports"

# Subdirectory structure
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

# Default dataset paths
# Use absolute paths based on the config to ensure they follow the directory structure
DEFAULT_MULOCBENCH_PATH = str(RAW_DATA_DIR / "mulocbench_v1.jsonl")
DEFAULT_FILTERED_PATH = str(PROCESSED_DATA_DIR / "filtered.jsonl")

# Large repos (>=100MB) excluded by default to avoid slow cloning
EXCLUDED_REPOS: frozenset[str] = frozenset(
    {
        # >1GB
        "langflow-ai/langflow",  # 1.2G
        # >500MB
        "PaddlePaddle/PaddleOCR",  # 645M
        "odoo/odoo",  # 603M
        # >300MB
        "ansible/ansible",  # 437M
        "pytorch/pytorch",  # 383M
        "deepfakes/faceswap",  # 374M
        "huggingface/transformers",  # 339M
        "python/cpython",  # 329M
        "All-Hands-AI/OpenHands",  # 310M
        # >100MB
        "hacksider/Deep-Live-Cam",  # 153M
        "yt-dlp/yt-dlp",  # 129M
        "pandas-dev/pandas",  # 114M
        # Previously excluded (not in current dataset)
        "home-assistant/core",
        "kubernetes/kubernetes",
        "torvalds/linux",
        "chromium/chromium",
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


def get_raw_data_dir() -> Path:
    return RAW_DATA_DIR


def get_processed_data_dir() -> Path:
    return PROCESSED_DATA_DIR


def get_reports_dir() -> Path:
    return REPORTS_DIR
