from collections.abc import Mapping
from pathlib import Path


def normalize_path(path: str, *, repo_root: Path | None) -> str:
    stripped = path.strip()
    if stripped.startswith("./"):
        stripped = stripped[2:]
    if stripped.startswith(("a/", "b/")):
        stripped = stripped[2:]

    as_path = Path(stripped)
    if as_path.is_absolute() and repo_root is not None:
        try:
            as_path = as_path.relative_to(repo_root)
        except ValueError:
            return as_path.as_posix()
    return as_path.as_posix()


def normalize_returned_files(
    returned_files: Mapping[str, object], *, repo_root: Path | None
) -> dict[str, list[list[int]]]:
    normalized: dict[str, list[list[int]]] = {}
    for raw_path, raw_ranges in returned_files.items():
        if not isinstance(raw_path, str):
            continue
        normalized_path = normalize_path(raw_path, repo_root=repo_root)
        if not isinstance(raw_ranges, list):
            continue
        ranges: list[list[int]] = []
        for value in raw_ranges:
            if (
                isinstance(value, list)
                and len(value) == 2
                and isinstance(value[0], int)
                and isinstance(value[1], int)
                and value[0] > 0
                and value[1] >= value[0]
            ):
                ranges.append([value[0], value[1]])
        normalized.setdefault(normalized_path, []).extend(ranges)
    return normalized


def normalize_ground_truth_files(
    ground_truth: Mapping[str, object], *, repo_root: Path | None
) -> dict[str, list[tuple[int, int]]]:
    normalized: dict[str, list[tuple[int, int]]] = {}
    for raw_path, raw_ranges in ground_truth.items():
        if not isinstance(raw_path, str):
            continue
        normalized_path = normalize_path(raw_path, repo_root=repo_root)
        if not isinstance(raw_ranges, list):
            continue
        ranges: list[tuple[int, int]] = []
        for value in raw_ranges:
            if (
                isinstance(value, tuple)
                and len(value) == 2
                and isinstance(value[0], int)
                and isinstance(value[1], int)
                and value[0] > 0
                and value[1] >= value[0]
            ):
                ranges.append((value[0], value[1]))
        normalized.setdefault(normalized_path, []).extend(ranges)
    return normalized


def match_paths(
    ground_truth_paths: set[str], returned_paths: set[str]
) -> tuple[dict[str, str], set[str], set[str]]:
    exact = ground_truth_paths & returned_paths
    gt_to_ret: dict[str, str] = {path: path for path in exact}
    matched_gt = set(gt_to_ret.keys())
    matched_ret = set(gt_to_ret.values())
    return gt_to_ret, matched_gt, matched_ret
