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


def collect_gitignore_specs(current_dir: Path, base_dir: Path) -> list[tuple[Path, GitIgnoreSpec]]:
    """Collect all .gitignore specs from base_dir down to current_dir."""
    specs: list[tuple[Path, GitIgnoreSpec]] = []
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
        for pattern in reversed(spec.patterns):
            if pattern.match_file(spec_rel):
                last_match = pattern.include
                break
        if last_match is None:
            continue
        ignored = last_match

    return ignored
