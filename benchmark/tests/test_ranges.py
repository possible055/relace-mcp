from benchmark.metrics.ranges import (
    intersection_length,
    normalize_line_ranges,
)


class TestNormalizeLineRanges:
    def test_empty(self) -> None:
        assert normalize_line_ranges([]) == []

    def test_valid_tuples(self) -> None:
        result = normalize_line_ranges([(1, 5), (3, 8)])
        assert result == [(1, 8)]

    def test_filters_invalid_types(self) -> None:
        result = normalize_line_ranges(
            [
                (1, 5),
                ("a", "b"),  # type: ignore[list-item]
            ]
        )
        assert result == [(1, 5)]

    def test_filters_invalid_start(self) -> None:
        result = normalize_line_ranges(
            [
                (1, 5),
                (0, 3),  # start must be > 0
            ]
        )
        assert result == [(1, 5)]

    def test_filters_invalid_order(self) -> None:
        result = normalize_line_ranges(
            [
                (1, 5),
                (5, 3),  # end < start
            ]
        )
        assert result == [(1, 5)]

    def test_list_format_works(self) -> None:
        result = normalize_line_ranges([[10, 15]])  # type: ignore[list-item]
        assert result == [(10, 15)]


class TestIntersectionLength:
    def test_no_overlap(self) -> None:
        assert intersection_length([(1, 5)], [(10, 15)]) == 0

    def test_full_overlap(self) -> None:
        assert intersection_length([(1, 10)], [(1, 10)]) == 10

    def test_partial_overlap(self) -> None:
        assert intersection_length([(1, 10)], [(5, 15)]) == 6

    def test_multiple_ranges(self) -> None:
        a = [(1, 5), (10, 15)]
        b = [(3, 12)]
        # (3,5) = 3 lines, (10,12) = 3 lines
        assert intersection_length(a, b) == 6

    def test_empty_lists(self) -> None:
        assert intersection_length([], [(1, 10)]) == 0
        assert intersection_length([(1, 10)], []) == 0
