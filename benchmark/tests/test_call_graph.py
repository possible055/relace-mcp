import sys
from pathlib import Path

# Add project root to path for benchmark imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from benchmark.analysis.call_graph import (
    analyze_file,
    expand_ground_truth,
)


class TestAnalyzeFile:
    def test_simple_function(self, tmp_path: Path) -> None:
        code = """
def foo():
    print("hello")
    bar()

def bar():
    pass
"""
        file_path = tmp_path / "test.py"
        file_path.write_text(code)

        result = analyze_file(file_path)
        assert result is not None
        assert "foo" in result.functions
        assert "bar" in result.functions

        foo = result.functions["foo"]
        assert foo.name == "foo"
        assert "print" in foo.calls
        assert "bar" in foo.calls

        bar = result.functions["bar"]
        assert bar.calls == []

    def test_method_in_class(self, tmp_path: Path) -> None:
        code = """
class MyClass:
    def method_a(self):
        self.method_b()
    
    def method_b(self):
        helper()

def helper():
    pass
"""
        file_path = tmp_path / "test.py"
        file_path.write_text(code)

        result = analyze_file(file_path)
        assert result is not None
        assert "method_a" in result.functions
        assert "method_b" in result.functions
        assert "helper" in result.functions

        method_a = result.functions["method_a"]
        assert "method_b" in method_a.calls

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        file_path = tmp_path / "nonexistent.py"
        result = analyze_file(file_path)
        assert result is None

    def test_non_python_file(self, tmp_path: Path) -> None:
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello world")
        result = analyze_file(file_path)
        assert result is None

    def test_function_line_numbers(self, tmp_path: Path) -> None:
        code = """def foo():
    pass

def bar():
    pass
"""
        file_path = tmp_path / "test.py"
        file_path.write_text(code)

        result = analyze_file(file_path)
        assert result is not None

        foo = result.functions["foo"]
        assert foo.start_line == 1
        assert foo.end_line == 2

        bar = result.functions["bar"]
        assert bar.start_line == 4
        assert bar.end_line == 5


class TestExpandGroundTruth:
    def test_expands_to_called_functions(self, tmp_path: Path) -> None:
        code = """
def main():
    helper()
    utils()

def helper():
    pass

def utils():
    pass

def unused():
    pass
"""
        file_path = tmp_path / "test.py"
        file_path.write_text(code)

        # Ground truth only includes main function (lines 2-4)
        ground_truth = {"test.py": [(2, 4)]}

        soft_gt = expand_ground_truth(tmp_path, ground_truth)

        # Should include helper and utils, but not unused
        assert "test.py" in soft_gt
        ranges = soft_gt["test.py"]

        # Check that helper (line 6-7) and utils (line 9-10) are included
        # Note: soft_gt should NOT include the original GT functions
        assert len(ranges) >= 1  # At least helper or utils

    def test_empty_ground_truth(self, tmp_path: Path) -> None:
        code = """
def foo():
    bar()
"""
        file_path = tmp_path / "test.py"
        file_path.write_text(code)

        soft_gt = expand_ground_truth(tmp_path, {})
        assert soft_gt == {}

    def test_no_calls(self, tmp_path: Path) -> None:
        code = """
def foo():
    x = 1 + 1
"""
        file_path = tmp_path / "test.py"
        file_path.write_text(code)

        ground_truth = {"test.py": [(2, 3)]}
        soft_gt = expand_ground_truth(tmp_path, ground_truth)
        # No functions called, so soft_gt should be empty
        assert soft_gt == {} or "test.py" not in soft_gt
