from benchmark.domain.metrics.engine import (
    FilePrecisionStrategy,
    FileRecallStrategy,
    MetricsEngine,
    MetricStrategy,
    Turn,
)
from benchmark.domain.metrics.layered import (
    AggregateMetrics,
    FileAccessWithMetrics,
    LayeredMetrics,
    ToolContribution,
    TurnMetrics,
)

from .path_metrics import (
    match_paths,
    normalize_ground_truth_files,
    normalize_path,
    normalize_returned_files,
)
from .range_metrics import intersection_length, merge_ranges, normalize_line_ranges


def compute_file_recall(
    returned_files: dict[str, list[list[int]]],
    ground_truth: dict[str, list[tuple[int, int]]],
    *,
    repo_root=None,
) -> float:
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
    repo_root=None,
) -> float:
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
    repo_root=None,
) -> float:
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


def compute_line_precision_matched(
    returned_files: dict[str, list[list[int]]],
    ground_truth: dict[str, list[tuple[int, int]]],
    *,
    repo_root=None,
) -> float:
    if not returned_files:
        return 0.0

    normalized_returned = normalize_returned_files(returned_files, repo_root=repo_root)
    normalized_gt = normalize_ground_truth_files(ground_truth, repo_root=repo_root)
    gt_to_ret, _, _ = match_paths(set(normalized_gt), set(normalized_returned))
    ret_to_gt = {value: key for key, value in gt_to_ret.items()}

    total_matched_lines = 0
    correct_lines = 0

    for ret_path, ret_ranges in normalized_returned.items():
        gt_path = ret_to_gt.get(ret_path)
        if not gt_path:
            continue

        merged_ret = normalize_line_ranges(ret_ranges)
        total_matched_lines += sum(end - start + 1 for start, end in merged_ret)

        merged_gt = merge_ranges(normalized_gt.get(gt_path, []))
        correct_lines += intersection_length(merged_ret, merged_gt)

    return correct_lines / total_matched_lines if total_matched_lines else 0.0


def compute_function_hits(
    returned_files: dict[str, list[list[int]]],
    function_targets,
    *,
    repo_root=None,
) -> tuple[int, int]:
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

    gt_paths = {path for path, _ in normalized_targets}
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


__all__ = [
    "AggregateMetrics",
    "FileAccessWithMetrics",
    "FilePrecisionStrategy",
    "FileRecallStrategy",
    "LayeredMetrics",
    "MetricStrategy",
    "MetricsEngine",
    "ToolContribution",
    "Turn",
    "TurnMetrics",
    "compute_file_precision",
    "compute_file_recall",
    "compute_function_hits",
    "compute_line_coverage",
    "compute_line_precision_matched",
    "normalize_returned_files",
]
