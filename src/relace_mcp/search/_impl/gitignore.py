import os
import subprocess  # nosec B404 - safe use with fixed args, no user input
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pathspec import GitIgnoreSpec
from pathspec.pattern import Pattern


@dataclass(frozen=True)
class CompiledGitIgnoreSpec:
    """Compiled .gitignore patterns for fast "last match wins" lookup."""

    patterns_reversed: tuple[Pattern, ...]


GitIgnoreSpecEntry = tuple[str, CompiledGitIgnoreSpec]
GitIgnoreSpecs = tuple[GitIgnoreSpecEntry, ...]


@lru_cache(maxsize=256)
def load_gitignore_spec(gitignore_path: str) -> CompiledGitIgnoreSpec | None:
    """Load and cache a .gitignore file with precompiled pattern order."""
    path = Path(gitignore_path)
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        spec = GitIgnoreSpec.from_lines(lines)
        return CompiledGitIgnoreSpec(patterns_reversed=tuple(reversed(list(spec.patterns))))
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
        result = subprocess.run(  # nosec B603 B607 - fixed command, no user input
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


def load_repo_exclude_spec(base_dir: Path) -> CompiledGitIgnoreSpec | None:
    """Load .git/info/exclude if exists."""
    exclude_path = base_dir / ".git" / "info" / "exclude"
    return load_gitignore_spec(str(exclude_path))


def _append_project_gitignore(
    specs: GitIgnoreSpecs, check_dir: Path, base_dir: Path
) -> GitIgnoreSpecs:
    spec = load_gitignore_spec(str(check_dir / ".gitignore"))
    if not spec:
        return specs

    spec_dir_rel = "" if check_dir == base_dir else check_dir.relative_to(base_dir).as_posix()
    return specs + ((spec_dir_rel, spec),)


def _collect_repo_level_specs(base_dir: Path) -> GitIgnoreSpecs:
    specs: GitIgnoreSpecs = ()
    global_path = get_global_excludes_path()
    if global_path:
        global_spec = load_gitignore_spec(str(global_path))
        if global_spec:
            specs += (("", global_spec),)

    repo_exclude = load_repo_exclude_spec(base_dir)
    if repo_exclude:
        specs += (("", repo_exclude),)

    return specs


@lru_cache(maxsize=4096)
def collect_gitignore_specs(current_dir: Path, base_dir: Path) -> GitIgnoreSpecs:
    """Collect all exclude specs in git priority order.

    Priority (low to high, later overrides earlier):
    1. Global excludes (core.excludesFile)
    2. Repository excludes (.git/info/exclude)
    3. Project .gitignore files (from base_dir down to current_dir)
    """
    if current_dir == base_dir:
        specs = _collect_repo_level_specs(base_dir)
        return _append_project_gitignore(specs, base_dir, base_dir)

    try:
        current_dir.relative_to(base_dir)
    except ValueError:
        return _collect_repo_level_specs(base_dir)

    parent_specs = collect_gitignore_specs(current_dir.parent, base_dir)
    return _append_project_gitignore(parent_specs, current_dir, base_dir)


def is_ignored(
    rel_path: str,
    is_dir: bool,
    specs: GitIgnoreSpecs,
) -> bool:
    """Check if a path is ignored by gitignore rules.

    Args:
        rel_path: Path relative to base_dir.
        is_dir: Whether the path is a directory.
        specs: Ordered gitignore specs (global -> repo -> nested directories).

    Returns:
        True if ignored by the effective rules, otherwise False.
    """
    if not specs:
        return False

    rel_posix = rel_path.strip("/")
    if not rel_posix:
        return False

    ignored = False
    for spec_dir_rel, spec in specs:
        if spec_dir_rel:
            prefix = f"{spec_dir_rel}/"
            if rel_posix == spec_dir_rel:
                spec_rel = "."
            elif rel_posix.startswith(prefix):
                spec_rel = rel_posix[len(prefix) :]
            else:
                continue
        else:
            spec_rel = rel_posix

        if is_dir:
            spec_rel += "/"

        # Git semantics: "last match wins" within each .gitignore file, and
        # deeper .gitignore files override parent rules. `GitIgnoreSpec.match_file`
        # only returns the final decision (ignored or not), so we need to
        # distinguish between "no match" and an explicit `!` unignore match.
        last_match: bool | None = None
        for pattern in spec.patterns_reversed:
            if pattern.match_file(spec_rel):
                last_match = pattern.include
                break
        if last_match is None:
            continue
        ignored = last_match

    return ignored
