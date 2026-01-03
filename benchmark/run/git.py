import subprocess  # nosec B404
from pathlib import Path


def _run_git(repo_path: Path | None, args: list[str]) -> None:
    cmd = ["git"]
    if repo_path is not None:
        cmd.extend(["-C", str(repo_path)])
    cmd.extend(args)
    completed = subprocess.run(  # nosec B603 B607
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 0:
        return
    stderr = (completed.stderr or completed.stdout or "").strip()
    details = f": {stderr}" if stderr else ""
    raise RuntimeError(f"git {' '.join(args)} failed (code {completed.returncode}){details}")


def git_has_commit(repo_path: Path, commit: str) -> bool:
    completed = subprocess.run(  # nosec B603 B607
        ["git", "-C", str(repo_path), "cat-file", "-e", f"{commit}^{{commit}}"],
        check=False,
        capture_output=True,
    )
    return completed.returncode == 0


def ensure_repo(
    *,
    repos_dir: Path,
    repo: str,
    base_commit: str,
    verbose: bool,
) -> Path:
    repo_name = repo.replace("/", "__")
    repo_path = repos_dir / repo_name

    if not repo_path.exists():
        if verbose:
            print(f"  Cloning {repo}...", flush=True)
        _run_git(None, ["clone", "--depth", "1", f"https://github.com/{repo}.git", str(repo_path)])

    if not git_has_commit(repo_path, base_commit):
        _run_git(repo_path, ["fetch", "--depth", "1", "origin", base_commit])

    _run_git(repo_path, ["checkout", base_commit])
    return repo_path
