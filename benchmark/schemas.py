from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class SolvabilityInfo:
    """LLM-evaluated solvability metadata."""

    solvable: bool
    confidence: float
    evidence: list[str] = field(default_factory=list)
    reject_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "solvable": self.solvable,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "reject_reason": self.reject_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SolvabilityInfo":
        return cls(
            solvable=bool(data.get("solvable", False)),
            confidence=float(data.get("confidence", 0.0)),
            evidence=list(data.get("evidence", [])),
            reject_reason=data.get("reject_reason"),
        )


@dataclass
class GroundTruthEntry:
    """A single ground truth function location."""

    path: str
    function: str
    range: tuple[int, int]
    target_ranges: list[tuple[int, int]] = field(default_factory=list)
    class_name: str | None = None
    signature: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "path": self.path,
            "function": self.function,
            "range": list(self.range),
        }
        if self.target_ranges:
            d["target_ranges"] = [list(r) for r in self.target_ranges]
        if self.class_name:
            d["class"] = self.class_name
        if self.signature:
            d["signature"] = self.signature
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GroundTruthEntry":
        range_data = data.get("range", [0, 0])
        target_ranges_data = data.get("target_ranges", [])
        target_ranges: list[tuple[int, int]] = []
        if isinstance(target_ranges_data, list):
            for r in target_ranges_data:
                if (
                    isinstance(r, (list, tuple))
                    and len(r) >= 2
                    and isinstance(r[0], int)
                    and isinstance(r[1], int)
                ):
                    target_ranges.append((r[0], r[1]))
        return cls(
            path=data.get("path", ""),
            function=data.get("function", ""),
            range=(range_data[0], range_data[1]) if len(range_data) >= 2 else (0, 0),
            target_ranges=target_ranges,
            class_name=data.get("class"),
            signature=data.get("signature"),
        )


@dataclass
class ContextEntry:
    """A soft context function (related but not directly modified)."""

    path: str
    function: str
    range: tuple[int, int]
    signature: str | None = None
    relevance_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "path": self.path,
            "function": self.function,
            "range": list(self.range),
        }
        if self.signature:
            d["signature"] = self.signature
        if self.relevance_score is not None:
            d["relevance_score"] = self.relevance_score
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextEntry":
        range_data = data.get("range", [0, 0])
        return cls(
            path=data.get("path", ""),
            function=data.get("function", ""),
            range=(range_data[0], range_data[1]) if len(range_data) >= 2 else (0, 0),
            signature=data.get("signature"),
            relevance_score=data.get("relevance_score"),
        )


@dataclass
class DatasetCase:
    """Unified benchmark case format.

    This is the canonical representation used throughout the pipeline.
    All dataset loaders should produce this type.
    """

    id: str
    query: str
    repo: str
    base_commit: str
    hard_gt: list[GroundTruthEntry] = field(default_factory=list)
    soft_context: list[ContextEntry] = field(default_factory=list)
    solvability: SolvabilityInfo | None = None
    issue_url: str | None = None
    pr_url: str | None = None

    @property
    def ground_truth_files(self) -> dict[str, list[tuple[int, int]]]:
        """Convert hard_gt to file -> target ranges format for metrics.

        Uses `target_ranges` when present; falls back to the full `range`.
        """
        files: dict[str, list[tuple[int, int]]] = {}
        for gt in self.hard_gt:
            if gt.path not in files:
                files[gt.path] = []
            ranges = gt.target_ranges if gt.target_ranges else [gt.range]
            files[gt.path].extend(ranges)
        return files

    @property
    def ground_truth_context_files(self) -> dict[str, list[tuple[int, int]]]:
        """Convert hard_gt to file -> context ranges (full function scopes)."""
        files: dict[str, list[tuple[int, int]]] = {}
        for gt in self.hard_gt:
            files.setdefault(gt.path, []).append(gt.range)
        return files

    @property
    def ground_truth_functions(self) -> list[dict[str, Any]]:
        """Return function targets for function-level metrics."""
        return [
            {
                "path": gt.path,
                "name": gt.function,
                "container": gt.class_name,
                "start_line": gt.range[0],
                "ranges": [gt.range],
            }
            for gt in self.hard_gt
        ]

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "query": self.query,
            "repo": self.repo,
            "base_commit": self.base_commit,
            "hard_gt": [gt.to_dict() for gt in self.hard_gt],
            "soft_context": [ctx.to_dict() for ctx in self.soft_context],
        }
        if self.solvability:
            d["solvability"] = self.solvability.to_dict()
        if self.issue_url:
            d["issue_url"] = self.issue_url
        if self.pr_url:
            d["pr_url"] = self.pr_url
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatasetCase":
        solvability = None
        if "solvability" in data and data["solvability"]:
            solvability = SolvabilityInfo.from_dict(data["solvability"])

        return cls(
            id=data.get("id", ""),
            query=data.get("query", ""),
            repo=data.get("repo", ""),
            base_commit=data.get("base_commit", ""),
            hard_gt=[GroundTruthEntry.from_dict(gt) for gt in data.get("hard_gt", [])],
            soft_context=[ContextEntry.from_dict(ctx) for ctx in data.get("soft_context", [])],
            solvability=solvability,
            issue_url=data.get("issue_url"),
            pr_url=data.get("pr_url"),
        )


def generate_output_filename(
    command: str,
    dataset_name: str,
    timestamp: datetime | None = None,
) -> str:
    """Generate standardized output filename.

    Format: {command}_{dataset}_{timestamp}

    Args:
        command: CLI command name (e.g., 'run', 'filter')
        dataset_name: Dataset identifier (e.g., 'filtered_v1')
        timestamp: Optional timestamp, defaults to now

    Returns:
        Filename without extension (extension added by caller)
    """
    ts = timestamp or datetime.now()
    ts_str = ts.strftime("%Y%m%d_%H%M%S")
    return f"{command}_{dataset_name}_{ts_str}"


def generate_output_path(
    base_dir: Path,
    command: str,
    dataset_name: str,
    timestamp: datetime | None = None,
) -> Path:
    """Generate standardized output path.

    Args:
        base_dir: Base directory for output
        command: CLI command name
        dataset_name: Dataset identifier
        timestamp: Optional timestamp

    Returns:
        Full path without extension
    """
    filename = generate_output_filename(command, dataset_name, timestamp)
    return base_dir / filename
