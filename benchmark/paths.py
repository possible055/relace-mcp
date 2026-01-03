from pathlib import Path


def get_benchmark_dir() -> Path:
    return Path(__file__).resolve().parent


def get_repos_dir() -> Path:
    return get_benchmark_dir() / "repos"
