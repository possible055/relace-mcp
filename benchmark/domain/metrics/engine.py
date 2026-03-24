"""Metrics computation engine with strategy pattern.

Provides extensible metric computation using pluggable strategies.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from benchmark.domain.metrics.layered import (
    AggregateMetrics,
    FileAccessWithMetrics,
    LayeredMetrics,
    ToolContribution,
    TurnMetrics,
)


class MetricStrategy(Protocol):
    """Protocol for metric computation strategies."""

    def compute(
        self,
        predicted: list[str],
        ground_truth: list[str],
    ) -> float:
        """Compute metric value."""
        ...


class FileRecallStrategy:
    """Compute file-level recall."""

    def compute(self, predicted: list[str], ground_truth: list[str]) -> float:
        if not ground_truth:
            return 1.0 if not predicted else 0.0
        hits = len(set(predicted) & set(ground_truth))
        return hits / len(ground_truth)


class FilePrecisionStrategy:
    """Compute file-level precision."""

    def compute(self, predicted: list[str], ground_truth: list[str]) -> float:
        if not predicted:
            return 1.0 if not ground_truth else 0.0
        hits = len(set(predicted) & set(ground_truth))
        return hits / len(predicted)


@dataclass
class Turn:
    """Represents a single turn in the search process."""

    index: int
    tool_calls: list[dict[str, Any]]
    files_accessed: list[str]


class MetricsEngine:
    """Engine for computing layered metrics from search results."""

    def __init__(
        self,
        strategies: dict[str, MetricStrategy] | None = None,
    ):
        self.strategies = strategies or {
            "file_recall": FileRecallStrategy(),
            "file_precision": FilePrecisionStrategy(),
        }

    def compute_all(
        self,
        turns: list[Turn],
        ground_truth_files: list[str],
        ground_truth_functions: list[dict[str, Any]] | None = None,
    ) -> LayeredMetrics:
        """Compute all layered metrics from search turns."""
        by_turn = self._compute_by_turn(turns, ground_truth_files)
        by_tool = self._compute_by_tool(turns, ground_truth_files)
        file_accesses = self._extract_file_accesses(turns, ground_truth_files)
        aggregate = self._compute_aggregate(turns, ground_truth_files, ground_truth_functions)

        return LayeredMetrics(
            by_turn=by_turn,
            by_tool=by_tool,
            aggregate=aggregate,
            file_accesses=file_accesses,
        )

    def _compute_by_turn(
        self,
        turns: list[Turn],
        ground_truth_files: list[str],
    ) -> dict[int, TurnMetrics]:
        """Compute metrics for each turn."""
        result = {}
        cumulative_files: set[str] = set()
        gt_set = set(ground_truth_files)

        for turn in turns:
            cumulative_files.update(turn.files_accessed)
            cumulative_list = list(cumulative_files)

            tools_used = list({tc.get("tool", "unknown") for tc in turn.tool_calls})
            files_hit = len(set(turn.files_accessed) & gt_set)

            result[turn.index] = TurnMetrics(
                turn_index=turn.index,
                file_recall=self.strategies["file_recall"].compute(
                    cumulative_list, ground_truth_files
                ),
                file_precision=self.strategies["file_precision"].compute(
                    cumulative_list, ground_truth_files
                ),
                files_accessed=len(turn.files_accessed),
                files_hit_target=files_hit,
                tools_used=tools_used,
            )

        return result

    def _compute_by_tool(
        self,
        turns: list[Turn],
        ground_truth_files: list[str],
    ) -> dict[str, ToolContribution]:
        """Compute contribution metrics for each tool."""
        tool_files: dict[str, set[str]] = {}
        tool_accesses: dict[str, int] = {}
        gt_set = set(ground_truth_files)

        for turn in turns:
            for tc in turn.tool_calls:
                tool = tc.get("tool", "unknown")
                files = tc.get("files", [])
                if isinstance(files, dict):
                    files = list(files.keys())
                elif not isinstance(files, list):
                    files = []

                tool_files.setdefault(tool, set()).update(files)
                tool_accesses[tool] = tool_accesses.get(tool, 0) + 1

        total_hits = sum(len(files & gt_set) for files in tool_files.values())

        result = {}
        for tool, files in tool_files.items():
            hits = len(files & gt_set)
            result[tool] = ToolContribution(
                tool_name=tool,
                files_found=len(files),
                files_hit_target=hits,
                total_accesses=tool_accesses.get(tool, 0),
                contribution_score=hits / total_hits if total_hits > 0 else 0.0,
            )

        return result

    def _extract_file_accesses(
        self,
        turns: list[Turn],
        ground_truth_files: list[str],
    ) -> list[FileAccessWithMetrics]:
        """Extract file access events with metrics."""
        gt_set = set(ground_truth_files)
        result = []

        for turn in turns:
            for tc in turn.tool_calls:
                tool = tc.get("tool", "unknown")
                files = tc.get("files", [])
                if isinstance(files, dict):
                    files = list(files.keys())

                for f in files:
                    result.append(
                        FileAccessWithMetrics(
                            path=f,
                            turn_index=turn.index,
                            tool_name=tool,
                            access_type="search",
                            is_target_hit=f in gt_set,
                        )
                    )

        return result

    def _compute_aggregate(
        self,
        turns: list[Turn],
        ground_truth_files: list[str],
        ground_truth_functions: list[dict[str, Any]] | None = None,
    ) -> AggregateMetrics:
        """Compute aggregate metrics across all turns."""
        all_files: set[str] = set()
        for turn in turns:
            all_files.update(turn.files_accessed)

        all_files_list = list(all_files)

        functions_hit = 0
        functions_total = len(ground_truth_functions or [])
        if ground_truth_functions:
            for func in ground_truth_functions:
                if func.get("path") in all_files:
                    functions_hit += 1

        return AggregateMetrics(
            file_recall=self.strategies["file_recall"].compute(all_files_list, ground_truth_files),
            file_precision=self.strategies["file_precision"].compute(
                all_files_list, ground_truth_files
            ),
            total_turns=len(turns),
            total_files_accessed=len(all_files),
            functions_hit=functions_hit,
            functions_total=functions_total,
            function_hit_rate=functions_hit / functions_total if functions_total > 0 else 0.0,
        )
