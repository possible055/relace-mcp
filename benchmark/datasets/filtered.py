"""Loader for processed/filtered datasets.

This module re-exports the unified loader for backwards compatibility.
The FilteredCase class is deprecated in favor of DatasetCase.
"""

from ..config import DEFAULT_FILTERED_PATH
from ..schemas import DatasetCase
from .mulocbench import load_dataset


def load_filtered_dataset(
    dataset_path: str = DEFAULT_FILTERED_PATH,
    *,
    limit: int | None = None,
    min_confidence: float = 0.0,
) -> list[DatasetCase]:
    """Load filtered dataset.

    This is an alias for load_dataset with appropriate defaults.

    Args:
        dataset_path: Path to filtered.jsonl (relative to benchmark/ if not absolute).
        limit: Maximum cases to load.
        min_confidence: Minimum solvability confidence to include.

    Returns:
        List of DatasetCase objects.
    """
    return load_dataset(
        dataset_path=dataset_path,
        limit=limit,
        shuffle=False,
        min_confidence=min_confidence,
    )


# Backwards compatibility: FilteredCase is now DatasetCase
FilteredCase = DatasetCase
