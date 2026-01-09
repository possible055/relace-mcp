import sys
from pathlib import Path

import pytest

# Add project root to path for benchmark imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.analysis.ast_spans import (
    _find_enclosing_node,
    _lines_to_ranges_fallback,
    normalize_to_ast_spans,
)
from benchmark.analysis.treesitter import get_parser as _get_parser
from benchmark.metrics.ranges import merge_ranges as _merge_ranges


class TestMergeRanges:
    def test_empty(self) -> None:
        assert _merge_ranges([]) == []

    def test_single_range(self) -> None:
        assert _merge_ranges([(1, 5)]) == [(1, 5)]

    def test_non_overlapping(self) -> None:
        assert _merge_ranges([(1, 3), (5, 7)]) == [(1, 3), (5, 7)]

    def test_overlapping(self) -> None:
        assert _merge_ranges([(1, 5), (3, 7)]) == [(1, 7)]

    def test_adjacent(self) -> None:
        assert _merge_ranges([(1, 3), (4, 6)]) == [(1, 6)]

    def test_unsorted_input(self) -> None:
        assert _merge_ranges([(5, 7), (1, 3)]) == [(1, 3), (5, 7)]


class TestFindEnclosingNode:
    @pytest.fixture
    def sample_code(self) -> bytes:
        return b"""
class MyClass:
    def method_one(self):
        x = 1
        return x
    
    def method_two(self):
        y = 2
        return y

def standalone_function():
    z = 3
    return z
"""

    def test_finds_function(self, sample_code: bytes) -> None:
        parser = _get_parser()
        tree = parser.parse(sample_code)

        # Line 4 is inside method_one
        result = _find_enclosing_node(tree, 4)
        assert result is not None
        start, end = result
        assert start <= 4 <= end

    def test_finds_class(self, sample_code: bytes) -> None:
        parser = _get_parser()
        tree = parser.parse(sample_code)

        # Line 2 is at class definition
        result = _find_enclosing_node(tree, 2)
        assert result is not None
        start, end = result
        assert start == 2

    def test_standalone_function(self, sample_code: bytes) -> None:
        parser = _get_parser()
        tree = parser.parse(sample_code)

        # Line 12 is inside standalone_function
        result = _find_enclosing_node(tree, 12)
        assert result is not None
        start, end = result
        assert start <= 12 <= end

    def test_no_enclosing_node(self, sample_code: bytes) -> None:
        parser = _get_parser()
        tree = parser.parse(sample_code)

        # Line 1 is blank, outside any node
        result = _find_enclosing_node(tree, 1)
        assert result is None


class TestNormalizeToAstSpans:
    @pytest.fixture
    def python_file(self, tmp_path: Path) -> Path:
        code = """def foo():
    x = 1
    y = 2
    return x + y

def bar():
    return 42
"""
        file_path = tmp_path / "sample.py"
        file_path.write_text(code)
        return file_path

    def test_expands_to_function_boundary(self, python_file: Path) -> None:
        # Line 2 is inside foo(), should expand to cover whole function
        result = normalize_to_ast_spans(python_file, {2}, context_padding=0)
        assert len(result) >= 1
        start, end = result[0]
        assert start == 1  # foo() starts at line 1
        assert end >= 4  # foo() ends at line 4

    def test_multiple_lines_same_function(self, python_file: Path) -> None:
        result = normalize_to_ast_spans(python_file, {2, 3}, context_padding=0)
        assert len(result) == 1  # Should merge into single span
        start, end = result[0]
        assert start == 1
        assert end >= 4

    def test_lines_in_different_functions(self, python_file: Path) -> None:
        result = normalize_to_ast_spans(python_file, {2, 7}, context_padding=0)
        assert len(result) == 2  # Two separate spans

    def test_context_padding(self, python_file: Path) -> None:
        result = normalize_to_ast_spans(python_file, {2}, context_padding=2)
        assert len(result) >= 1
        start, end = result[0]
        assert start <= 1  # With padding, should start at 1 (can't go below 1)
        assert end >= 6  # Should extend 2 lines beyond function end

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "nonexistent.py"
        result = normalize_to_ast_spans(fake_path, {1, 2, 3}, context_padding=2)
        # Should fall back gracefully
        assert len(result) >= 1

    def test_empty_lines(self, python_file: Path) -> None:
        result = normalize_to_ast_spans(python_file, set(), context_padding=0)
        assert result == []


class TestLinesToRangesFallback:
    def test_single_line(self) -> None:
        result = _lines_to_ranges_fallback({5}, context_padding=2)
        assert result == [(3, 7)]

    def test_adjacent_lines(self) -> None:
        result = _lines_to_ranges_fallback({5, 6, 7}, context_padding=2)
        assert result == [(3, 9)]

    def test_gap_larger_than_padding(self) -> None:
        result = _lines_to_ranges_fallback({5, 15}, context_padding=2)
        assert len(result) == 2

    def test_respects_min_line_1(self) -> None:
        result = _lines_to_ranges_fallback({1}, context_padding=5)
        assert result[0][0] == 1  # Should not go below 1

    def test_empty_input(self) -> None:
        result = _lines_to_ranges_fallback(set(), context_padding=2)
        assert result == []
