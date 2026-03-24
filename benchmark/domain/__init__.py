"""Domain layer for benchmark architecture.

This module contains the core domain models and business logic,
following Clean Architecture principles. Domain objects are pure
Python with no I/O dependencies.

Modules:
    experiment: ExperimentMetadata, EnvironmentInfo, DatasetInfo
    checkpoint: Checkpoint, CheckpointManager protocol
    metrics/: LayeredMetrics, MetricsEngine
    tools/: ToolRegistry, ToolDefinition
"""

from benchmark.domain.checkpoint import (
    Checkpoint,
    CheckpointManager,
    CheckpointRepository,
    FileCheckpointRepository,
)
from benchmark.domain.experiment import (
    DatasetInfo,
    EnvironmentInfo,
    ExperimentMetadata,
    ExperimentStatus,
    SamplingConfig,
    SearchConfig,
)
from benchmark.domain.metrics import (
    AggregateMetrics,
    LayeredMetrics,
    MetricsEngine,
    ToolContribution,
    TurnMetrics,
)
from benchmark.domain.tools import (
    ToolCategory,
    ToolDefinition,
    ToolRegistry,
)

__all__ = [
    "AggregateMetrics",
    "Checkpoint",
    "CheckpointManager",
    "CheckpointRepository",
    "DatasetInfo",
    "EnvironmentInfo",
    "ExperimentMetadata",
    "ExperimentStatus",
    "FileCheckpointRepository",
    "LayeredMetrics",
    "MetricsEngine",
    "SamplingConfig",
    "SearchConfig",
    "ToolCategory",
    "ToolContribution",
    "ToolDefinition",
    "ToolRegistry",
    "TurnMetrics",
]
