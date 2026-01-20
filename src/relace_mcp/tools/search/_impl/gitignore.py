import os
import subprocess
from functools import lru_cache
from pathlib import Path

from pathspec import GitIgnoreSpec


@lru_cache(maxsize=256)
def load_gitignore_spec(gitignore_path: str) -> GitIgnoreSpec | None:
    """Load and cache a .gitignore file as a GitIgnoreSpec."""
    path = Path(gitignore_path)
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return GitIgnoreSpec.from_lines(lines)
    except Exception:
        return None


@lru_cache(maxsize=1)
def get_global_excludes_path() -> Path | None:
    """Get global excludes file path from git config or default location.

    Priority:
    1. git config --global core.excludesFile
    2. $XDG_CONFIG_HOME/git/ignore (default: ~/.config/git/ignore)
    3. ~/.gitignore (legacy fallback)
    """
    # Try git config first
    try:
        result = subprocess.run(
            ["git", "config", "--global", "core.excludesFile"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0 and result.stdout.strip():
            path = Path(result.stdout.strip()).expanduser()
            if path.is_file():
                return path
    except (subprocess.SubprocessError, OSError):
        pass

    # XDG default
    xdg_config = os.environ.get("XDG_CONFIG_HOME", "")
    if xdg_config:
        xdg_path = Path(xdg_config) / "git" / "ignore"
    else:
        xdg_path = Path.home() / ".config" / "git" / "ignore"
    if xdg_path.is_file():
        return xdg_path

    # Legacy fallback
    legacy_path = Path.home() / ".gitignore"
    if legacy_path.is_file():
        return legacy_path

    return None


def load_repo_exclude_spec(base_dir: Path) -> GitIgnoreSpec | None:
    """Load .git/info/exclude if exists."""
    exclude_path = base_dir / ".git" / "info" / "exclude"
    return load_gitignore_spec(str(exclude_path))


def collect_gitignore_specs(current_dir: Path, base_dir: Path) -> list[tuple[Path, GitIgnoreSpec]]:
    """Collect all exclude specs in git priority order.

    Priority (low to high, later overrides earlier):
    1. Global excludes (core.excludesFile)
    2. Repository excludes (.git/info/exclude)
    3. Project .gitignore files (from base_dir down to current_dir)
    """
    specs: list[tuple[Path, GitIgnoreSpec]] = []

    # 1. Global excludes (lowest priority, applies to entire repo)
    global_path = get_global_excludes_path()
    if global_path:
        global_spec = load_gitignore_spec(str(global_path))
        if global_spec:
            specs.append((base_dir, global_spec))

    # 2. .git/info/exclude (repo-level, applies to entire repo)
    repo_exclude = load_repo_exclude_spec(base_dir)
    if repo_exclude:
        specs.append((base_dir, repo_exclude))

    # 3. Project .gitignore files (highest priority, directory-scoped)
    try:
        rel_parts = current_dir.relative_to(base_dir).parts
    except ValueError:
        return specs

    check_dir = base_dir
    gitignore = check_dir / ".gitignore"
    spec = load_gitignore_spec(str(gitignore))
    if spec:
        specs.append((check_dir, spec))

    for part in rel_parts:
        check_dir = check_dir / part
        gitignore = check_dir / ".gitignore"
        spec = load_gitignore_spec(str(gitignore))
        if spec:
            specs.append((check_dir, spec))

    return specs


def is_ignored(
    rel_path: str,
    is_dir: bool,
    specs: list[tuple[Path, GitIgnoreSpec]],
    base_dir: Path,
) -> bool:
    """Check if a path is ignored by gitignore rules.

    Args:
        rel_path: Path relative to base_dir.
        is_dir: Whether the path is a directory.
        specs: List of (spec_dir, spec) from base_dir to current_dir.
        base_dir: Repository base directory.

    Returns:
        True if ignored by the effective rules, otherwise False.
    """
    if not specs:
        return False

    full_path = base_dir / rel_path

    ignored = False
    for spec_dir, spec in specs:
        try:
            spec_rel = full_path.relative_to(spec_dir).as_posix()
            if is_dir:
                spec_rel += "/"
        except ValueError:
            continue

        # Git semantics: "last match wins" within each .gitignore file, and
        # deeper .gitignore files override parent rules. `GitIgnoreSpec.match_file`
        # only returns the final decision (ignored or not), so we need to
        # distinguish between "no match" and an explicit `!` unignore match.
        last_match: bool | None = None
        for pattern in reversed(list(spec.patterns)):
            if pattern.match_file(spec_rel):
                last_match = pattern.include
                break
        if last_match is None:
            continue
        ignored = last_match

    return ignored
