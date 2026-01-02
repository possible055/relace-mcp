from pathlib import Path


def compute_file_recall(
    returned_files: dict[str, list[list[int]]],
    ground_truth: dict[str, list[tuple[int, int]]],
) -> float:
    """Compute what fraction of ground truth files were found.

    Uses basename matching to handle absolute vs relative path differences.

    Args:
        returned_files: Files returned by fast_search (path -> [[start, end], ...]).
        ground_truth: Ground truth files from patch (path -> [(start, end), ...]).

    Returns:
        Recall score between 0.0 and 1.0.
    """
    if not ground_truth:
        return 1.0

    gt_basenames = {Path(f).name for f in ground_truth}
    returned_basenames = {Path(f).name for f in returned_files}

    matched = gt_basenames & returned_basenames
    return len(matched) / len(gt_basenames)


def compute_file_precision(
    returned_files: dict[str, list[list[int]]],
    ground_truth: dict[str, list[tuple[int, int]]],
) -> float:
    """Compute what fraction of returned files are in ground truth.

    Args:
        returned_files: Files returned by fast_search.
        ground_truth: Ground truth files from patch.

    Returns:
        Precision score between 0.0 and 1.0.
    """
    if not returned_files:
        return 0.0

    gt_basenames = {Path(f).name for f in ground_truth}
    returned_basenames = {Path(f).name for f in returned_files}

    matched = gt_basenames & returned_basenames
    return len(matched) / len(returned_basenames)


def compute_line_coverage(
    returned_files: dict[str, list[list[int]]],
    ground_truth: dict[str, list[tuple[int, int]]],
) -> float:
    """Compute what fraction of ground truth lines are covered.

    Args:
        returned_files: Files returned by fast_search (path -> [[start, end], ...]).
        ground_truth: Ground truth files from patch (path -> [(start, end), ...]).

    Returns:
        Coverage score between 0.0 and 1.0.
    """
    if not ground_truth:
        return 1.0

    total_gt_lines = 0
    covered_lines = 0

    for gt_path, gt_ranges in ground_truth.items():
        gt_basename = Path(gt_path).name

        # Find matching returned file by basename
        matched_ranges: list[list[int]] = []
        for ret_path, ret_ranges in returned_files.items():
            if Path(ret_path).name == gt_basename:
                matched_ranges = ret_ranges
                break

        for start, end in gt_ranges:
            gt_line_set = set(range(start, end + 1))
            total_gt_lines += len(gt_line_set)

            for r in matched_ranges:
                if isinstance(r, list) and len(r) == 2:
                    ret_line_set = set(range(r[0], r[1] + 1))
                    covered_lines += len(gt_line_set & ret_line_set)

    return covered_lines / total_gt_lines if total_gt_lines else 1.0
