import pytest

from relace_mcp.tools.apply.snippet import (
    anchor_precheck,
    check_symbol_preservation,
    concrete_lines,
    count_effective_diff_lines,
    estimate_removed_lines,
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
        """Should pass when 2+ anchors found (both unique)."""
        concrete = ["def hello_world():", "    print('Hello, World!')"]
        initial_code = "def hello_world():\n    print('Hello, World!')\n"
        passed, warning = anchor_precheck(concrete, initial_code)
        assert passed is True
        assert warning is None

    def test_rejects_no_anchors(self) -> None:
        """Should block when no anchors match."""
        concrete = ["def totally_different():", "    return 999"]
        initial_code = "def hello_world():\n    print('Hello')\n"
        passed, warning = anchor_precheck(concrete, initial_code)
        assert passed is False

    def test_rejects_short_anchors_only(self) -> None:
        """Should block when only short anchors (like 'return') are found."""
        concrete = ["return", "}"]
        initial_code = "def foo():\n    return\n"
        passed, warning = anchor_precheck(concrete, initial_code)
        assert passed is False


class TestAnchorPrecheckEdgeCases:
    """Test anchor_precheck 3-tier logic."""

    def test_single_unique_anchor_no_warning(self) -> None:
        """1 unique match → pass, no warning."""
        lines = [f"line_{i}_padding_content" for i in range(100)]
        lines[50] = "def single_valid_anchor_fn():"
        initial_code = "\n".join(lines)

        passed, warning = anchor_precheck(["def single_valid_anchor_fn():"], initial_code)
        assert passed is True
        assert warning is None  # unique → no warning

    def test_two_anchors_no_warning(self) -> None:
        """2+ matches → pass, no warning regardless of uniqueness."""
        lines = [f"line_{i}_padding_content" for i in range(500)]
        lines[10] = "def function_at_start():"
        lines[490] = "def function_at_end():"
        initial_code = "\n".join(lines)

        passed, warning = anchor_precheck(
            ["def function_at_start():", "def function_at_end():"], initial_code
        )
        assert passed is True
        assert warning is None

    def test_single_ambiguous_anchor_warns(self) -> None:
        """1 match that appears multiple times → pass with WEAK_ANCHOR warning."""
        initial_code = (
            "def handler():\n"
            "    logger.info('processing request')\n"
            "    return 1\n\n"
            "def other_handler():\n"
            "    logger.info('processing request')\n"
            "    return 2\n"
        )
        passed, warning = anchor_precheck(["    logger.info('processing request')"], initial_code)
        assert passed is True
        assert warning is not None
        assert "WEAK_ANCHOR" in warning

    def test_rejects_when_no_anchor_matches(self) -> None:
        """Should block when no anchor line (≥10 chars) exists in the file."""
        initial_code = "def existing_function():\n    return 42\n"
        concrete = ["def completely_wrong_function():", "    return totally_different"]
        passed, _ = anchor_precheck(concrete, initial_code)
        assert passed is False

    def test_accepts_with_remove_directive_and_anchor(self) -> None:
        """Remove directives alone don't count, but a real anchor alongside does."""
        initial_code = "def keep_me():\n    return 1\n\ndef delete_me():\n    return 2\n"
        concrete = ["// remove delete_me", "def keep_me():"]
        passed, warning = anchor_precheck(concrete, initial_code)
        assert passed is True
        assert warning is None  # "def keep_me():" is unique → no warning

    def test_rejects_only_remove_directives(self) -> None:
        """Only remove directives, no real anchors → block."""
        initial_code = "def foo():\n    return 1\n"
        concrete = ["// remove foo", "# remove bar"]
        passed, _ = anchor_precheck(concrete, initial_code)
        assert passed is False


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
        """Should return max(added, deleted) for paired replacements."""
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
        # 2 deleted, 2 added → max(2, 2) = 2
        assert count_effective_diff_lines(diff) == 2

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
        # 1 real deleted, 1 real added → max(1, 1) = 1
        assert count_effective_diff_lines(diff) == 1

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
        """Go import names should not be included, but func should be extracted."""
        code = 'import "fmt"\n\nfunc main() {\n}\n'
        symbols = extract_top_level_symbols(code, "main.go")
        assert "fmt" not in symbols
        assert "main" in symbols

    def test_go_func_and_type(self) -> None:
        """Should extract Go func (including methods) and type declarations."""
        code = (
            "package server\n\n"
            "type Config struct {\n    Port int\n}\n\n"
            "func NewServer() *Server {\n    return nil\n}\n\n"
            "func (s *Server) Handle() {\n}\n"
        )
        symbols = extract_top_level_symbols(code, "server.go")
        assert "Config" in symbols
        assert "NewServer" in symbols
        assert "Handle" in symbols

    def test_rust_fn_struct_enum_trait(self) -> None:
        """Should extract Rust fn, struct, enum, trait, impl (with pub variants)."""
        code = (
            "use std::io;\n\n"
            "fn helper() -> i32 { 0 }\n\n"
            "pub fn new() -> Self { Self {} }\n\n"
            "struct Foo {\n    x: i32,\n}\n\n"
            "pub(crate) enum Bar {\n    A,\n    B,\n}\n\n"
            "trait Baz {\n    fn do_it(&self);\n}\n\n"
            "impl Foo {\n    fn method(&self) {}\n}\n"
        )
        symbols = extract_top_level_symbols(code, "lib.rs")
        assert "helper" in symbols
        assert "new" in symbols
        assert "Foo" in symbols
        assert "Bar" in symbols
        assert "Baz" in symbols
        # impl block — Foo extracted as the impl target
        assert symbols.count("Foo") == 1  # deduplicated

    def test_ts_arrow_functions(self) -> None:
        """Should extract TS/JS const/let/var arrow function declarations."""
        code = (
            "import React from 'react'\n\n"
            "export const App = () => {\n  return null\n}\n\n"
            "const handler = async () => {\n  await fetch()\n}\n\n"
            "let mutable = () => {}\n"
        )
        symbols = extract_top_level_symbols(code, "app.tsx")
        assert "React" not in symbols
        assert "App" in symbols
        assert "handler" in symbols
        assert "mutable" in symbols

    def test_ts_interface(self) -> None:
        """Should extract TS interface declarations."""
        code = (
            "export interface UserProps {\n  name: string\n}\n\n"
            "interface InternalConfig {\n  port: number\n}\n"
        )
        symbols = extract_top_level_symbols(code, "types.ts")
        assert "UserProps" in symbols
        assert "InternalConfig" in symbols


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


class TestEstimateRemovedLines:
    """Test estimate_removed_lines function."""

    def test_python_function(self) -> None:
        """Should count lines of a matching Python function."""
        code = "def small():\n    return 1\n\ndef big_func():\n    x = 1\n    y = 2\n    return x + y\n"
        # big_func has 4 lines (def + 3 body lines)
        result = estimate_removed_lines(code, ["big_func"])
        assert result == 4

    def test_no_match(self) -> None:
        """Should return 0 when target is not found."""
        code = "def foo():\n    return 1\n"
        assert estimate_removed_lines(code, ["nonexistent"]) == 0

    def test_empty_targets(self) -> None:
        """Should return 0 for empty target list."""
        code = "def foo():\n    return 1\n"
        assert estimate_removed_lines(code, []) == 0

    def test_multiple_targets(self) -> None:
        """Should sum lines of multiple targets."""
        code = (
            "def alpha():\n    return 1\n\n"
            "def beta():\n    return 2\n\n"
            "def gamma():\n    return 3\n"
        )
        # alpha: def + body + blank separator = 3 lines, beta: def + body + blank = 3 lines
        result = estimate_removed_lines(code, ["alpha", "beta"])
        assert result == 6
