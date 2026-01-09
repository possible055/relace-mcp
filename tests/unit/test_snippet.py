"""Tests for snippet.py functions."""

import pytest

from relace_mcp.tools.apply.snippet import (
    anchor_precheck,
    concrete_lines,
    expects_changes,
    extract_remove_targets,
    is_truncation_placeholder,
    post_check_merged_code,
    validate_syntax_delta,
)


class TestIsTruncationPlaceholder:
    """Test is_truncation_placeholder function."""

    @pytest.mark.parametrize(
        "line,expected",
        [
            ("// ... existing code ...", True),
            ("# ... existing code ...", True),
            ("// ...", True),
            ("# ...", True),
            ("  // ... existing code ...  ", True),
            ("", True),
            ("   ", True),
            ("def foo():", False),
            ("// remove SomeClass", False),
            ("# remove SomeFunc", False),
            ("// some comment", False),
        ],
    )
    def test_placeholder_detection(self, line: str, expected: bool) -> None:
        """Should correctly identify truncation placeholders."""
        assert is_truncation_placeholder(line) == expected


class TestConcreteLines:
    """Test concrete_lines function."""

    def test_filters_placeholders(self) -> None:
        """Should filter out placeholder lines."""
        text = """def foo():
    # ... existing code ...
    return 42
// ... more code ..."""
        result = concrete_lines(text)
        assert "def foo():" in result
        assert "    return 42" in result
        assert len(result) == 2

    def test_keeps_remove_directives(self) -> None:
        """Should keep remove directives (they are not placeholders)."""
        text = """def foo():
// remove OldFunction
# remove AnotherFunc"""
        result = concrete_lines(text)
        assert "// remove OldFunction" in result
        assert "# remove AnotherFunc" in result


class TestAnchorPrecheck:
    """Test anchor_precheck function."""

    def test_finds_anchors(self) -> None:
        """Should return True when anchors are found."""
        concrete = ["def hello_world():", "    print('Hello, World!')"]
        initial_code = "def hello_world():\n    print('Hello, World!')\n"
        assert anchor_precheck(concrete, initial_code) is True

    def test_rejects_no_anchors(self) -> None:
        """Should return False when no anchors are found."""
        concrete = ["def totally_different():", "    return 999"]
        initial_code = "def hello_world():\n    print('Hello')\n"
        assert anchor_precheck(concrete, initial_code) is False

    def test_rejects_short_anchors_only(self) -> None:
        """Should reject when only short anchors (like 'return') are found."""
        concrete = ["return", "}"]
        initial_code = "def foo():\n    return\n"
        assert anchor_precheck(concrete, initial_code) is False


class TestExtractRemoveTargets:
    """Test extract_remove_targets function."""

    def test_extracts_js_style(self) -> None:
        """Should extract // remove targets."""
        snippet = "// remove OldFunction\n// remove AnotherClass"
        assert extract_remove_targets(snippet) == ["OldFunction", "AnotherClass"]

    def test_extracts_python_style(self) -> None:
        """Should extract # remove targets."""
        snippet = "# remove deprecated_func\n# remove OldClass"
        assert extract_remove_targets(snippet) == ["deprecated_func", "OldClass"]

    def test_mixed_styles(self) -> None:
        """Should handle mixed styles."""
        snippet = "// remove Foo\n# remove Bar"
        assert extract_remove_targets(snippet) == ["Foo", "Bar"]

    def test_empty_snippet(self) -> None:
        """Should return empty list for no directives."""
        assert extract_remove_targets("def foo(): pass") == []


class TestExpectsChanges:
    """Test expects_changes function."""

    def test_new_code_expects_changes(self) -> None:
        """Should expect changes when new code is added."""
        snippet = "def foo():\n    new_feature_implementation()"
        initial = "def foo():\n    pass"
        assert expects_changes(snippet, initial) is True

    def test_same_code_no_changes(self) -> None:
        """Should not expect changes when code is identical."""
        snippet = "def foo():\n    pass"
        initial = "def foo():\n    pass\n"
        assert expects_changes(snippet, initial) is False

    def test_remove_directive_expects_changes(self) -> None:
        """Should expect changes when remove directive is present."""
        snippet = "// remove OldFunction"
        initial = "def OldFunction(): pass"
        assert expects_changes(snippet, initial) is True


class TestPostCheckMergedCode:
    """Test post_check_merged_code function."""

    def test_passes_when_new_lines_present(self) -> None:
        """Should pass when new lines are in merged code."""
        snippet = "def foo():\n    new_feature_call_here()"
        merged = "def foo():\n    new_feature_call_here()\n"
        initial = "def foo():\n    pass\n"
        passed, reason = post_check_merged_code(snippet, merged, initial)
        assert passed is True
        assert reason is None

    def test_fails_when_new_lines_missing(self) -> None:
        """Should fail when new lines are missing from merged code."""
        snippet = "def foo():\n    brand_new_feature_call()"
        merged = "def foo():\n    pass\n"
        initial = "def foo():\n    pass\n"
        passed, reason = post_check_merged_code(snippet, merged, initial)
        assert passed is False
        assert reason is not None
        assert "new lines found" in reason

    def test_fails_when_remove_target_still_exists(self) -> None:
        """Should fail when remove target still exists."""
        snippet = "// remove OldFunction"
        merged = "def OldFunction(): pass\n"
        initial = "def OldFunction(): pass\n"
        passed, reason = post_check_merged_code(snippet, merged, initial)
        assert passed is False
        assert reason is not None
        assert "OldFunction" in reason


class TestValidateSyntaxDelta:
    """Test L1 syntax validation."""

    def test_valid_python_passes(self) -> None:
        """Should pass when merged_code is syntactically correct."""
        initial = "def foo():\n    pass\n"
        merged = "def foo():\n    return 42\n"
        passed, reason = validate_syntax_delta(initial, merged, "test.py")
        assert passed is True
        assert reason is None

    def test_syntax_error_fails(self) -> None:
        """Should fail when merged_code has syntax error."""
        initial = "def foo():\n    pass\n"
        merged = "def foo(:\n    return 42\n"
        passed, reason = validate_syntax_delta(initial, merged, "test.py")
        assert passed is False
        assert reason is not None
        assert "SyntaxError" in reason

    def test_indentation_error_fails(self) -> None:
        """Should fail when merged_code has indentation error."""
        initial = "def foo():\n    pass\n"
        merged = "def foo():\nreturn 42\n"
        passed, reason = validate_syntax_delta(initial, merged, "test.py")
        assert passed is False
        assert reason is not None
        assert "SyntaxError" in reason or "indent" in reason.lower()

    def test_initial_error_ignored(self) -> None:
        """Should not fail when initial_code already had syntax error."""
        initial = "def foo(:\n    pass\n"
        merged = "def bar(:\n    return\n"
        passed, reason = validate_syntax_delta(initial, merged, "test.py")
        assert passed is True
        assert reason is None

    def test_non_python_skipped(self) -> None:
        """Should skip validation for non-Python files."""
        initial = "function foo() {"
        merged = "function foo( {"
        passed, reason = validate_syntax_delta(initial, merged, "test.js")
        assert passed is True
        assert reason is None

    def test_typescript_skipped(self) -> None:
        """Should skip validation for TypeScript files."""
        initial = "const x: number = 1;"
        merged = "const x number = 1;"
        passed, reason = validate_syntax_delta(initial, merged, "test.ts")
        assert passed is True
        assert reason is None

    def test_unclosed_string_fails(self) -> None:
        """Should fail when merged_code has unclosed string."""
        initial = "x = 'hello'\n"
        merged = "x = 'hello\n"
        passed, reason = validate_syntax_delta(initial, merged, "test.py")
        assert passed is False
        assert reason is not None
        assert "SyntaxError" in reason

    def test_missing_colon_fails(self) -> None:
        """Should fail when merged_code is missing colon."""
        initial = "if True:\n    pass\n"
        merged = "if True\n    pass\n"
        passed, reason = validate_syntax_delta(initial, merged, "test.py")
        assert passed is False
        assert reason is not None
        assert "SyntaxError" in reason
