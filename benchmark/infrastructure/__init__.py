"""Infrastructure layer for benchmark architecture.

Contains I/O, caching, and external service adapters.
Implements repository pattern for data persistence.

Modules:
    cache: ExperimentCache with SQLite + LRU memory cache
"""

from benchmark.infrastructure.cache import CachedExperiment, ExperimentCache

__all__ = [
    "CachedExperiment",
    "ExperimentCache",
]
