import sys
from pathlib import Path

# Add project root to path for benchmark imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from benchmark.cli.build_locbench import _build_target_ranges, _cluster_lines_to_ranges
from benchmark.schemas import DatasetCase, GroundTruthEntry


class TestClusterLinesToRanges:
    def test_merges_within_gap(self) -> None:
        assert _cluster_lines_to_ranges([10, 14], gap=3) == [(10, 14)]

    def test_splits_beyond_gap(self) -> None:
        assert _cluster_lines_to_ranges([10, 15], gap=3) == [(10, 10), (15, 15)]

    def test_filters_invalid_lines(self) -> None:
        assert _cluster_lines_to_ranges([0, -1, 3, 3], gap=3) == [(3, 3)]


class TestBuildTargetRanges:
    def test_falls_back_when_too_many_clusters(self) -> None:
        # With GAP=3, these become 3 clusters -> fall back to a single span.
        result = _build_target_ranges([1, 10, 20], context_start=1, context_end=30)
        assert result == [(1, 20)]

    def test_clamps_to_context(self) -> None:
        result = _build_target_ranges([1, 10, 20], context_start=5, context_end=15)
        assert result == [(5, 15)]


class TestDatasetCaseGroundTruthFiles:
    def test_prefers_target_ranges(self) -> None:
        case = DatasetCase(
            id="c1",
            query="q",
            repo="r",
            base_commit="abc",
            hard_gt=[
                GroundTruthEntry(
                    path="a.py",
                    function="foo",
                    range=(100, 200),
                    target_ranges=[(110, 112), (150, 150)],
                )
            ],
        )
        assert case.ground_truth_files == {"a.py": [(110, 112), (150, 150)]}
        assert case.ground_truth_context_files == {"a.py": [(100, 200)]}

    def test_falls_back_to_context_range(self) -> None:
        case = DatasetCase(
            id="c2",
            query="q",
            repo="r",
            base_commit="abc",
            hard_gt=[
                GroundTruthEntry(
                    path="a.py",
                    function="foo",
                    range=(10, 20),
                    target_ranges=[],
                )
            ],
        )
        assert case.ground_truth_files == {"a.py": [(10, 20)]}
