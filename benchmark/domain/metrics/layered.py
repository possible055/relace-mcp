"""Layered metrics data models.

Defines hierarchical metric structures for granular performance analysis.
"""

from dataclasses import dataclass, field
from typing import Any, Self


@dataclass
class TurnMetrics:
    """Metrics for a single turn in the search process."""

    turn_index: int
    file_recall: float = 0.0
    file_precision: float = 0.0
    line_coverage: float = 0.0
    files_accessed: int = 0
    files_hit_target: int = 0
    tools_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "file_recall": self.file_recall,
            "file_precision": self.file_precision,
            "line_coverage": self.line_coverage,
            "files_accessed": self.files_accessed,
            "files_hit_target": self.files_hit_target,
            "tools_used": self.tools_used,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            turn_index=data.get("turn_index", 0),
            file_recall=data.get("file_recall", 0.0),
            file_precision=data.get("file_precision", 0.0),
            line_coverage=data.get("line_coverage", 0.0),
            files_accessed=data.get("files_accessed", 0),
            files_hit_target=data.get("files_hit_target", 0),
            tools_used=data.get("tools_used", []),
        )


@dataclass
class ToolContribution:
    """Contribution metrics for a single tool."""

    tool_name: str
    files_found: int = 0
    files_hit_target: int = 0
    total_accesses: int = 0
    contribution_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "files_found": self.files_found,
            "files_hit_target": self.files_hit_target,
            "total_accesses": self.total_accesses,
            "contribution_score": self.contribution_score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            tool_name=data.get("tool_name", ""),
            files_found=data.get("files_found", 0),
            files_hit_target=data.get("files_hit_target", 0),
            total_accesses=data.get("total_accesses", 0),
            contribution_score=data.get("contribution_score", 0.0),
        )


@dataclass
class AggregateMetrics:
    """Aggregated metrics across all turns."""

    file_recall: float = 0.0
    file_precision: float = 0.0
    line_coverage: float = 0.0
    line_precision_matched: float = 0.0
    context_line_coverage: float = 0.0
    function_hit_rate: float = 0.0
    functions_hit: int = 0
    functions_total: int = 0
    total_turns: int = 0
    total_files_accessed: int = 0
    hints_used: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_recall": self.file_recall,
            "file_precision": self.file_precision,
            "line_coverage": self.line_coverage,
            "line_precision_matched": self.line_precision_matched,
            "context_line_coverage": self.context_line_coverage,
            "function_hit_rate": self.function_hit_rate,
            "functions_hit": self.functions_hit,
            "functions_total": self.functions_total,
            "total_turns": self.total_turns,
            "total_files_accessed": self.total_files_accessed,
            "hints_used": self.hints_used,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            file_recall=data.get("file_recall", 0.0),
            file_precision=data.get("file_precision", 0.0),
            line_coverage=data.get("line_coverage", 0.0),
            line_precision_matched=data.get("line_precision_matched", 0.0),
            context_line_coverage=data.get("context_line_coverage", 0.0),
            function_hit_rate=data.get("function_hit_rate", 0.0),
            functions_hit=data.get("functions_hit", 0),
            functions_total=data.get("functions_total", 0),
            total_turns=data.get("total_turns", 0),
            total_files_accessed=data.get("total_files_accessed", 0),
            hints_used=data.get("hints_used", 0),
        )


@dataclass
class FileAccessWithMetrics:
    """File access event with associated metrics."""

    path: str
    turn_index: int
    tool_name: str
    access_type: str
    is_target_hit: bool = False
    ground_truth_function: str | None = None
    line_range: tuple[int, int] | None = None
    contribution_to_recall: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "turn_index": self.turn_index,
            "tool_name": self.tool_name,
            "access_type": self.access_type,
            "is_target_hit": self.is_target_hit,
            "ground_truth_function": self.ground_truth_function,
            "line_range": list(self.line_range) if self.line_range else None,
            "contribution_to_recall": self.contribution_to_recall,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        line_range = data.get("line_range")
        return cls(
            path=data.get("path", ""),
            turn_index=data.get("turn_index", 0),
            tool_name=data.get("tool_name", ""),
            access_type=data.get("access_type", ""),
            is_target_hit=data.get("is_target_hit", False),
            ground_truth_function=data.get("ground_truth_function"),
            line_range=tuple(line_range) if line_range else None,
            contribution_to_recall=data.get("contribution_to_recall", 0.0),
        )


@dataclass
class LayeredMetrics:
    """Hierarchical metrics structure with turn, tool, and aggregate views."""

    by_turn: dict[int, TurnMetrics] = field(default_factory=dict)
    by_tool: dict[str, ToolContribution] = field(default_factory=dict)
    aggregate: AggregateMetrics = field(default_factory=AggregateMetrics)
    file_accesses: list[FileAccessWithMetrics] = field(default_factory=list)

    def get_turn_progression(self) -> list[float]:
        """Get recall progression across turns."""
        return [self.by_turn[i].file_recall for i in sorted(self.by_turn.keys())]

    def get_top_contributing_tools(self, n: int = 3) -> list[ToolContribution]:
        """Get top N tools by contribution score."""
        sorted_tools = sorted(
            self.by_tool.values(),
            key=lambda t: t.contribution_score,
            reverse=True,
        )
        return sorted_tools[:n]

    def explain_low_precision(self, threshold: float = 0.5) -> list[str]:
        """Generate explanations for low precision results."""
        explanations = []

        if self.aggregate.file_precision < threshold:
            false_positives = [fa for fa in self.file_accesses if not fa.is_target_hit]
            if false_positives:
                by_tool = {}
                for fa in false_positives:
                    by_tool.setdefault(fa.tool_name, []).append(fa.path)

                for tool, paths in sorted(by_tool.items(), key=lambda x: len(x[1]), reverse=True):
                    explanations.append(f"{tool} returned {len(paths)} non-target files")

        return explanations

    def explain_low_recall(self, threshold: float = 0.5) -> list[str]:
        """Generate explanations for low recall results."""
        explanations = []

        if self.aggregate.file_recall < threshold:
            if self.aggregate.functions_total > 0:
                miss_rate = 1 - (self.aggregate.functions_hit / self.aggregate.functions_total)
                if miss_rate > 0.3:
                    explanations.append(f"Missed {int(miss_rate * 100)}% of target functions")

            for turn_idx, turn in sorted(self.by_turn.items()):
                if turn.files_accessed > 0 and turn.files_hit_target == 0:
                    explanations.append(
                        f"Turn {turn_idx}: {turn.files_accessed} files accessed, none hit targets"
                    )

        return explanations

    def to_dict(self) -> dict[str, Any]:
        return {
            "by_turn": {str(k): v.to_dict() for k, v in self.by_turn.items()},
            "by_tool": {k: v.to_dict() for k, v in self.by_tool.items()},
            "aggregate": self.aggregate.to_dict(),
            "file_accesses": [fa.to_dict() for fa in self.file_accesses],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        by_turn = {int(k): TurnMetrics.from_dict(v) for k, v in data.get("by_turn", {}).items()}
        by_tool = {k: ToolContribution.from_dict(v) for k, v in data.get("by_tool", {}).items()}
        return cls(
            by_turn=by_turn,
            by_tool=by_tool,
            aggregate=AggregateMetrics.from_dict(data.get("aggregate", {})),
            file_accesses=[
                FileAccessWithMetrics.from_dict(fa) for fa in data.get("file_accesses", [])
            ],
        )
