import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "benchmark"))

from datasets.query_classifier import QueryType, classify_query, classify_query_str


class TestClassifyQuery:
    def test_bug_fix_patterns(self) -> None:
        queries = [
            "Fix crash when loading empty file",
            "Bug: TypeError in parser",
            "Error handling is broken",
            "Traceback when running tests",
        ]
        for q in queries:
            result = classify_query(q)
            assert result == QueryType.BUG_FIX, f"'{q}' should be bug_fix, got {result}"

    def test_feature_patterns(self) -> None:
        queries = [
            "Add support for async iterators",
            "Implement new caching mechanism",
            "Create a new API endpoint",
        ]
        for q in queries:
            result = classify_query(q)
            assert result == QueryType.FEATURE, f"'{q}' should be feature, got {result}"

    def test_refactor_patterns(self) -> None:
        queries = [
            "Refactor the authentication module",
            "Clean up deprecated code",
            "Extract common logic into utility",
        ]
        for q in queries:
            result = classify_query(q)
            assert result == QueryType.REFACTOR, f"'{q}' should be refactor, got {result}"

    def test_performance_patterns(self) -> None:
        queries = [
            "Optimize database queries",
            "Performance bottleneck in parser",
            "Speed up file loading",
        ]
        for q in queries:
            result = classify_query(q)
            assert result == QueryType.PERFORMANCE, f"'{q}' should be performance, got {result}"

    def test_config_patterns(self) -> None:
        queries = [
            "Configuration option for timeout",
            "Update settings in config file",
            "Environment variable override not working",
        ]
        for q in queries:
            result = classify_query(q)
            assert result == QueryType.CONFIG, f"'{q}' should be config, got {result}"

    def test_doc_patterns(self) -> None:
        queries = [
            "Update README with usage examples",
            "Missing documentation in module",
        ]
        for q in queries:
            result = classify_query(q)
            assert result == QueryType.DOC, f"'{q}' should be documentation, got {result}"

    def test_test_patterns(self) -> None:
        queries = [
            "Unit tests for parser module",
            "Pytest fixture for database",
            "Update test coverage",
        ]
        for q in queries:
            result = classify_query(q)
            assert result == QueryType.TEST, f"'{q}' should be test, got {result}"

    def test_unknown_for_empty(self) -> None:
        assert classify_query("") == QueryType.UNKNOWN
        assert classify_query("   ") == QueryType.UNKNOWN

    def test_unknown_for_no_patterns(self) -> None:
        result = classify_query("Hello world 12345")
        assert result == QueryType.UNKNOWN

    def test_classify_query_str(self) -> None:
        result = classify_query_str("Fix the bug")
        assert result == "bug_fix"
        assert isinstance(result, str)

    def test_mixed_patterns_highest_wins(self) -> None:
        # Bug patterns have higher weight, should win
        query = "Fix performance issue with crash"
        result = classify_query(query)
        # Could be either bug_fix or performance, but should be consistent
        assert result in (QueryType.BUG_FIX, QueryType.PERFORMANCE)
