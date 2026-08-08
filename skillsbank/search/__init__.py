"""FTS5 full-text search engine for SkillsBank.

Provides:
- FTS5 virtual tables for skills, capabilities, tags
- BM25 ranking with configurable column weights
- Faceted filtering (domain, category, agent, quality, security)
- Boolean queries (AND, OR, NOT, prefix)
- Index sync from SQLite tables
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SearchFilters:
    """Faceted filters applied to search results."""

    domain: str | None = None
    category: str | None = None
    agent: str | None = None
    min_quality: float | None = None
    max_risk: str | None = None  # LOW, MEDIUM, HIGH, CRITICAL
    repo: str | None = None
    lifecycle: str | None = None
    has_mcp: bool | None = None
    format: str | None = None  # SKILL.md, AGENTS.md, README


@dataclass
class SearchResult:
    """Single search result with score breakdown."""

    skill_id: str
    name: str
    summary: str
    domain: str
    repo: str
    quality_score: float
    bm25_score: float
    matched_fields: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class SearchResponse:
    """Full search response with facets and results."""

    query: str
    total: int
    results: list[SearchResult]
    facets: dict[str, list[tuple[str, int]]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# FTS5 setup
# ---------------------------------------------------------------------------

FTS_SKILLS_TABLE = "fts_skills"
FTS_CAPABILITIES_TABLE = "fts_capabilities"
FTS_TAGS_TABLE = "fts_tags"


def _drop_fts_tables(engine: Engine) -> None:
    """Drop FTS5 virtual tables if they exist."""
    with engine.begin() as conn:
        for table in [FTS_SKILLS_TABLE, FTS_CAPABILITIES_TABLE, FTS_TAGS_TABLE]:
            conn.execute(text(f"DROP TABLE IF EXISTS {table}"))


def _create_fts_tables(engine: Engine) -> None:
    """Create FTS5 virtual tables (must be dropped first if exist)."""
    with engine.begin() as conn:
        # Main skills FTS index
        conn.execute(
            text(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_SKILLS_TABLE} USING fts5(
                skill_id UNINDEXED,
                name,
                summary,
                domain,
                repo,
                tokenize='porter unicode61'
            )
        """)
        )

        # Capabilities FTS index
        conn.execute(
            text(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_CAPABILITIES_TABLE} USING fts5(
                skill_id UNINDEXED,
                capability_name,
                canonical_name,
                taxonomy_path,
                tokenize='porter unicode61'
            )
        """)
        )

        # Tags FTS index
        conn.execute(
            text(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TAGS_TABLE} USING fts5(
                skill_id UNINDEXED,
                tag_name,
                tokenize='porter unicode61'
            )
        """)
        )


# ---------------------------------------------------------------------------
# Index sync
# ---------------------------------------------------------------------------


def rebuild_fts_index(session: Session) -> dict[str, int]:
    """Rebuild all FTS5 indexes from current SQLite data.

    Drops existing FTS tables, recreates, and repopulates.
    Returns counts of indexed entries per table.
    """
    engine = session.get_bind()

    # Drop and recreate (contentless FTS5 tables can't be DELETEd from)
    _drop_fts_tables(engine)
    _create_fts_tables(engine)

    with engine.begin() as conn:
        # Index skills (join versions to get latest data)
        conn.execute(
            text(f"""
            INSERT INTO {FTS_SKILLS_TABLE} (skill_id, name, summary, domain, repo)
            SELECT
                s.id,
                COALESCE(v.name, s.name, ''),
                COALESCE(v.summary, ''),
                COALESCE(v.domain_primary, ''),
                COALESCE(v.source_repo, '')
            FROM skills s
            LEFT JOIN versions v ON v.skill_id = s.id
            WHERE s.is_current = 1
        """)
        )

        # Index capabilities
        conn.execute(
            text(f"""
            INSERT INTO {FTS_CAPABILITIES_TABLE} (skill_id, capability_name, canonical_name, taxonomy_path)
            SELECT
                v.skill_id,
                COALESCE(c.name, ''),
                COALESCE(c.canonical, ''),
                COALESCE(c.taxonomy_path, '')
            FROM capabilities c
            JOIN versions v ON v.id = c.version_id_fk
        """)
        )

        # Index tags
        conn.execute(
            text(f"""
            INSERT INTO {FTS_TAGS_TABLE} (skill_id, tag_name)
            SELECT
                v.skill_id,
                COALESCE(t.name, '')
            FROM tags t
            JOIN versions v ON v.id = t.version_id_fk
        """)
        )

        # Get counts
        skill_count = conn.execute(text(f"SELECT COUNT(*) FROM {FTS_SKILLS_TABLE}")).scalar()
        cap_count = conn.execute(text(f"SELECT COUNT(*) FROM {FTS_CAPABILITIES_TABLE}")).scalar()
        tag_count = conn.execute(text(f"SELECT COUNT(*) FROM {FTS_TAGS_TABLE}")).scalar()

    return {
        "skills_indexed": skill_count,
        "capabilities_indexed": cap_count,
        "tags_indexed": tag_count,
    }


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def _build_skill_query(query: str) -> str:
    """Convert user query to FTS5 query syntax.

    - bare words become implicit AND
    - quoted phrases stay quoted
    - words get prefix matching (word*) for autocomplete
    - supports explicit AND/OR/NOT
    """
    if not query or not query.strip():
        return ""

    # If user already uses FTS5 syntax, pass through
    special_chars = set('"*+-()')
    if any(c in query for c in special_chars):
        return query

    # Split into tokens, add prefix matching
    tokens = query.strip().split()
    if not tokens:
        return ""

    fts_tokens = []
    for tok in tokens:
        upper = tok.upper()
        if upper in ("AND", "OR", "NOT"):
            fts_tokens.append(upper)
        else:
            # Add prefix match for each token
            fts_tokens.append(f'"{tok}" OR {tok}*')

    # Join non-boolean tokens with AND, keep booleans as-is
    parts = []
    for tok in fts_tokens:
        if tok in ("AND", "OR", "NOT"):
            parts.append(tok)
        elif parts and parts[-1] not in ("AND", "OR", "NOT"):
            parts.append("AND")
            parts.append(tok)
        else:
            parts.append(tok)

    return " ".join(parts)


def _get_facets(session: Session, skill_ids: list[str]) -> dict[str, list[tuple[str, int]]]:
    """Compute facet counts for a set of skill IDs."""
    if not skill_ids:
        return {}

    facets: dict[str, list[tuple[str, int]]] = {}
    session.get_bind()

    # Domain facets
    placeholders = ",".join(f"'{sid}'" for sid in skill_ids[:500])
    rows = session.execute(
        text(f"""
        SELECT v.domain_primary, COUNT(DISTINCT v.skill_id) as cnt
        FROM versions v
        WHERE v.skill_id IN ({placeholders})
        AND v.domain_primary IS NOT NULL AND v.domain_primary != ''
        GROUP BY v.domain_primary
        ORDER BY cnt DESC
        LIMIT 20
    """)
    ).fetchall()
    facets["domain"] = [(r[0], r[1]) for r in rows]

    # Repo facets
    rows = session.execute(
        text(f"""
        SELECT v.source_repo, COUNT(DISTINCT v.skill_id) as cnt
        FROM versions v
        WHERE v.skill_id IN ({placeholders})
        AND v.source_repo IS NOT NULL AND v.source_repo != ''
        GROUP BY v.source_repo
        ORDER BY cnt DESC
        LIMIT 20
    """)
    ).fetchall()
    facets["repo"] = [(r[0], r[1]) for r in rows]

    # Capability category facets (from taxonomy_path)
    rows = session.execute(
        text(f"""
        SELECT
            CASE
                WHEN c.taxonomy_path LIKE '%/%' THEN SUBSTR(c.taxonomy_path, 1, INSTR(c.taxonomy_path, '/') - 1)
                ELSE COALESCE(c.taxonomy_path, 'uncategorized')
            END as category,
            COUNT(DISTINCT v.skill_id) as cnt
        FROM capabilities c
        JOIN versions v ON v.id = c.version_id_fk
        WHERE v.skill_id IN ({placeholders})
        AND c.taxonomy_path IS NOT NULL AND c.taxonomy_path != ''
        GROUP BY category
        ORDER BY cnt DESC
        LIMIT 20
    """)
    ).fetchall()
    facets["category"] = [(r[0], r[1]) for r in rows]

    return facets


def _apply_filters(
    base_query: str,
    filters: SearchFilters | None,
    params: dict,
) -> tuple[str, dict]:
    """Apply faceted filters to a SQL WHERE clause.

    Returns (conditions_string, updated_params).  The conditions_string
    is either empty or a list of AND-connected conditions WITHOUT a
    leading AND (the caller decides how to prepend).
    """
    if not filters:
        return "", params

    conditions = []

    if filters.domain:
        conditions.append("v.domain_primary = :domain")
        params["domain"] = filters.domain

    if filters.repo:
        conditions.append("v.source_repo = :repo")
        params["repo"] = filters.repo

    if filters.lifecycle:
        conditions.append("s.lifecycle = :lifecycle")
        params["lifecycle"] = filters.lifecycle

    if filters.min_quality is not None:
        conditions.append("CAST(json_extract(v.quality, '$.overall_score') AS REAL) >= :min_quality")
        params["min_quality"] = filters.min_quality

    if filters.max_risk:
        risk_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        max_val = risk_order.get(filters.max_risk.upper(), 3)
        conditions.append("CAST(json_extract(v.security, '$.risk_level') AS TEXT) IN (:risk_levels)")
        allowed = [k for k, v in risk_order.items() if v <= max_val]
        params["risk_levels"] = allowed

    if filters.has_mcp is not None:
        if filters.has_mcp:
            conditions.append("v.compatibility IS NOT NULL AND json_extract(v.compatibility, '$.mcp_compatible') = 1")
        else:
            conditions.append("v.compatibility IS NULL OR json_extract(v.compatibility, '$.mcp_compatible') != 1")

    if filters.format:
        conditions.append("v.source_type = :format")
        params["format"] = filters.format

    return " AND ".join(conditions), params


def search(
    session: Session,
    query: str,
    filters: SearchFilters | None = None,
    limit: int = 50,
    offset: int = 0,
    include_facets: bool = True,
) -> SearchResponse:
    """Full-text search with BM25 ranking and faceted filtering.

    Args:
        session: SQLAlchemy session
        query: Search query string
        filters: Optional faceted filters
        limit: Max results (default 50)
        offset: Pagination offset
        include_facets: Whether to compute facets

    Returns:
        SearchResponse with results, total count, and facets
    """
    engine = session.get_bind()
    _create_fts_tables(engine)

    fts_query = _build_skill_query(query)
    if not fts_query:
        return SearchResponse(query=query, total=0, results=[])

    # Build the search query with BM25 ranking
    params = {"fts_query": fts_query, "limit": limit, "offset": offset}

    # Main search using FTS5 with BM25
    sql = """
        SELECT
            fts.skill_id,
            fts.name,
            fts.summary,
            fts.domain,
            fts.repo,
            bm25(fts_skills, 10.0, 5.0, 2.0, 1.0) as rank
        FROM fts_skills fts
        WHERE fts_skills MATCH :fts_query
    """

    # Apply filters via EXISTS subquery
    filter_conditions, filter_params = _apply_filters("", filters, params)
    filter_sql = """
        AND EXISTS (
            SELECT 1 FROM skills s
            JOIN versions v ON v.skill_id = s.id
            WHERE s.id = fts.skill_id AND s.is_current = 1
    """
    if filter_conditions:
        filter_sql += " AND " + filter_conditions
    filter_sql += ")"
    sql += filter_sql

    sql += " ORDER BY rank LIMIT :limit OFFSET :offset"

    try:
        rows = session.execute(text(sql), filter_params).fetchall()
    except Exception:
        # Fallback: simpler query if FTS has issues
        return SearchResponse(query=query, total=0, results=[])

    # Get total count
    count_sql = """
        SELECT COUNT(*)
        FROM fts_skills fts
        WHERE fts_skills MATCH :fts_query
    """
    count_sql += filter_sql
    try:
        total = session.execute(text(count_sql), filter_params).scalar() or 0
    except Exception:
        total = len(rows)

    # Build results
    results = []
    for row in rows:
        skill_id = row[0]

        # Get capabilities
        caps = session.execute(
            text("""
            SELECT c.canonical FROM capabilities c
            JOIN versions v ON v.id = c.version_id_fk
            WHERE v.skill_id = :sid
            LIMIT 10
        """),
            {"sid": skill_id},
        ).fetchall()

        # Get tags
        tags = session.execute(
            text("""
            SELECT t.name FROM tags t
            JOIN versions v ON v.id = t.version_id_fk
            WHERE v.skill_id = :sid
            LIMIT 10
        """),
            {"sid": skill_id},
        ).fetchall()

        # Get quality score
        quality_row = session.execute(
            text("""
            SELECT CAST(json_extract(v.quality, '$.overall_score') AS REAL)
            FROM versions v WHERE v.skill_id = :sid LIMIT 1
        """),
            {"sid": skill_id},
        ).fetchone()
        quality = quality_row[0] if quality_row and quality_row[0] is not None else 0.0

        # Determine matched fields
        matched = []
        fts_q_lower = fts_query.lower()
        if row[1] and any(t in row[1].lower() for t in fts_q_lower.split()):
            matched.append("name")
        if row[2] and any(t in row[2].lower() for t in fts_q_lower.split()):
            matched.append("summary")
        if row[3] and any(t in row[3].lower() for t in fts_q_lower.split()):
            matched.append("domain")
        if any(c[0] and any(t in c[0].lower() for t in fts_q_lower.split()) for c in caps):
            matched.append("capabilities")
        if any(t[0] and any(tok in t[0].lower() for tok in fts_q_lower.split()) for t in tags):
            matched.append("tags")

        results.append(
            SearchResult(
                skill_id=skill_id,
                name=row[1] or "",
                summary=row[2] or "",
                domain=row[3] or "",
                repo=row[4] or "",
                quality_score=quality,
                bm25_score=abs(row[5]) if row[5] else 0.0,
                matched_fields=list(set(matched)),
                capabilities=[c[0] for c in caps if c[0]],
                tags=[t[0] for t in tags if t[0]],
            )
        )

    # Compute facets
    facets = {}
    if include_facets and results:
        result_ids = [r.skill_id for r in results]
        facets = _get_facets(session, result_ids)

    return SearchResponse(
        query=query,
        total=total,
        results=results,
        facets=facets,
    )


# ---------------------------------------------------------------------------
# Capability / Tag search
# ---------------------------------------------------------------------------


def search_by_capability(
    session: Session,
    capability: str,
    limit: int = 50,
) -> list[SearchResult]:
    """Search skills by capability name (exact or fuzzy)."""
    engine = session.get_bind()
    _create_fts_tables(engine)

    fts_query = _build_skill_query(capability)

    rows = session.execute(
        text(f"""
        SELECT DISTINCT skill_id FROM {FTS_CAPABILITIES_TABLE}
        WHERE {FTS_CAPABILITIES_TABLE} MATCH :fts_query
        LIMIT :limit
    """),
        {"fts_query": fts_query, "limit": limit},
    ).fetchall()

    results = []
    for row in rows:
        skill = session.execute(
            text("""
            SELECT s.id, v.name, v.summary, v.domain_primary, v.source_repo
            FROM skills s
            JOIN versions v ON v.skill_id = s.id
            WHERE s.id = :sid AND s.is_current = 1
            LIMIT 1
        """),
            {"sid": row[0]},
        ).fetchone()

        if skill:
            results.append(
                SearchResult(
                    skill_id=skill[0],
                    name=skill[1] or "",
                    summary=skill[2] or "",
                    domain=skill[3] or "",
                    repo=skill[4] or "",
                    quality_score=0.0,
                    bm25_score=0.0,
                    matched_fields=["capabilities"],
                )
            )

    return results


def search_by_tag(
    session: Session,
    tag: str,
    limit: int = 50,
) -> list[SearchResult]:
    """Search skills by tag name."""
    engine = session.get_bind()
    _create_fts_tables(engine)

    fts_query = _build_skill_query(tag)

    rows = session.execute(
        text(f"""
        SELECT DISTINCT skill_id FROM {FTS_TAGS_TABLE}
        WHERE {FTS_TAGS_TABLE} MATCH :fts_query
        LIMIT :limit
    """),
        {"fts_query": fts_query, "limit": limit},
    ).fetchall()

    results = []
    for row in rows:
        skill = session.execute(
            text("""
            SELECT s.id, v.name, v.summary, v.domain_primary, v.source_repo
            FROM skills s
            JOIN versions v ON v.skill_id = s.id
            WHERE s.id = :sid AND s.is_current = 1
            LIMIT 1
        """),
            {"sid": row[0]},
        ).fetchone()

        if skill:
            results.append(
                SearchResult(
                    skill_id=skill[0],
                    name=skill[1] or "",
                    summary=skill[2] or "",
                    domain=skill[3] or "",
                    repo=skill[4] or "",
                    quality_score=0.0,
                    bm25_score=0.0,
                    matched_fields=["tags"],
                )
            )

    return results


# ---------------------------------------------------------------------------
# Autocomplete / suggestions
# ---------------------------------------------------------------------------


def autocomplete(
    session: Session,
    prefix: str,
    limit: int = 10,
) -> list[str]:
    """Return skill names matching a prefix for autocomplete."""
    if not prefix or len(prefix) < 2:
        return []

    engine = session.get_bind()
    _create_fts_tables(engine)

    # Use prefix search on name field
    fts_query = f'"{prefix}"*'

    rows = session.execute(
        text(f"""
        SELECT name FROM {FTS_SKILLS_TABLE}
        WHERE name MATCH :fts_query
        ORDER BY rank
        LIMIT :limit
    """),
        {"fts_query": fts_query, "limit": limit},
    ).fetchall()

    return [r[0] for r in rows if r[0]]


# ---------------------------------------------------------------------------
# Search stats
# ---------------------------------------------------------------------------


def get_search_stats(session: Session) -> dict:
    """Get search index statistics."""
    engine = session.get_bind()
    _create_fts_tables(engine)

    stats = {}
    for table_name in [FTS_SKILLS_TABLE, FTS_CAPABILITIES_TABLE, FTS_TAGS_TABLE]:
        try:
            count = session.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            stats[table_name] = count
        except Exception:
            stats[table_name] = 0

    return stats


__all__ = [
    "SearchFilters",
    "SearchResponse",
    "SearchResult",
    "autocomplete",
    "get_search_stats",
    "rebuild_fts_index",
    "search",
    "search_by_capability",
    "search_by_tag",
]
