from collections.abc import Sequence
from pathlib import Path

from .paths import (
    match_paths,
    normalize_ground_truth_files,
    normalize_path,
    normalize_returned_files,
)
from .ranges import intersection_length, merge_ranges, normalize_line_ranges


def compute_file_recall(
    returned_files: dict[str, list[list[int]]],
    ground_truth: dict[str, list[tuple[int, int]]],
    *,
    repo_root: Path | None = None,
) -> float:
    """Compute what fraction of ground truth files were found.

    Args:
        returned_files: Files returned by fast_search (path -> [[start, end], ...]).
        ground_truth: Ground truth files from dataset annotations (path -> [(start, end), ...]).
        repo_root: Repository root for normalizing absolute paths to relative paths.

    Returns:
        Recall score between 0.0 and 1.0.
    """
    if not ground_truth:
        return 1.0

    normalized_returned = normalize_returned_files(returned_files, repo_root=repo_root)
    normalized_gt = normalize_ground_truth_files(ground_truth, repo_root=repo_root)
    if not normalized_gt:
        return 1.0
    _, matched_gt, _ = match_paths(set(normalized_gt), set(normalized_returned))
    return len(matched_gt) / len(normalized_gt)


def compute_file_precision(
    returned_files: dict[str, list[list[int]]],
    ground_truth: dict[str, list[tuple[int, int]]],
    *,
    repo_root: Path | None = None,
) -> float:
    """Compute what fraction of returned files are in ground truth.

    Args:
        returned_files: Files returned by fast_search.
        ground_truth: Ground truth files from dataset annotations.

    Returns:
        Precision score between 0.0 and 1.0.
    """
    if not returned_files:
        return 0.0

    normalized_returned = normalize_returned_files(returned_files, repo_root=repo_root)
    if not normalized_returned:
        return 0.0
    normalized_gt = normalize_ground_truth_files(ground_truth, repo_root=repo_root)
    _, _, matched_ret = match_paths(set(normalized_gt), set(normalized_returned))
    return len(matched_ret) / len(normalized_returned)


def compute_line_coverage(
    returned_files: dict[str, list[list[int]]],
    ground_truth: dict[str, list[tuple[int, int]]],
    *,
    repo_root: Path | None = None,
) -> float:
    """Compute what fraction of ground truth lines are covered.

    Args:
        returned_files: Files returned by fast_search (path -> [[start, end], ...]).
        ground_truth: Ground truth files from dataset annotations (path -> [(start, end), ...]).

    Returns:
        Coverage score between 0.0 and 1.0.
    """
    if not ground_truth:
        return 0.0

    normalized_returned = normalize_returned_files(returned_files, repo_root=repo_root)
    normalized_gt = normalize_ground_truth_files(ground_truth, repo_root=repo_root)
    gt_to_ret, _, _ = match_paths(set(normalized_gt), set(normalized_returned))

    total_gt_lines = 0
    covered_lines = 0

    for gt_path, gt_ranges in normalized_gt.items():
        merged_gt = merge_ranges(gt_ranges)
        total_gt_lines += sum(end - start + 1 for start, end in merged_gt)

        ret_path = gt_to_ret.get(gt_path)
        if not ret_path:
            continue

        merged_ret = normalize_line_ranges(normalized_returned.get(ret_path, []))
        covered_lines += intersection_length(merged_gt, merged_ret)

    return covered_lines / total_gt_lines if total_gt_lines else 0.0


def compute_line_precision(
    returned_files: dict[str, list[list[int]]],
    ground_truth: dict[str, list[tuple[int, int]]],
    *,
    repo_root: Path | None = None,
) -> float:
    """Compute what fraction of returned lines are in ground truth.

    Line Precision = Σ(Returned_lines ∩ GT_lines) / Σ(Returned_lines)

    Counts all returned lines across all returned files; files not in ground truth
    contribute 0 to the intersection (i.e., they reduce precision).

    Args:
        returned_files: Files returned by fast_search (path -> [[start, end], ...]).
        ground_truth: Ground truth files from dataset annotations (path -> [(start, end), ...]).
        repo_root: Repository root for normalizing absolute paths.

    Returns:
        Precision score between 0.0 and 1.0.
    """
    if not returned_files:
        return 0.0

    normalized_returned = normalize_returned_files(returned_files, repo_root=repo_root)
    normalized_gt = normalize_ground_truth_files(ground_truth, repo_root=repo_root)
    gt_to_ret, _, _ = match_paths(set(normalized_gt), set(normalized_returned))

    # Build reverse mapping: ret_path -> gt_path
    ret_to_gt = {v: k for k, v in gt_to_ret.items()}

    total_returned_lines = 0
    correct_lines = 0

    for ret_path, ret_ranges in normalized_returned.items():
        merged_ret = normalize_line_ranges(ret_ranges)
        total_returned_lines += sum(end - start + 1 for start, end in merged_ret)

        gt_path = ret_to_gt.get(ret_path)
        if not gt_path:
            continue

        merged_gt = merge_ranges(normalized_gt.get(gt_path, []))
        correct_lines += intersection_length(merged_ret, merged_gt)

    return correct_lines / total_returned_lines if total_returned_lines else 0.0


def compute_line_precision_matched(
    returned_files: dict[str, list[list[int]]],
    ground_truth: dict[str, list[tuple[int, int]]],
    *,
    repo_root: Path | None = None,
) -> float:
    """Compute line precision only for matched files (no penalty for unrelated files).

    Line Precision (Matched) = Σ(Correct lines) / Σ(Matched file lines)

    Unlike compute_line_precision, this only counts lines from files that exist
    in both returned and GT, providing a pure measure of range accuracy.

    Args:
        returned_files: Files returned by fast_search (path -> [[start, end], ...]).
        ground_truth: Ground truth files from dataset annotations (path -> [(start, end), ...]).
        repo_root: Repository root for normalizing absolute paths.

    Returns:
        Precision score between 0.0 and 1.0.
    """
    if not returned_files:
        return 0.0

    normalized_returned = normalize_returned_files(returned_files, repo_root=repo_root)
    normalized_gt = normalize_ground_truth_files(ground_truth, repo_root=repo_root)
    gt_to_ret, _, _ = match_paths(set(normalized_gt), set(normalized_returned))

    # Build reverse mapping: ret_path -> gt_path
    ret_to_gt = {v: k for k, v in gt_to_ret.items()}

    total_matched_lines = 0
    correct_lines = 0

    for ret_path, ret_ranges in normalized_returned.items():
        gt_path = ret_to_gt.get(ret_path)
        if not gt_path:
            continue  # Skip unmatched files

        merged_ret = normalize_line_ranges(ret_ranges)
        total_matched_lines += sum(end - start + 1 for start, end in merged_ret)

        merged_gt = merge_ranges(normalized_gt.get(gt_path, []))
        correct_lines += intersection_length(merged_ret, merged_gt)

    return correct_lines / total_matched_lines if total_matched_lines else 0.0


def compute_line_iou_matched(
    returned_files: dict[str, list[list[int]]],
    ground_truth: dict[str, list[tuple[int, int]]],
    *,
    repo_root: Path | None = None,
) -> float:
    """Compute line IoU across matched files only.

    IoU = Σ(Intersection) / Σ(Union), where Union = GT + Returned - Intersection.
    This ignores unmatched files (file precision/recall covers that separately).
    """
    if not returned_files or not ground_truth:
        return 0.0

    normalized_returned = normalize_returned_files(returned_files, repo_root=repo_root)
    normalized_gt = normalize_ground_truth_files(ground_truth, repo_root=repo_root)
    gt_to_ret, _, _ = match_paths(set(normalized_gt), set(normalized_returned))

    intersection = 0
    union = 0

    for gt_path, gt_ranges in normalized_gt.items():
        ret_path = gt_to_ret.get(gt_path)
        if not ret_path:
            continue

        merged_gt = merge_ranges(gt_ranges)
        merged_ret = normalize_line_ranges(normalized_returned.get(ret_path, []))

        gt_len = sum(end - start + 1 for start, end in merged_gt)
        ret_len = sum(end - start + 1 for start, end in merged_ret)
        inter_len = intersection_length(merged_gt, merged_ret)
        intersection += inter_len
        union += gt_len + ret_len - inter_len

    return intersection / union if union else 0.0


def compute_function_hits(
    returned_files: dict[str, list[list[int]]],
    function_targets: Sequence[tuple[str, Sequence[tuple[int, int]]]],
    *,
    repo_root: Path | None = None,
) -> tuple[int, int]:
    """Compute how many target functions have any returned-line overlap.

    Args:
        returned_files: fast_search output (path -> [[start, end], ...]).
        function_targets: Sequence of (path, [(start, end), ...]) per function.
        repo_root: Repository root for normalizing absolute paths.

    Returns:
        (hits, total)
    """
    if not function_targets:
        return (0, 0)

    normalized_returned = normalize_returned_files(returned_files, repo_root=repo_root)
    returned_paths = set(normalized_returned)

    normalized_targets: list[tuple[str, list[tuple[int, int]]]] = []
    for raw_path, raw_ranges in function_targets:
        if not isinstance(raw_path, str) or not raw_path:
            continue
        normalized_path = normalize_path(raw_path, repo_root=repo_root)
        merged_ranges = merge_ranges(raw_ranges)
        if not merged_ranges:
            continue
        normalized_targets.append((normalized_path, merged_ranges))

    if not normalized_targets:
        return (0, 0)

    gt_paths = {p for p, _ in normalized_targets}
    gt_to_ret, _, _ = match_paths(gt_paths, returned_paths)

    hits = 0
    total = 0

    for gt_path, gt_ranges in normalized_targets:
        total += 1
        ret_path = gt_to_ret.get(gt_path)
        if not ret_path:
            continue
        merged_ret = normalize_line_ranges(normalized_returned.get(ret_path, []))
        if intersection_length(gt_ranges, merged_ret) > 0:
            hits += 1

    return (hits, total)
