"""Tests for LayeredMetrics and MetricsEngine."""

import pytest

from benchmark.domain.metrics.engine import (
    FilePrecisionStrategy,
    FileRecallStrategy,
    MetricsEngine,
    Turn,
)
from benchmark.domain.metrics.layered import (
    AggregateMetrics,
    FileAccessWithMetrics,
    LayeredMetrics,
    ToolContribution,
    TurnMetrics,
)


class TestTurnMetrics:
    def test_to_dict(self):
        metrics = TurnMetrics(
            turn_index=0,
            file_recall=0.8,
            file_precision=0.6,
            files_accessed=5,
            tools_used=["grep", "read"],
        )
        d = metrics.to_dict()
        assert d["turn_index"] == 0
        assert d["file_recall"] == 0.8
        assert d["tools_used"] == ["grep", "read"]

    def test_from_dict(self):
        data = {
            "turn_index": 1,
            "file_recall": 0.9,
            "file_precision": 0.7,
        }
        metrics = TurnMetrics.from_dict(data)
        assert metrics.turn_index == 1
        assert metrics.file_recall == 0.9


class TestToolContribution:
    def test_to_dict(self):
        contrib = ToolContribution(
            tool_name="agentic_search",
            files_found=10,
            files_hit_target=8,
            contribution_score=0.8,
        )
        d = contrib.to_dict()
        assert d["tool_name"] == "agentic_search"
        assert d["contribution_score"] == 0.8

    def test_from_dict(self):
        data = {
            "tool_name": "grep",
            "files_found": 5,
            "files_hit_target": 3,
        }
        contrib = ToolContribution.from_dict(data)
        assert contrib.tool_name == "grep"
        assert contrib.files_found == 5


class TestAggregateMetrics:
    def test_to_dict_and_from_dict(self):
        metrics = AggregateMetrics(
            file_recall=0.85,
            file_precision=0.75,
            total_turns=3,
            total_files_accessed=15,
        )
        d = metrics.to_dict()
        restored = AggregateMetrics.from_dict(d)
        assert restored.file_recall == 0.85
        assert restored.total_turns == 3


class TestFileAccessWithMetrics:
    def test_to_dict(self):
        fa = FileAccessWithMetrics(
            path="src/main.py",
            turn_index=0,
            tool_name="grep",
            access_type="search",
            is_target_hit=True,
            line_range=(10, 50),
        )
        d = fa.to_dict()
        assert d["path"] == "src/main.py"
        assert d["is_target_hit"] is True
        assert d["line_range"] == [10, 50]

    def test_from_dict(self):
        data = {
            "path": "src/util.py",
            "turn_index": 1,
            "tool_name": "read",
            "access_type": "read",
        }
        fa = FileAccessWithMetrics.from_dict(data)
        assert fa.path == "src/util.py"
        assert fa.is_target_hit is False


class TestLayeredMetrics:
    @pytest.fixture
    def sample_metrics(self) -> LayeredMetrics:
        return LayeredMetrics(
            by_turn={
                0: TurnMetrics(turn_index=0, file_recall=0.5, files_accessed=3),
                1: TurnMetrics(turn_index=1, file_recall=0.8, files_accessed=2),
            },
            by_tool={
                "grep": ToolContribution(
                    tool_name="grep",
                    files_found=3,
                    files_hit_target=2,
                    contribution_score=0.6,
                ),
                "read": ToolContribution(
                    tool_name="read",
                    files_found=2,
                    files_hit_target=1,
                    contribution_score=0.4,
                ),
            },
            aggregate=AggregateMetrics(
                file_recall=0.8,
                file_precision=0.4,
                total_turns=2,
            ),
            file_accesses=[
                FileAccessWithMetrics(
                    path="a.py",
                    turn_index=0,
                    tool_name="grep",
                    access_type="search",
                    is_target_hit=True,
                ),
                FileAccessWithMetrics(
                    path="b.py",
                    turn_index=0,
                    tool_name="grep",
                    access_type="search",
                    is_target_hit=False,
                ),
            ],
        )

    def test_get_turn_progression(self, sample_metrics: LayeredMetrics):
        progression = sample_metrics.get_turn_progression()
        assert progression == [0.5, 0.8]

    def test_get_top_contributing_tools(self, sample_metrics: LayeredMetrics):
        top = sample_metrics.get_top_contributing_tools(n=1)
        assert len(top) == 1
        assert top[0].tool_name == "grep"

    def test_explain_low_precision(self, sample_metrics: LayeredMetrics):
        explanations = sample_metrics.explain_low_precision(threshold=0.5)
        assert len(explanations) > 0
        assert "grep" in explanations[0]

    def test_to_dict_and_from_dict(self, sample_metrics: LayeredMetrics):
        d = sample_metrics.to_dict()
        restored = LayeredMetrics.from_dict(d)
        assert len(restored.by_turn) == 2
        assert len(restored.by_tool) == 2
        assert len(restored.file_accesses) == 2


class TestMetricStrategies:
    def test_file_recall_all_hit(self):
        strategy = FileRecallStrategy()
        result = strategy.compute(["a", "b", "c"], ["a", "b", "c"])
        assert result == 1.0

    def test_file_recall_partial(self):
        strategy = FileRecallStrategy()
        result = strategy.compute(["a", "b"], ["a", "b", "c"])
        assert abs(result - 2 / 3) < 0.01

    def test_file_recall_empty_gt(self):
        strategy = FileRecallStrategy()
        result = strategy.compute(["a"], [])
        assert result == 0.0

    def test_file_precision_all_correct(self):
        strategy = FilePrecisionStrategy()
        result = strategy.compute(["a", "b"], ["a", "b", "c"])
        assert result == 1.0

    def test_file_precision_partial(self):
        strategy = FilePrecisionStrategy()
        result = strategy.compute(["a", "b", "x"], ["a", "b"])
        assert abs(result - 2 / 3) < 0.01


class TestMetricsEngine:
    @pytest.fixture
    def engine(self) -> MetricsEngine:
        return MetricsEngine()

    def test_compute_all(self, engine: MetricsEngine):
        turns = [
            Turn(
                index=0,
                tool_calls=[
                    {"tool": "grep", "files": ["a.py", "b.py"]},
                ],
                files_accessed=["a.py", "b.py"],
            ),
            Turn(
                index=1,
                tool_calls=[
                    {"tool": "read", "files": ["c.py"]},
                ],
                files_accessed=["c.py"],
            ),
        ]
        ground_truth = ["a.py", "c.py"]

        metrics = engine.compute_all(turns, ground_truth)

        assert len(metrics.by_turn) == 2
        assert len(metrics.by_tool) == 2
        assert metrics.aggregate.total_turns == 2
        assert metrics.aggregate.file_recall == 1.0

    def test_compute_by_turn_cumulative(self, engine: MetricsEngine):
        turns = [
            Turn(index=0, tool_calls=[], files_accessed=["a.py"]),
            Turn(index=1, tool_calls=[], files_accessed=["b.py"]),
        ]
        ground_truth = ["a.py", "b.py"]

        by_turn = engine._compute_by_turn(turns, ground_truth)

        assert by_turn[0].file_recall == 0.5
        assert by_turn[1].file_recall == 1.0

    def test_compute_by_tool(self, engine: MetricsEngine):
        turns = [
            Turn(
                index=0,
                tool_calls=[
                    {"tool": "grep", "files": ["a.py", "b.py"]},
                    {"tool": "read", "files": ["c.py"]},
                ],
                files_accessed=["a.py", "b.py", "c.py"],
            ),
        ]
        ground_truth = ["a.py", "c.py"]

        by_tool = engine._compute_by_tool(turns, ground_truth)

        assert "grep" in by_tool
        assert "read" in by_tool
        assert by_tool["grep"].files_hit_target == 1
        assert by_tool["read"].files_hit_target == 1
