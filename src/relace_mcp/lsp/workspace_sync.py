import fnmatch
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class WorkspaceSyncState:
    snapshot: dict[str, tuple[int, int]]
    snapshot_initialized: bool
    last_sync: float


@dataclass
class WorkspaceSyncOutcome:
    state: WorkspaceSyncState
    restart_reason: str | None
    changes: list[dict[str, Any]]


def extract_analysis_patterns(
    workspace_settings: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    basedpyright = workspace_settings.get("basedpyright")
    if not isinstance(basedpyright, dict):
        return ([], [], [])

    analysis = basedpyright.get("analysis")
    if not isinstance(analysis, dict):
        return ([], [], [])

    include = analysis.get("include")
    exclude = analysis.get("exclude")
    ignore = analysis.get("ignore")

    include_patterns = include if isinstance(include, list) else []
    exclude_patterns = exclude if isinstance(exclude, list) else []
    ignore_patterns = ignore if isinstance(ignore, list) else []
    return (
        [p for p in include_patterns if isinstance(p, str)],
        [p for p in exclude_patterns if isinstance(p, str)],
        [p for p in ignore_patterns if isinstance(p, str)],
    )


def _normalize_glob_pattern(raw: str) -> str:
    pattern = raw.strip().replace("\\", "/")
    while pattern.startswith("./"):
        pattern = pattern[2:]
    pattern = pattern.lstrip("/")
    return pattern


def _expand_glob_patterns(raw_patterns: list[str]) -> list[str]:
    patterns: list[str] = []
    seen: set[str] = set()
    for raw in raw_patterns:
        base = _normalize_glob_pattern(raw)
        if not base:
            continue

        candidate = base
        while True:
            if candidate and candidate not in seen:
                seen.add(candidate)
                patterns.append(candidate)

            if "/**/" in candidate:
                candidate = candidate.replace("/**/", "/", 1)
                continue

            if candidate.endswith("/**"):
                candidate = candidate[:-3]
                continue

            break
    return patterns


def _iter_parent_paths(rel_path: str) -> list[str]:
    parents: list[str] = []
    parts = rel_path.split("/")
    for i in range(len(parts) - 1, 0, -1):
        parents.append("/".join(parts[:i]))
    return parents


def _matches_any_pattern(rel_path: str, patterns: list[str]) -> bool:
    if not patterns:
        return False

    if any(fnmatch.fnmatchcase(rel_path, pattern) for pattern in patterns):
        return True

    parents = _iter_parent_paths(rel_path)
    for parent in parents:
        if any(fnmatch.fnmatchcase(parent, pattern) for pattern in patterns):
            return True

    return False


def _extract_glob_prefix(raw: str) -> str:
    pattern = _normalize_glob_pattern(raw)
    if not pattern:
        return ""

    parts = [p for p in pattern.split("/") if p and p != "."]
    prefix_parts: list[str] = []
    for part in parts:
        if any(ch in part for ch in ("*", "?", "[")):
            break
        prefix_parts.append(part)

    return "/".join(prefix_parts)


def sync_workspace_changes(
    *,
    workspace: str,
    workspace_settings: dict[str, Any],
    config_files: tuple[str, ...],
    file_extensions: tuple[str, ...],
    ignored_dir_names: frozenset[str],
    state: WorkspaceSyncState,
    min_interval_seconds: float,
    budget_seconds: float,
    max_files: int,
    max_events: int,
) -> WorkspaceSyncOutcome | None:
    now = time.monotonic()
    if now - state.last_sync < min_interval_seconds:
        return None
    last_sync = now

    workspace_root = Path(workspace)
    include_raw, exclude_raw, _ = extract_analysis_patterns(workspace_settings)
    include_patterns = _expand_glob_patterns(include_raw)
    exclude_patterns = _expand_glob_patterns(exclude_raw)
    config_files_set = frozenset(config_files)

    scan_roots: list[Path] = []
    if include_raw:
        root_candidates: set[Path] = set()
        for raw in include_raw:
            prefix = _extract_glob_prefix(raw)
            if not prefix:
                continue
            candidate = workspace_root / prefix
            if candidate.is_dir():
                root_candidates.add(candidate)
            elif candidate.is_file() and candidate.parent.is_dir():
                root_candidates.add(candidate.parent)
        scan_roots = sorted(root_candidates) if root_candidates else [workspace_root]
    else:
        scan_roots = [workspace_root]

    start = time.monotonic()
    scanned_files = 0
    truncated = False

    def should_consider(rel_path: str) -> bool:
        if include_patterns and not _matches_any_pattern(rel_path, include_patterns):
            return False
        if _matches_any_pattern(rel_path, exclude_patterns):
            return False
        return True

    def should_skip_dir(rel_dir: str, dir_name: str) -> bool:
        if rel_dir not in ("", ".") and dir_name in ignored_dir_names:
            return True
        if _matches_any_pattern(rel_dir, exclude_patterns):
            return True
        return False

    current_snapshot: dict[str, tuple[int, int]] = {}

    def record_path(path: Path) -> None:
        nonlocal scanned_files, truncated
        if path.is_symlink():
            return
        try:
            rel_path = path.relative_to(workspace_root).as_posix()
        except ValueError:
            return
        try:
            st = path.stat()
        except OSError:
            return
        if rel_path not in config_files_set and not should_consider(rel_path):
            return
        current_snapshot[rel_path] = (st.st_mtime_ns, st.st_size)
        scanned_files += 1
        if scanned_files >= max_files:
            truncated = True

    for cfg in config_files:
        record_path(workspace_root / cfg)

    pending_dirs: list[Path] = list(reversed(scan_roots))
    while pending_dirs and not truncated:
        if time.monotonic() - start > budget_seconds:
            truncated = True
            break

        current_dir = pending_dirs.pop()
        try:
            rel_dir = current_dir.relative_to(workspace_root).as_posix()
        except ValueError:
            continue

        if rel_dir and should_skip_dir(rel_dir, current_dir.name):
            continue

        try:
            with os.scandir(current_dir) as it:
                for entry in it:
                    if time.monotonic() - start > budget_seconds:
                        truncated = True
                        break
                    if scanned_files >= max_files:
                        truncated = True
                        break
                    if entry.is_symlink():
                        continue

                    try:
                        if entry.is_dir(follow_symlinks=False):
                            child_dir = Path(entry.path)
                            try:
                                child_rel = child_dir.relative_to(workspace_root).as_posix()
                            except ValueError:
                                continue
                            if should_skip_dir(child_rel, entry.name):
                                continue
                            pending_dirs.append(child_dir)
                            continue

                        if not entry.is_file(follow_symlinks=False):
                            continue
                    except OSError:
                        continue

                    if not entry.name.endswith(file_extensions):
                        continue

                    record_path(Path(entry.path))
        except OSError:
            continue

    if not state.snapshot_initialized:
        return WorkspaceSyncOutcome(
            state=WorkspaceSyncState(
                snapshot=current_snapshot,
                snapshot_initialized=True,
                last_sync=last_sync,
            ),
            restart_reason=None,
            changes=[],
        )

    previous_snapshot = state.snapshot
    changes: list[tuple[int, str]] = []
    config_changed = False

    for rel_path, meta in current_snapshot.items():
        prev = previous_snapshot.get(rel_path)
        if prev is None:
            changes.append((1, rel_path))
        elif prev != meta:
            changes.append((2, rel_path))
        if rel_path in config_files_set:
            config_changed = config_changed or prev != meta

    if truncated:
        for cfg in config_files:
            if cfg in previous_snapshot and cfg not in current_snapshot:
                changes.append((3, cfg))
                config_changed = True

    if not truncated:
        for rel_path in previous_snapshot:
            if rel_path not in current_snapshot:
                changes.append((3, rel_path))
                if rel_path in config_files_set:
                    config_changed = True
        next_snapshot = current_snapshot
    else:
        next_snapshot = dict(previous_snapshot)
        next_snapshot.update(current_snapshot)

    next_state = WorkspaceSyncState(
        snapshot=next_snapshot,
        snapshot_initialized=True,
        last_sync=last_sync,
    )

    if config_changed:
        return WorkspaceSyncOutcome(
            state=next_state,
            restart_reason="Workspace configuration changed",
            changes=[],
        )

    if not changes:
        return WorkspaceSyncOutcome(
            state=next_state,
            restart_reason=None,
            changes=[],
        )

    if len(changes) > max_events:
        return WorkspaceSyncOutcome(
            state=next_state,
            restart_reason=f"Too many file changes ({len(changes)})",
            changes=[],
        )

    payload: list[dict[str, Any]] = []
    for change_type, rel_path in changes:
        abs_path = (workspace_root / rel_path).absolute()
        payload.append({"uri": abs_path.as_uri(), "type": change_type})

    return WorkspaceSyncOutcome(
        state=next_state,
        restart_reason=None,
        changes=payload,
    )


__all__ = [
    "WorkspaceSyncOutcome",
    "WorkspaceSyncState",
    "extract_analysis_patterns",
    "sync_workspace_changes",
]
