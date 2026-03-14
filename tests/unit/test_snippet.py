import pytest

from relace_mcp.tools.apply.snippet import (
    anchor_precheck,
    check_symbol_preservation,
    concrete_lines,
    count_effective_diff_lines,
    expects_changes,
    extract_remove_targets,
    extract_top_level_symbols,
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


class TestAnchorPrecheckCluster:
    """Test anchor cluster validation (80-line window)."""

    def test_accepts_clustered_anchors(self) -> None:
        """Anchors in same region should pass."""
        # Build a file where anchors are close together (lines 2 and 3)
        lines = [f"line_{i}_padding_content" for i in range(100)]
        lines[2] = "def target_function_here():"
        lines[3] = "    return important_value_42"
        initial_code = "\n".join(lines)

        concrete = ["def target_function_here():", "    return important_value_42"]
        assert anchor_precheck(concrete, initial_code) is True

    def test_rejects_scattered_anchors(self) -> None:
        """Anchors separated by more than 80 lines should fail."""
        lines = [f"line_{i}_padding_content" for i in range(200)]
        lines[5] = "def first_anchor_function():"
        lines[150] = "def second_anchor_far_away():"
        initial_code = "\n".join(lines)

        concrete = ["def first_anchor_function():", "def second_anchor_far_away():"]
        assert anchor_precheck(concrete, initial_code) is False

    def test_accepts_anchors_at_boundary(self) -> None:
        """Anchors exactly 80 lines apart should pass."""
        lines = [f"line_{i}_padding_content" for i in range(200)]
        lines[10] = "def boundary_start_function():"
        lines[90] = "def boundary_end_function():"
        initial_code = "\n".join(lines)

        concrete = ["def boundary_start_function():", "def boundary_end_function():"]
        assert anchor_precheck(concrete, initial_code) is True

    def test_rejects_anchors_just_beyond_boundary(self) -> None:
        """Anchors 81 lines apart should fail."""
        lines = [f"line_{i}_padding_content" for i in range(200)]
        lines[10] = "def just_beyond_start_fn():"
        lines[91] = "def just_beyond_end_fn():"
        initial_code = "\n".join(lines)

        concrete = ["def just_beyond_start_fn():", "def just_beyond_end_fn():"]
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


class TestCountEffectiveDiffLines:
    """Test count_effective_diff_lines function."""

    def test_counts_real_changes(self) -> None:
        """Should count added/deleted lines with content."""
        diff = (
            "--- before\n"
            "+++ after\n"
            "@@ -1,3 +1,3 @@\n"
            "-old_line_one\n"
            "+new_line_one\n"
            " unchanged\n"
            "-old_line_two\n"
            "+new_line_two\n"
        )
        assert count_effective_diff_lines(diff) == 4

    def test_excludes_whitespace_only(self) -> None:
        """Should not count whitespace-only changes."""
        diff = (
            "--- before\n"
            "+++ after\n"
            "@@ -1,4 +1,4 @@\n"
            "-real_change_here\n"
            "+real_replacement_here\n"
            "-   \n"
            "+     \n"
            "-\t\n"
            "+\t\t\n"
        )
        assert count_effective_diff_lines(diff) == 2

    def test_empty_diff(self) -> None:
        """Should return 0 for empty diff."""
        assert count_effective_diff_lines("") == 0

    def test_ignores_context_lines(self) -> None:
        """Should not count unchanged context lines."""
        diff = (
            "--- before\n"
            "+++ after\n"
            "@@ -1,3 +1,4 @@\n"
            " context_line_unchanged\n"
            "+added_new_line_content\n"
            " another_context_line\n"
        )
        assert count_effective_diff_lines(diff) == 1


class TestAnchorPrecheckRepeatedAnchors:
    """Test anchor cluster validation with repeated anchor text in file."""

    def test_accepts_when_close_occurrence_exists(self) -> None:
        """Should accept when a closer occurrence of anchor exists near target."""
        lines = [f"line_{i}_padding_content" for i in range(250)]
        # First occurrence far away
        lines[5] = 'logger.info("processing started")'
        # Target cluster near line 200
        lines[200] = 'logger.info("processing started")'
        lines[201] = "result = compute_important_value()"
        initial_code = "\n".join(lines)

        concrete = [
            'logger.info("processing started")',
            "result = compute_important_value()",
        ]
        assert anchor_precheck(concrete, initial_code) is True

    def test_rejects_when_all_occurrences_scattered(self) -> None:
        """Should reject when no combination of occurrences clusters."""
        lines = [f"line_{i}_padding_content" for i in range(300)]
        lines[5] = "def handler_function_alpha():"
        lines[250] = "def handler_function_beta():"
        initial_code = "\n".join(lines)

        concrete = ["def handler_function_alpha():", "def handler_function_beta():"]
        assert anchor_precheck(concrete, initial_code) is False


class TestExtractTopLevelSymbols:
    """Test extract_top_level_symbols for Python files."""

    def test_extracts_functions_and_classes(self) -> None:
        code = "import os\n\ndef foo():\n    pass\n\nclass Bar:\n    pass\n"
        symbols = extract_top_level_symbols(code, "test.py")
        assert "foo" in symbols
        assert "Bar" in symbols

    def test_does_not_extract_imports(self) -> None:
        code = "import os\nfrom pathlib import Path\n\ndef main():\n    pass\n"
        symbols = extract_top_level_symbols(code, "test.py")
        assert "os" not in symbols
        assert "Path" not in symbols
        assert "main" in symbols

    def test_non_python_excludes_imports(self) -> None:
        """Non-Python files should not include import names as symbols."""
        code = "import React from 'react'\nexport function App() { return null }\n"
        symbols = extract_top_level_symbols(code, "app.tsx")
        assert "React" not in symbols
        assert "App" in symbols

    def test_go_excludes_imports(self) -> None:
        """Go import names should not be included as symbols."""
        code = 'import "fmt"\n\nfunc main() {\n}\n'
        symbols = extract_top_level_symbols(code, "main.go")
        assert "fmt" not in symbols


class TestCheckSymbolPreservation:
    """Test check_symbol_preservation function."""

    def test_passes_when_symbols_preserved(self) -> None:
        initial = "def foo():\n    pass\n\ndef bar():\n    pass\n"
        merged = "def foo():\n    return 1\n\ndef bar():\n    pass\n"
        passed, _ = check_symbol_preservation(initial, merged, "", "test.py")
        assert passed is True

    def test_fails_when_function_lost(self) -> None:
        initial = "def foo():\n    pass\n\ndef bar():\n    pass\n"
        merged = "def foo():\n    pass\n"
        passed, reason = check_symbol_preservation(initial, merged, "", "test.py")
        assert passed is False
        assert reason is not None
        assert "bar" in reason

    def test_allows_import_removal(self) -> None:
        """Import changes should NOT trigger SYMBOL_LOST."""
        initial = "import os\nfrom pathlib import Path\n\ndef main():\n    pass\n"
        merged = "from os.path import join\n\ndef main():\n    pass\n"
        passed, _ = check_symbol_preservation(initial, merged, "", "test.py")
        assert passed is True

    def test_allows_remove_directive(self) -> None:
        initial = "def foo():\n    pass\n\ndef bar():\n    pass\n"
        merged = "def foo():\n    pass\n"
        passed, _ = check_symbol_preservation(initial, merged, "# remove bar", "test.py")
        assert passed is True

    def test_ts_import_removal_not_flagged(self) -> None:
        """Removing TS imports should NOT trigger SYMBOL_LOST."""
        initial = "import React from 'react'\nexport function App() { return null }\n"
        merged = "export function App() { return null }\n"
        passed, _ = check_symbol_preservation(initial, merged, "", "app.tsx")
        assert passed is True
