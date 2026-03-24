"""Tests for ExperimentCache."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from benchmark.infrastructure.cache import CachedExperiment, ExperimentCache


class TestCachedExperiment:
    @pytest.fixture
    def sample_cached(self) -> CachedExperiment:
        return CachedExperiment(
            experiment_id="exp_001",
            name="Test Experiment",
            status="completed",
            dataset_name="locbench",
            case_count=50,
            created_at="2026-01-01T00:00:00Z",
            file_recall=0.85,
            file_precision=0.75,
            metadata_json="{}",
            cached_at=datetime.now(UTC),
        )

    def test_fields(self, sample_cached: CachedExperiment):
        assert sample_cached.experiment_id == "exp_001"
        assert sample_cached.file_recall == 0.85


class TestExperimentCacheMemoryOnly:
    @pytest.fixture
    def cache(self) -> ExperimentCache:
        return ExperimentCache(db_path=None, max_memory_entries=10)

    def test_set_and_get(self, cache: ExperimentCache):
        cached = CachedExperiment(
            experiment_id="exp_001",
            name="Test",
            status="completed",
            dataset_name="test",
            case_count=10,
            created_at="2026-01-01",
            file_recall=0.8,
            file_precision=0.7,
            metadata_json="{}",
            cached_at=datetime.now(UTC),
        )
        cache.set(cached)

        result = cache.get("exp_001")
        assert result is not None
        assert result.experiment_id == "exp_001"

    def test_get_nonexistent(self, cache: ExperimentCache):
        result = cache.get("nonexistent")
        assert result is None

    def test_invalidate(self, cache: ExperimentCache):
        cached = CachedExperiment(
            experiment_id="exp_002",
            name="Test",
            status="completed",
            dataset_name="test",
            case_count=10,
            created_at="2026-01-01",
            file_recall=0.8,
            file_precision=0.7,
            metadata_json="{}",
            cached_at=datetime.now(UTC),
        )
        cache.set(cached)
        assert cache.get("exp_002") is not None

        cache.invalidate("exp_002")
        assert cache.get("exp_002") is None

    def test_lru_eviction(self):
        cache = ExperimentCache(db_path=None, max_memory_entries=2)

        for i in range(3):
            cached = CachedExperiment(
                experiment_id=f"exp_{i:03d}",
                name=f"Test {i}",
                status="completed",
                dataset_name="test",
                case_count=10,
                created_at="2026-01-01",
                file_recall=0.8,
                file_precision=0.7,
                metadata_json="{}",
                cached_at=datetime.now(UTC),
            )
            cache.set(cached)

        assert cache.get("exp_000") is None
        assert cache.get("exp_001") is not None
        assert cache.get("exp_002") is not None

    def test_list_all(self, cache: ExperimentCache):
        for i in range(3):
            cached = CachedExperiment(
                experiment_id=f"exp_{i:03d}",
                name=f"Test {i}",
                status="completed" if i < 2 else "failed",
                dataset_name="test",
                case_count=10,
                created_at=f"2026-01-0{i + 1}",
                file_recall=0.8,
                file_precision=0.7,
                metadata_json="{}",
                cached_at=datetime.now(UTC),
            )
            cache.set(cached)

        all_items = cache.list_all()
        assert len(all_items) == 3

        completed = cache.list_all(status="completed")
        assert len(completed) == 2


class TestExperimentCacheWithSQLite:
    @pytest.fixture
    def cache(self, tmp_path: Path) -> ExperimentCache:
        db_path = tmp_path / "cache.db"
        return ExperimentCache(db_path=db_path)

    def test_set_and_get_persisted(self, cache: ExperimentCache):
        cached = CachedExperiment(
            experiment_id="exp_001",
            name="Test",
            status="completed",
            dataset_name="test",
            case_count=10,
            created_at="2026-01-01",
            file_recall=0.8,
            file_precision=0.7,
            metadata_json='{"key": "value"}',
            cached_at=datetime.now(UTC),
        )
        cache.set(cached)
        cache._memory_cache.clear()

        result = cache.get("exp_001")
        assert result is not None
        assert result.experiment_id == "exp_001"
        assert result.metadata_json == '{"key": "value"}'

    def test_list_with_filters(self, cache: ExperimentCache):
        for i, ds in enumerate(["locbench", "locbench", "other"]):
            cached = CachedExperiment(
                experiment_id=f"exp_{i:03d}",
                name=f"Test {i}",
                status="completed",
                dataset_name=ds,
                case_count=10,
                created_at=f"2026-01-0{i + 1}",
                file_recall=0.8,
                file_precision=0.7,
                metadata_json="{}",
                cached_at=datetime.now(UTC),
            )
            cache.set(cached)

        locbench_items = cache.list_all(dataset="locbench")
        assert len(locbench_items) == 2

    def test_list_with_pagination(self, cache: ExperimentCache):
        for i in range(5):
            cached = CachedExperiment(
                experiment_id=f"exp_{i:03d}",
                name=f"Test {i}",
                status="completed",
                dataset_name="test",
                case_count=10,
                created_at=f"2026-01-0{i + 1}",
                file_recall=0.8,
                file_precision=0.7,
                metadata_json="{}",
                cached_at=datetime.now(UTC),
            )
            cache.set(cached)

        page1 = cache.list_all(limit=2, offset=0)
        assert len(page1) == 2

        page2 = cache.list_all(limit=2, offset=2)
        assert len(page2) == 2

        page3 = cache.list_all(limit=2, offset=4)
        assert len(page3) == 1
