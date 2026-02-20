import logging
import subprocess  # nosec B404
from pathlib import Path

logger = logging.getLogger(__name__)


def get_git_head(base_dir: str) -> str | None:
    try:
        result = subprocess.run(  # nosec B603 B607
            ["git", "rev-parse", "HEAD"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode == 0:
            return (result.stdout or "").strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def get_git_root(base_dir: str) -> Path:
    """Return the git repository root directory for a given path.

    This function executes `git rev-parse --show-toplevel` with `base_dir` as
    the working directory. The command and arguments are hardcoded; only the
    working directory changes.

    Args:
        base_dir: Any directory inside (or outside) a git repository.

    Returns:
        The resolved git top-level directory. If git is unavailable or the
        command fails, returns `Path(base_dir).resolve()`.
    """
    base_path = Path(base_dir).resolve()
    try:
        result = subprocess.run(  # nosec B603 B607
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
    """Return `remote.origin.url` for a git repository.

    Args:
        repo_root: The repository root directory.

    Returns:
        The remote origin URL, or an empty string if not set or git fails.
    """
    try:
        result = subprocess.run(  # nosec B603 B607
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
    """Return current git branch name and HEAD SHA for a directory.

    Args:
        base_dir: Any directory inside a git repository.

    Returns:
        A tuple of `(branch, head_sha)`. Returns empty strings if git is not
        available or commands fail.
    """
    branch = ""
    head_sha = ""

    try:
        result = subprocess.run(  # nosec B603 B607
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()

        result = subprocess.run(  # nosec B603 B607
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
    """Return whether the git working tree has uncommitted changes.

    Args:
        base_dir: Any directory inside a git repository.

    Returns:
        True if `git status --porcelain` returns any output; otherwise False.
        Returns False if git is unavailable or the command fails.
    """
    repo_root = get_git_root(base_dir)
    try:
        result = subprocess.run(  # nosec B603 B607
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
