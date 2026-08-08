"""Tests for skillsbank.perf — caching, eager loading, benchmarking."""

from __future__ import annotations

import time

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from skillsbank.db.base import Base
from skillsbank.db.persistence_models import (
    CapabilityRow,
    SkillRow,
    TagRow,
    VersionRow,
)
from skillsbank.perf import (
    BenchmarkResult,
    BenchmarkSuite,
    LRUCache,
    apply_performance_pragmas,
    benchmark,
    cache_key,
    cached,
    check_missing_indexes,
    explain_query,
    get_optimized_engine,
    get_skill_with_version,
    get_versions_with_details,
    run_default_benchmarks,
)


@pytest.fixture
def cache():
    return LRUCache(max_size=10, ttl_seconds=1.0)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Seed data
    skill = SkillRow(id="s1", name="test-skill", canonical_key="test-skill", lifecycle="active")
    session.add(skill)
    session.flush()

    v = VersionRow(
        skill_id="s1",
        version_id="v1",
        name="test-skill",
        summary="A test skill",
        domain_primary="security",
        source_repo="test/repo",
    )
    session.add(v)
    session.flush()

    session.add(CapabilityRow(version_id_fk=v.id, name="pentest", canonical="pentest"))
    session.add(TagRow(version_id_fk=v.id, name="security"))
    session.commit()

    yield session
    session.close()
    engine.dispose()


# ── LRU Cache ────────────────────────────────────────────────────────


class TestLRUCache:
    def test_put_get(self, cache: LRUCache):
        cache.put("k1", "v1")
        found, val = cache.get("k1")
        assert found is True
        assert val == "v1"

    def test_miss(self, cache: LRUCache):
        found, val = cache.get("nonexistent")
        assert found is False
        assert val is None

    def test_ttl_expiry(self, cache: LRUCache):
        cache.put("k1", "v1")
        time.sleep(1.1)
        found, _ = cache.get("k1")
        assert found is False

    def test_eviction(self, cache: LRUCache):
        for i in range(15):
            cache.put(f"k{i}", f"v{i}")
        assert cache.stats["size"] <= 10

    def test_invalidate_prefix(self, cache: LRUCache):
        cache.put("search:1", "a")
        cache.put("search:2", "b")
        cache.put("other:1", "c")
        removed = cache.invalidate("search:")
        assert removed == 2
        found, _ = cache.get("other:1")
        assert found is True

    def test_invalidate_all(self, cache: LRUCache):
        cache.put("k1", "v1")
        cache.put("k2", "v2")
        removed = cache.invalidate()
        assert removed == 2
        assert cache.stats["size"] == 0

    def test_stats(self, cache: LRUCache):
        cache.put("k1", "v1")
        cache.get("k1")
        cache.get("missing")
        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5


class TestCacheKey:
    def test_deterministic(self):
        assert cache_key("a", "b", x=1) == cache_key("a", "b", x=1)

    def test_different_args(self):
        assert cache_key("a") != cache_key("b")

    def test_kwargs_order(self):
        assert cache_key(x=1, y=2) == cache_key(y=2, x=1)


class TestCachedDecorator:
    def test_caches_result(self):
        call_count = 0

        @cached("test")
        def expensive(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = expensive(5)
        result2 = expensive(5)
        assert result1 == 10
        assert result2 == 10
        assert call_count == 1  # second call used cache


# ── Eager Loading ────────────────────────────────────────────────────


class TestEagerLoading:
    def test_get_skill_with_version(self, db_session: Session):
        skill = get_skill_with_version(db_session, "s1")
        assert skill is not None
        assert skill.name == "test-skill"
        assert len(skill.versions) == 1
        assert len(skill.versions[0].capabilities) == 1
        assert skill.versions[0].capabilities[0].name == "pentest"

    def test_get_skill_not_found(self, db_session: Session):
        assert get_skill_with_version(db_session, "nonexistent") is None

    def test_get_versions_with_details(self, db_session: Session):
        versions = get_versions_with_details(db_session, domain="security")
        assert len(versions) == 1
        assert versions[0].domain_primary == "security"
        assert len(versions[0].capabilities) == 1

    def test_get_versions_with_repo_filter(self, db_session: Session):
        versions = get_versions_with_details(db_session, repo="test/repo")
        assert len(versions) == 1

    def test_get_versions_limit(self, db_session: Session):
        versions = get_versions_with_details(db_session, limit=0)
        assert len(versions) == 0


# ── Benchmarking ─────────────────────────────────────────────────────


class TestBenchmark:
    def test_benchmark_runs(self):
        def noop():
            return 42

        result = benchmark("noop", noop, iterations=5)
        assert isinstance(result, BenchmarkResult)
        assert result.iterations == 5
        assert result.avg_ms >= 0

    def test_benchmark_result_to_dict(self):
        def noop():
            return [1, 2, 3]

        result = benchmark("test", noop, iterations=3)
        d = result.to_dict()
        assert d["name"] == "test"
        assert d["iterations"] == 3

    def test_benchmark_suite(self):
        suite = BenchmarkSuite()
        suite.run("noop", lambda: None, iterations=3)
        report = suite.report()
        assert report["total_benchmarks"] == 1
        assert len(report["benchmarks"]) == 1


# ── SQLite Pragmas ───────────────────────────────────────────────────


class TestPragmas:
    def test_apply_performance_pragmas(self, db_session: Session):
        apply_performance_pragmas(db_session)
        # In-memory SQLite uses 'memory' journal mode; file-based uses 'wal'
        mode = db_session.execute(text("PRAGMA journal_mode")).scalar()
        assert mode in ("wal", "memory")


# ── Query Plan Analysis ──────────────────────────────────────────────


class TestQueryPlan:
    def test_explain_query(self, db_session: Session):
        plan = explain_query(db_session, "SELECT * FROM skills WHERE name='test'")
        assert isinstance(plan, list)

    def test_check_missing_indexes(self, db_session: Session):
        recs = check_missing_indexes(db_session)
        assert isinstance(recs, list)


# ── Optimized Engine ─────────────────────────────────────────────────


class TestOptimizedEngine:
    def test_memory_engine(self):
        engine = get_optimized_engine("sqlite:///:memory:")
        assert engine is not None
        with engine.connect() as conn:
            mode = conn.execute(text("PRAGMA journal_mode")).scalar()
            assert mode in ("wal", "memory")
        engine.dispose()


# ── DB Benchmarks (requires populated DB) ────────────────────────────


class TestDBBenchmark:
    def test_run_default_benchmarks(self, db_session: Session):
        suite = run_default_benchmarks(db_session)
        report = suite.report()
        assert report["total_benchmarks"] >= 4
        for b in report["benchmarks"]:
            assert b["avg_ms"] >= 0
