"""SQLite-backed index for benchmark experiments."""

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import ExperimentState
from .store import ExperimentFilters, ExperimentStore


@dataclass
class IndexedExperiment:
    experiment_id: str
    kind: str
    name: str
    status: str
    dataset_name: str
    case_count: int
    created_at: str
    completion_rate: float
    avg_file_recall: float
    avg_file_precision: float
    manifest_json: str
    state_json: str
    summary_json: str
    indexed_at: datetime


@dataclass
class IndexedCase:
    experiment_id: str
    case_id: str
    repo: str
    completed: bool
    partial: bool
    file_recall: float
    file_precision: float
    line_coverage: float
    function_hit_rate: float
    turns_used: int
    latency_s: float
    result_json: str


class ExperimentIndex:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS experiments (
                experiment_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                dataset_name TEXT NOT NULL,
                case_count INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                completion_rate REAL NOT NULL,
                avg_file_recall REAL NOT NULL,
                avg_file_precision REAL NOT NULL,
                manifest_json TEXT NOT NULL,
                state_json TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                indexed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cases (
                experiment_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                repo TEXT NOT NULL,
                completed INTEGER NOT NULL,
                partial INTEGER NOT NULL,
                file_recall REAL NOT NULL,
                file_precision REAL NOT NULL,
                line_coverage REAL NOT NULL,
                function_hit_rate REAL NOT NULL,
                turns_used INTEGER NOT NULL,
                latency_s REAL NOT NULL,
                result_json TEXT NOT NULL,
                PRIMARY KEY (experiment_id, case_id)
            );
            CREATE INDEX IF NOT EXISTS idx_experiments_kind_created ON experiments(kind, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_experiments_status_created ON experiments(status, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_cases_experiment ON cases(experiment_id);
            """
        )
        self._conn.commit()

    def rebuild(self, store: ExperimentStore, filters: ExperimentFilters | None = None) -> int:
        rows_written = 0
        with self._lock:
            self._conn.execute("DELETE FROM cases")
            self._conn.execute("DELETE FROM experiments")
            for manifest, state in store.list(filters=filters):
                summary = store.get_summary(manifest.experiment_id) or {}
                stats = summary.get("stats", {}) if isinstance(summary, dict) else {}
                state_model = state or ExperimentState(
                    status="pending",
                    total_cases=int(manifest.dataset.get("case_count", 0)),
                    completed_cases=0,
                    failed_cases=0,
                )
                indexed = IndexedExperiment(
                    experiment_id=manifest.experiment_id,
                    kind=manifest.kind,
                    name=manifest.name,
                    status=state_model.status,
                    dataset_name=str(manifest.dataset.get("name", "unknown")),
                    case_count=state_model.total_cases,
                    created_at=manifest.created_at.isoformat(),
                    completion_rate=float(stats.get("completion_rate", 0.0)),
                    avg_file_recall=float(stats.get("avg_file_recall", 0.0)),
                    avg_file_precision=float(stats.get("avg_file_precision", 0.0)),
                    manifest_json=json.dumps(manifest.to_dict(), ensure_ascii=False),
                    state_json=json.dumps(state_model.to_dict(), ensure_ascii=False),
                    summary_json=json.dumps(summary, ensure_ascii=False),
                    indexed_at=datetime.now(UTC),
                )
                self._conn.execute(
                    """
                    INSERT INTO experiments (
                        experiment_id, kind, name, status, dataset_name, case_count,
                        created_at, completion_rate, avg_file_recall, avg_file_precision,
                        manifest_json, state_json, summary_json, indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        indexed.experiment_id,
                        indexed.kind,
                        indexed.name,
                        indexed.status,
                        indexed.dataset_name,
                        indexed.case_count,
                        indexed.created_at,
                        indexed.completion_rate,
                        indexed.avg_file_recall,
                        indexed.avg_file_precision,
                        indexed.manifest_json,
                        indexed.state_json,
                        indexed.summary_json,
                        indexed.indexed_at.isoformat(),
                    ),
                )
                for result in store.load_results(manifest.experiment_id):
                    self._conn.execute(
                        """
                        INSERT INTO cases (
                            experiment_id, case_id, repo, completed, partial,
                            file_recall, file_precision, line_coverage, function_hit_rate,
                            turns_used, latency_s, result_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            manifest.experiment_id,
                            result.case_id,
                            result.repo,
                            1 if result.completed else 0,
                            1 if result.partial else 0,
                            result.file_recall,
                            result.file_precision,
                            result.line_coverage,
                            result.function_hit_rate,
                            result.turns_used,
                            result.latency_s,
                            json.dumps(result.to_dict(), ensure_ascii=False),
                        ),
                    )
                rows_written += 1
            self._conn.commit()
        return rows_written

    def list_experiments(
        self,
        *,
        kinds: list[str] | None = None,
        status: str | None = None,
        dataset: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IndexedExperiment]:
        query = "SELECT * FROM experiments WHERE 1=1"
        params: list[Any] = []
        if kinds:
            query += f" AND kind IN ({','.join('?' for _ in kinds)})"
            params.extend(kinds)
        if status:
            query += " AND status = ?"
            params.append(status)
        if dataset:
            query += " AND dataset_name = ?"
            params.append(dataset)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_experiment(row) for row in rows]

    def count_experiments(
        self,
        *,
        kinds: list[str] | None = None,
        status: str | None = None,
        dataset: str | None = None,
    ) -> int:
        query = "SELECT COUNT(*) AS total FROM experiments WHERE 1=1"
        params: list[Any] = []
        if kinds:
            query += f" AND kind IN ({','.join('?' for _ in kinds)})"
            params.extend(kinds)
        if status:
            query += " AND status = ?"
            params.append(status)
        if dataset:
            query += " AND dataset_name = ?"
            params.append(dataset)
        row = self._conn.execute(query, params).fetchone()
        return int(row["total"]) if row else 0

    def get_experiment(self, experiment_id: str) -> IndexedExperiment | None:
        row = self._conn.execute(
            "SELECT * FROM experiments WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()
        return self._row_to_experiment(row) if row else None

    def list_cases(
        self,
        experiment_id: str,
        *,
        completed: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IndexedCase]:
        query = "SELECT * FROM cases WHERE experiment_id = ?"
        params: list[Any] = [experiment_id]
        if completed is not None:
            query += " AND completed = ?"
            params.append(1 if completed else 0)
        query += " ORDER BY case_id ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_case(row) for row in rows]

    def count_cases(self, experiment_id: str, *, completed: bool | None = None) -> int:
        query = "SELECT COUNT(*) AS total FROM cases WHERE experiment_id = ?"
        params: list[Any] = [experiment_id]
        if completed is not None:
            query += " AND completed = ?"
            params.append(1 if completed else 0)
        row = self._conn.execute(query, params).fetchone()
        return int(row["total"]) if row else 0

    def get_case(self, experiment_id: str, case_id: str) -> IndexedCase | None:
        row = self._conn.execute(
            "SELECT * FROM cases WHERE experiment_id = ? AND case_id = ?",
            (experiment_id, case_id),
        ).fetchone()
        return self._row_to_case(row) if row else None

    def invalidate(self, experiment_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM cases WHERE experiment_id = ?", (experiment_id,))
            self._conn.execute("DELETE FROM experiments WHERE experiment_id = ?", (experiment_id,))
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _row_to_experiment(self, row: sqlite3.Row) -> IndexedExperiment:
        return IndexedExperiment(
            experiment_id=row["experiment_id"],
            kind=row["kind"],
            name=row["name"],
            status=row["status"],
            dataset_name=row["dataset_name"],
            case_count=row["case_count"],
            created_at=row["created_at"],
            completion_rate=row["completion_rate"],
            avg_file_recall=row["avg_file_recall"],
            avg_file_precision=row["avg_file_precision"],
            manifest_json=row["manifest_json"],
            state_json=row["state_json"],
            summary_json=row["summary_json"],
            indexed_at=datetime.fromisoformat(row["indexed_at"]),
        )

    def _row_to_case(self, row: sqlite3.Row) -> IndexedCase:
        return IndexedCase(
            experiment_id=row["experiment_id"],
            case_id=row["case_id"],
            repo=row["repo"],
            completed=bool(row["completed"]),
            partial=bool(row["partial"]),
            file_recall=row["file_recall"],
            file_precision=row["file_precision"],
            line_coverage=row["line_coverage"],
            function_hit_rate=row["function_hit_rate"],
            turns_used=row["turns_used"],
            latency_s=row["latency_s"],
            result_json=row["result_json"],
        )


CachedExperiment = IndexedExperiment
ExperimentCache = ExperimentIndex
