"""Cache infrastructure for experiment data.

Provides SQLite-backed caching with LRU memory layer for fast lookups.
"""

import json
import sqlite3
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class CachedExperiment:
    """Cached experiment summary."""

    experiment_id: str
    name: str
    status: str
    dataset_name: str
    case_count: int
    created_at: str
    file_recall: float
    file_precision: float
    metadata_json: str
    cached_at: datetime


class ExperimentCache:
    """SQLite + LRU memory cache for experiment lookups."""

    def __init__(
        self,
        db_path: Path | None = None,
        max_memory_entries: int = 1000,
    ):
        self.db_path = db_path
        self.max_memory_entries = max_memory_entries
        self._memory_cache: OrderedDict[str, CachedExperiment] = OrderedDict()
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

        if db_path:
            self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database."""
        if not self.db_path:
            return

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                experiment_id TEXT PRIMARY KEY,
                name TEXT,
                status TEXT,
                dataset_name TEXT,
                case_count INTEGER,
                created_at TEXT,
                file_recall REAL,
                file_precision REAL,
                metadata_json TEXT,
                cached_at TEXT
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_experiments_status
            ON experiments(status)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_experiments_dataset
            ON experiments(dataset_name)
        """)
        self._conn.commit()

    def get(self, experiment_id: str) -> CachedExperiment | None:
        """Get cached experiment by ID."""
        with self._lock:
            if experiment_id in self._memory_cache:
                self._memory_cache.move_to_end(experiment_id)
                return self._memory_cache[experiment_id]

        if self._conn:
            cursor = self._conn.execute(
                "SELECT * FROM experiments WHERE experiment_id = ?",
                (experiment_id,),
            )
            row = cursor.fetchone()
            if row:
                cached = self._row_to_cached(row)
                self._add_to_memory(cached)
                return cached

        return None

    def set(self, cached: CachedExperiment) -> None:
        """Cache experiment data."""
        self._add_to_memory(cached)

        if self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO experiments
                (experiment_id, name, status, dataset_name, case_count,
                 created_at, file_recall, file_precision, metadata_json, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cached.experiment_id,
                    cached.name,
                    cached.status,
                    cached.dataset_name,
                    cached.case_count,
                    cached.created_at,
                    cached.file_recall,
                    cached.file_precision,
                    cached.metadata_json,
                    cached.cached_at.isoformat(),
                ),
            )
            self._conn.commit()

    def invalidate(self, experiment_id: str) -> None:
        """Remove experiment from cache."""
        with self._lock:
            self._memory_cache.pop(experiment_id, None)

        if self._conn:
            self._conn.execute(
                "DELETE FROM experiments WHERE experiment_id = ?",
                (experiment_id,),
            )
            self._conn.commit()

    def list_all(
        self,
        status: str | None = None,
        dataset: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CachedExperiment]:
        """List cached experiments with optional filters."""
        if not self._conn:
            with self._lock:
                results = list(self._memory_cache.values())
                if status:
                    results = [r for r in results if r.status == status]
                if dataset:
                    results = [r for r in results if r.dataset_name == dataset]
                results.sort(key=lambda x: x.created_at, reverse=True)
                if offset:
                    results = results[offset:]
                if limit:
                    results = results[:limit]
                return results

        query = "SELECT * FROM experiments WHERE 1=1"
        params: list[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if dataset:
            query += " AND dataset_name = ?"
            params.append(dataset)

        query += " ORDER BY created_at DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)
        if offset:
            query += " OFFSET ?"
            params.append(offset)

        cursor = self._conn.execute(query, params)
        return [self._row_to_cached(row) for row in cursor.fetchall()]

    def refresh_from_source(
        self,
        experiments: list[dict[str, Any]],
    ) -> int:
        """Refresh cache from source data."""
        count = 0
        for exp in experiments:
            metadata = exp.get("metadata", {})
            stats = {
                k: v for k, v in exp.items() if k not in ("metadata", "results", "experiment_name")
            }

            cached = CachedExperiment(
                experiment_id=exp.get("experiment_name", ""),
                name=exp.get("experiment_name", ""),
                status="completed",
                dataset_name=metadata.get("dataset", {})
                .get("dataset_path", "")
                .split("/")[-1]
                .replace(".jsonl", ""),
                case_count=exp.get("total_cases", 0),
                created_at=metadata.get("run", {}).get("started_at_utc", ""),
                file_recall=stats.get("avg_file_recall", 0.0),
                file_precision=stats.get("avg_file_precision", 0.0),
                metadata_json=json.dumps(metadata),
                cached_at=datetime.now(UTC),
            )
            self.set(cached)
            count += 1

        return count

    def _add_to_memory(self, cached: CachedExperiment) -> None:
        """Add to memory cache with LRU eviction."""
        with self._lock:
            if cached.experiment_id in self._memory_cache:
                self._memory_cache.move_to_end(cached.experiment_id)
            else:
                self._memory_cache[cached.experiment_id] = cached
                while len(self._memory_cache) > self.max_memory_entries:
                    self._memory_cache.popitem(last=False)

    def _row_to_cached(self, row: sqlite3.Row) -> CachedExperiment:
        """Convert database row to CachedExperiment."""
        return CachedExperiment(
            experiment_id=row["experiment_id"],
            name=row["name"],
            status=row["status"],
            dataset_name=row["dataset_name"],
            case_count=row["case_count"],
            created_at=row["created_at"],
            file_recall=row["file_recall"],
            file_precision=row["file_precision"],
            metadata_json=row["metadata_json"],
            cached_at=datetime.fromisoformat(row["cached_at"])
            if row["cached_at"]
            else datetime.now(UTC),
        )

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
