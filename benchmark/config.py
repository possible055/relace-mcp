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
