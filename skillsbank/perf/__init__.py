"""Performance optimization: caching, query tuning, benchmarking."""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from threading import Lock
from typing import Any, TypeVar

from sqlalchemy import event, text
from sqlalchemy.orm import Session, joinedload, selectinload

from skillsbank.db.persistence_models import (
    CapabilityRow,
    RepoRow,
    SkillRow,
    TagRow,
    VersionRow,
)

F = TypeVar("F", bound=Callable[..., Any])


# ── LRU Cache ────────────────────────────────────────────────────────


class LRUCache:
    """Thread-safe LRU cache with TTL support."""

    def __init__(self, max_size: int = 256, ttl_seconds: float = 300.0):
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> tuple[bool, Any]:
        with self._lock:
            if key in self._cache:
                value, ts = self._cache[key]
                if time.time() - ts < self._ttl:
                    self._cache.move_to_end(key)
                    self._hits += 1
                    return True, value
                else:
                    del self._cache[key]
            self._misses += 1
            return False, None

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (value, time.time())
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def invalidate(self, prefix: str | None = None) -> int:
        with self._lock:
            if prefix is None:
                count = len(self._cache)
                self._cache.clear()
                return count
            keys = [k for k in self._cache if k.startswith(prefix)]
            for k in keys:
                del self._cache[k]
            return len(keys)

    @property
    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "ttl_seconds": self._ttl,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / total if total > 0 else 0.0,
            }


_global_cache = LRUCache(max_size=512, ttl_seconds=300.0)


def get_cache() -> LRUCache:
    return _global_cache


def cache_key(*args: Any, **kwargs: Any) -> str:
    """Build a deterministic cache key from arguments."""
    parts = [str(a) for a in args]
    parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
    raw = "|".join(parts)
    return hashlib.md5(raw.encode()).hexdigest()


def cached(prefix: str, ttl: float | None = None) -> Callable[[F], F]:
    """Decorator to cache function results in the global LRU cache."""

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = f"{prefix}:{cache_key(*args, **kwargs)}"
            found, value = _global_cache.get(key)
            if found:
                return value
            result = func(*args, **kwargs)
            _global_cache.put(key, result)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


# ── Eager-Loading Queries ────────────────────────────────────────────


def get_skill_with_version(session: Session, skill_id: str) -> SkillRow | None:
    """Load skill + current version (with caps/tags) in a single query."""
    return (
        session.query(SkillRow)
        .options(
            selectinload(SkillRow.versions).selectinload(VersionRow.capabilities),
            selectinload(SkillRow.versions).selectinload(VersionRow.tags),
        )
        .filter(SkillRow.id == skill_id)
        .first()
    )


def get_versions_with_details(
    session: Session,
    domain: str | None = None,
    repo: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[VersionRow]:
    """Load versions with eager caps/tags, avoiding N+1."""
    q = session.query(VersionRow).options(
        selectinload(VersionRow.capabilities),
        selectinload(VersionRow.tags),
    )
    if domain:
        q = q.filter(VersionRow.domain_primary == domain)
    if repo:
        q = q.filter(VersionRow.source_repo == repo)
    return q.offset(offset).limit(limit).all()


def get_repo_with_snapshots(session: Session, repo_id: str) -> RepoRow | None:
    """Load repo + snapshots in one query."""
    return session.query(RepoRow).options(selectinload(RepoRow.snapshots)).filter(RepoRow.id == repo_id).first()


# ── Bulk Operations ──────────────────────────────────────────────────


def bulk_insert_versions(session: Session, rows: list[dict[str, Any]]) -> int:
    """Bulk insert version rows using core insert for speed."""
    if not rows:
        return 0
    from sqlalchemy import insert

    stmt = insert(VersionRow.__table__)
    session.execute(stmt, rows)
    session.flush()
    return len(rows)


def bulk_insert_capabilities(session: Session, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    from sqlalchemy import insert

    stmt = insert(CapabilityRow.__table__)
    session.execute(stmt, rows)
    session.flush()
    return len(rows)


def bulk_insert_tags(session: Session, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    from sqlalchemy import insert

    stmt = insert(TagRow.__table__)
    session.execute(stmt, rows)
    session.flush()
    return len(rows)


# ── SQLite Pragmas ───────────────────────────────────────────────────


def apply_performance_pragmas(session: Session) -> None:
    """Apply SQLite performance pragmas."""
    pragmas = [
        "PRAGMA journal_mode=WAL",
        "PRAGMA synchronous=NORMAL",
        "PRAGMA cache_size=-64000",  # 64MB
        "PRAGMA temp_store=MEMORY",
        "PRAGMA mmap_size=268435456",  # 256MB
        "PRAGMA optimize",
    ]
    for pragma in pragmas:
        session.execute(text(pragma))


def analyze_tables(session: Session) -> None:
    """Run ANALYZE to update query planner statistics."""
    session.execute(text("ANALYZE"))
    session.commit()


# ── Benchmarking ─────────────────────────────────────────────────────


@dataclass
class BenchmarkResult:
    name: str
    duration_ms: float
    iterations: int
    avg_ms: float
    min_ms: float
    max_ms: float
    p50_ms: float
    p95_ms: float
    rows_processed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "duration_ms": round(self.duration_ms, 2),
            "iterations": self.iterations,
            "avg_ms": round(self.avg_ms, 3),
            "min_ms": round(self.min_ms, 3),
            "max_ms": round(self.max_ms, 3),
            "p50_ms": round(self.p50_ms, 3),
            "p95_ms": round(self.p95_ms, 3),
            "rows_processed": self.rows_processed,
        }


def benchmark(
    name: str,
    func: Callable[..., Any],
    iterations: int = 10,
    *args: Any,
    **kwargs: Any,
) -> BenchmarkResult:
    """Run a function multiple times and collect timing stats."""
    times: list[float] = []
    rows = 0
    for _ in range(iterations):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
        if hasattr(result, "__len__"):
            rows = len(result)
    times.sort()
    total = sum(times)
    return BenchmarkResult(
        name=name,
        duration_ms=total,
        iterations=iterations,
        avg_ms=total / iterations,
        min_ms=times[0],
        max_ms=times[-1],
        p50_ms=times[len(times) // 2],
        p95_ms=times[int(len(times) * 0.95)],
        rows_processed=rows,
    )


@dataclass
class BenchmarkSuite:
    results: list[BenchmarkResult] = field(default_factory=list)

    def run(self, name: str, func: Callable, iterations: int = 10, **kwargs: Any) -> BenchmarkResult:
        result = benchmark(name, func, iterations, **kwargs)
        self.results.append(result)
        return result

    def report(self) -> dict[str, Any]:
        return {
            "benchmarks": [r.to_dict() for r in self.results],
            "total_benchmarks": len(self.results),
        }


def run_default_benchmarks(session: Session) -> BenchmarkSuite:
    """Run standard performance benchmarks against the DB."""
    suite = BenchmarkSuite()

    from skillsbank.db.persistence_models import SkillRow, VersionRow

    def q_all_skills():
        return session.query(SkillRow).all()

    def q_versions_with_domain():
        return session.query(VersionRow).filter(VersionRow.domain_primary == "security").all()

    def q_capabilities_join():
        return session.query(VersionRow).options(selectinload(VersionRow.capabilities)).limit(100).all()

    def q_tags_join():
        return session.query(VersionRow).options(selectinload(VersionRow.tags)).limit(100).all()

    def q_count():
        return session.query(SkillRow).count()

    suite.run("select_all_skills", q_all_skills)
    suite.run("select_versions_by_domain", q_versions_with_domain)
    suite.run("versions_with_capabilities", q_capabilities_join, iterations=20)
    suite.run("versions_with_tags", q_tags_join, iterations=20)
    suite.run("count_skills", q_count, iterations=50)

    return suite


# ── Query Plan Analysis ──────────────────────────────────────────────


def explain_query(session: Session, sql: str) -> list[dict[str, Any]]:
    """Get EXPLAIN QUERY PLAN for a SQL statement."""
    rows = session.execute(text(f"EXPLAIN QUERY PLAN {sql}")).fetchall()
    return [{"id": r[0], "parent": r[1], "detail": r[3]} for r in rows]


def check_missing_indexes(session: Session) -> list[dict[str, Any]]:
    """Identify queries that might benefit from additional indexes."""
    recommendations = []

    # Check if FTS tables exist and are populated
    fts_tables = session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'fts_%'")
    ).fetchall()
    if not fts_tables:
        recommendations.append(
            {
                "issue": "FTS tables missing",
                "recommendation": "Run 'skillsbank rebuild-fts' to create full-text search index",
                "severity": "high",
            }
        )

    # Check for large tables without covering indexes
    version_count = session.execute(text("SELECT COUNT(*) FROM versions")).scalar()
    if version_count and version_count > 500:
        # Check composite query patterns
        plan = explain_query(
            session,
            "SELECT * FROM versions WHERE domain_primary='security' AND source_repo='anthropics/skills'",
        )
        for p in plan:
            if "SCAN" in p.get("detail", ""):
                recommendations.append(
                    {
                        "issue": f"Full table scan on versions: {p['detail']}",
                        "recommendation": "Consider adding composite index on (domain_primary, source_repo)",
                        "severity": "medium",
                    }
                )

    # Check for missing indexes on FK columns
    existing_indexes = set()
    for row in session.execute(text("SELECT name, tbl_name FROM sqlite_master WHERE type='index'")).fetchall():
        existing_indexes.add((row[1], row[0]))

    return recommendations


# ── Connection Pool Tuning ───────────────────────────────────────────


def get_optimized_engine(url: str = "sqlite:///skillsbank.db"):
    """Create engine with optimized connection pool settings."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    if url == "sqlite:///:memory:" or url == "sqlite:///":
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=3600,
        )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA mmap_size=268435456")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine
