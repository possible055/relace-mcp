import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def get_git_root(base_dir: str) -> Path:
    base_path = Path(base_dir).resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            top = result.stdout.strip()
            if top:
                return Path(top).resolve()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        logger.debug("Failed to get git root")
    return base_path


def get_git_remote_origin_url(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            if url:
                return url
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        logger.debug("Failed to get git remote origin url")
    return ""


def get_current_git_info(base_dir: str) -> tuple[str, str]:
    branch = ""
    head_sha = ""

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            head_sha = result.stdout.strip()

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        logger.debug("Failed to get git info")

    return branch, head_sha


def is_git_dirty(base_dir: str) -> bool:
    repo_root = get_git_root(base_dir)
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        logger.debug("Failed to get git dirty status")
    return False
