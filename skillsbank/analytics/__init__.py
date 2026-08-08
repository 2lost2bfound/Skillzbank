"""SkillsBank Analytics — comprehensive diagnostics, trends, and gap analysis."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from skillsbank.db.persistence_models import (
    CapabilityRow,
    RepoRow,
    RepoSnapshotRow,
    SkillRow,
    TagRow,
    VersionRow,
)

# ── Data classes ───────────────────────────────────────────────────────


@dataclass
class CheckResult:
    """A single diagnostic check."""

    name: str
    status: str  # "ok", "warn", "fail", "info"
    detail: str
    value: Any = None
    recommendation: str | None = None


@dataclass
class CoverageReport:
    """Data completeness analysis."""

    total_skills: int = 0
    with_summary: int = 0
    with_domain: int = 0
    with_capabilities: int = 0
    with_tags: int = 0
    with_quality_score: int = 0
    with_security_assessment: int = 0
    with_license: int = 0
    with_dependencies: int = 0
    with_compatibility: int = 0
    with_raw_content: int = 0
    coverage_pct: dict[str, float] = field(default_factory=dict)

    def compute(self) -> None:
        """Compute coverage percentages."""
        t = self.total_skills or 1
        self.coverage_pct = {
            "summary": round(self.with_summary / t * 100, 1),
            "domain": round(self.with_domain / t * 100, 1),
            "capabilities": round(self.with_capabilities / t * 100, 1),
            "tags": round(self.with_tags / t * 100, 1),
            "quality_score": round(self.with_quality_score / t * 100, 1),
            "security": round(self.with_security_assessment / t * 100, 1),
            "license": round(self.with_license / t * 100, 1),
            "dependencies": round(self.with_dependencies / t * 100, 1),
            "compatibility": round(self.with_compatibility / t * 100, 1),
            "raw_content": round(self.with_raw_content / t * 100, 1),
        }


@dataclass
class GapAnalysis:
    """Identifies missing or incomplete data."""

    missing_summary: list[str] = field(default_factory=list)
    missing_domain: list[str] = field(default_factory=list)
    uncategorized_capabilities: list[str] = field(default_factory=list)
    broken_quality: list[str] = field(default_factory=list)
    empty_repos: list[str] = field(default_factory=list)
    stale_repos: list[str] = field(default_factory=list)
    high_risk_skills: list[str] = field(default_factory=list)


@dataclass
class QualityDistribution:
    """Quality score distribution."""

    min: float = 0.0
    max: float = 0.0
    mean: float = 0.0
    median: float = 0.0
    p25: float = 0.0
    p75: float = 0.0
    histogram: dict[str, int] = field(default_factory=dict)
    top_skills: list[dict[str, Any]] = field(default_factory=list)
    bottom_skills: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EcosystemHealth:
    """Per-repository health metrics."""

    repo_url: str = ""
    owner: str = ""
    name: str = ""
    skill_count: int = 0
    avg_quality: float = 0.0
    has_license: bool = False
    parser_compatible: str = ""
    last_sync: str | None = None
    issues: list[str] = field(default_factory=list)


@dataclass
class AnalyticsReport:
    """Complete analytics report."""

    generated_at: str = ""
    checks: list[CheckResult] = field(default_factory=list)
    coverage: CoverageReport = field(default_factory=CoverageReport)
    gaps: GapAnalysis = field(default_factory=GapAnalysis)
    quality: QualityDistribution = field(default_factory=QualityDistribution)
    ecosystems: list[EcosystemHealth] = field(default_factory=list)
    domain_distribution: dict[str, int] = field(default_factory=dict)
    category_distribution: dict[str, int] = field(default_factory=dict)
    risk_distribution: dict[str, int] = field(default_factory=dict)
    agent_compatibility: dict[str, dict[str, int]] = field(default_factory=dict)
    dependency_risks: list[dict[str, Any]] = field(default_factory=list)
    duplicate_summary: dict[str, Any] = field(default_factory=dict)

    @property
    def overall_health(self) -> str:
        """Overall health: healthy, degraded, unhealthy."""
        fail_count = sum(1 for c in self.checks if c.status == "fail")
        warn_count = sum(1 for c in self.checks if c.status == "warn")
        if fail_count > 0:
            return "unhealthy"
        if warn_count > 2:
            return "degraded"
        return "healthy"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON output."""
        return {
            "generated_at": self.generated_at,
            "overall_health": self.overall_health,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status,
                    "detail": c.detail,
                    "value": c.value,
                    "recommendation": c.recommendation,
                }
                for c in self.checks
            ],
            "coverage": {
                "total_skills": self.coverage.total_skills,
                "percentages": self.coverage.coverage_pct,
                "counts": {
                    "summary": self.coverage.with_summary,
                    "domain": self.coverage.with_domain,
                    "capabilities": self.coverage.with_capabilities,
                    "tags": self.coverage.with_tags,
                    "quality_score": self.coverage.with_quality_score,
                    "security": self.coverage.with_security_assessment,
                    "license": self.coverage.with_license,
                    "dependencies": self.coverage.with_dependencies,
                    "compatibility": self.coverage.with_compatibility,
                    "raw_content": self.coverage.with_raw_content,
                },
            },
            "gaps": {
                "missing_summary": len(self.gaps.missing_summary),
                "missing_domain": len(self.gaps.missing_domain),
                "uncategorized_capabilities": len(self.gaps.uncategorized_capabilities),
                "broken_quality": len(self.gaps.broken_quality),
                "empty_repos": self.gaps.empty_repos,
                "stale_repos": self.gaps.stale_repos,
                "high_risk_skills": len(self.gaps.high_risk_skills),
            },
            "quality": {
                "min": self.quality.min,
                "max": self.quality.max,
                "mean": self.quality.mean,
                "median": self.quality.median,
                "p25": self.quality.p25,
                "p75": self.quality.p75,
                "histogram": self.quality.histogram,
                "top_skills": self.quality.top_skills[:5],
                "bottom_skills": self.quality.bottom_skills[:5],
            },
            "ecosystems": [
                {
                    "repo": e.repo_url,
                    "owner": e.owner,
                    "name": e.name,
                    "skill_count": e.skill_count,
                    "avg_quality": e.avg_quality,
                    "has_license": e.has_license,
                    "issues": e.issues,
                }
                for e in self.ecosystems
            ],
            "domain_distribution": self.domain_distribution,
            "category_distribution": self.category_distribution,
            "risk_distribution": self.risk_distribution,
            "agent_compatibility": self.agent_compatibility,
            "dependency_risks": self.dependency_risks,
            "duplicate_summary": self.duplicate_summary,
        }


# ── Core analytics functions ──────────────────────────────────────────


def _check_db_accessible(session: Session) -> CheckResult:
    """Check database is accessible and has data."""
    try:
        count = session.query(func.count(SkillRow.id)).scalar()
        if count == 0:
            return CheckResult("DB accessible", "warn", "Database is empty", count)
        return CheckResult("DB accessible", "ok", f"{count:,} skills loaded", count)
    except Exception as e:
        return CheckResult("DB accessible", "fail", str(e))


def _check_fk_integrity(session: Session) -> CheckResult:
    """Check foreign key integrity."""
    orphans = session.execute(
        text("SELECT COUNT(*) FROM versions v LEFT JOIN skills s ON v.skill_id = s.id WHERE s.id IS NULL")
    ).scalar()
    if orphans > 0:
        return CheckResult(
            "FK integrity", "fail", f"{orphans} orphan versions", orphans, "Run import to fix orphaned records"
        )
    return CheckResult("FK integrity", "ok", "No orphan records")


def _check_fts_index(session: Session) -> CheckResult:
    """Check FTS5 index health."""
    try:
        from skillsbank.search import get_search_stats

        stats = get_search_stats(session)
        fts_count = stats.get("fts_skills", 0)
        skill_count = session.query(func.count(SkillRow.id)).scalar()
        if fts_count == 0:
            return CheckResult("FTS index", "fail", "FTS index is empty", 0, "Run `skillsbank rebuild-fts`")
        if fts_count < skill_count:
            return CheckResult(
                "FTS index",
                "warn",
                f"FTS has {fts_count} entries but {skill_count} skills",
                fts_count,
                "Run `skillsbank rebuild-fts` to reindex",
            )
        return CheckResult("FTS index", "ok", f"{fts_count:,} entries indexed", fts_count)
    except Exception as e:
        return CheckResult("FTS index", "fail", str(e), recommendation="Run `skillsbank rebuild-fts`")


def _check_capability_taxonomy(session: Session) -> CheckResult:
    """Check capability normalization coverage."""
    total = session.query(func.count(CapabilityRow.id)).scalar()
    uncategorized = session.execute(
        text("SELECT COUNT(*) FROM capabilities WHERE taxonomy_path IS NULL OR taxonomy_path = ''")
    ).scalar()
    if total == 0:
        return CheckResult("Capability taxonomy", "warn", "No capabilities indexed")
    pct = round((total - uncategorized) / total * 100, 1)
    if uncategorized > total * 0.5:
        return CheckResult(
            "Capability taxonomy",
            "warn",
            f"{uncategorized}/{total} uncategorized ({pct}% classified)",
            pct,
            "Run `skillsbank normalize` to improve coverage",
        )
    return CheckResult("Capability taxonomy", "ok", f"{pct}% classified ({uncategorized} uncategorized)", pct)


def _check_quality_coverage(session: Session) -> CheckResult:
    """Check quality scoring coverage."""
    total = session.query(func.count(VersionRow.id)).scalar()
    scored = session.execute(
        text("SELECT COUNT(*) FROM versions WHERE quality IS NOT NULL AND quality != '{}' AND quality != 'null'")
    ).scalar()
    if total == 0:
        return CheckResult("Quality scoring", "info", "No versions to score")
    pct = round(scored / total * 100, 1)
    if scored < total:
        return CheckResult(
            "Quality scoring",
            "warn",
            f"{scored}/{total} versions scored ({pct}%)",
            pct,
            "Re-run import to compute quality scores",
        )
    return CheckResult("Quality scoring", "ok", f"All {total} versions scored", pct)


def _check_security_assessment(session: Session) -> CheckResult:
    """Check security assessment coverage."""
    total = session.query(func.count(VersionRow.id)).scalar()
    assessed = session.execute(
        text("SELECT COUNT(*) FROM versions WHERE security IS NOT NULL AND security != '{}' AND security != 'null'")
    ).scalar()
    if total == 0:
        return CheckResult("Security assessment", "info", "No versions to assess")
    pct = round(assessed / total * 100, 1)
    high_risk = session.execute(
        text("SELECT COUNT(*) FROM versions WHERE json_extract(security, '$.risk_level') IN ('HIGH', 'CRITICAL')")
    ).scalar()
    detail = f"{assessed}/{total} assessed ({pct}%)"
    if high_risk > 0:
        detail += f", {high_risk} high/critical risk"
    status = "ok" if assessed == total else "warn"
    return CheckResult("Security assessment", status, detail, {"assessed": assessed, "high_risk": high_risk})


def _check_repo_health(session: Session) -> CheckResult:
    """Check repository registration health."""
    repos = session.query(RepoRow).all()
    if not repos:
        return CheckResult("Repo health", "warn", "No repositories registered")
    empty = [r.url for r in repos if r.skill_count == 0]
    if empty:
        return CheckResult(
            "Repo health",
            "warn",
            f"{len(empty)}/{len(repos)} repos have 0 skills",
            {"total": len(repos), "empty": len(empty)},
        )
    return CheckResult("Repo health", "ok", f"{len(repos)} repos registered", len(repos))


def _check_data_freshness(session: Session) -> CheckResult:
    """Check how recently data was synced."""
    last_import = session.execute(text("SELECT MAX(imported_at) FROM versions")).scalar()
    if not last_import:
        return CheckResult("Data freshness", "warn", "No import timestamps found")
    # Could be string or datetime
    return CheckResult("Data freshness", "ok", f"Last import: {last_import}")


def _check_duplicate_rate(session: Session) -> CheckResult:
    """Check duplicate detection status."""
    from skillsbank.db.persistence_models import RelationshipRow

    dup_count = session.query(func.count(RelationshipRow.id)).filter(RelationshipRow.rel_type == "DUPLICATE").scalar()
    if dup_count > 0:
        return CheckResult(
            "Duplicate detection",
            "warn",
            f"{dup_count} duplicate pairs found",
            dup_count,
            "Review duplicates with `skillsbank dedup`",
        )
    return CheckResult("Duplicate detection", "ok", "No exact duplicates detected")


def run_health_checks(session: Session) -> list[CheckResult]:
    """Run all health checks and return results."""
    return [
        _check_db_accessible(session),
        _check_fk_integrity(session),
        _check_fts_index(session),
        _check_capability_taxonomy(session),
        _check_quality_coverage(session),
        _check_security_assessment(session),
        _check_repo_health(session),
        _check_data_freshness(session),
        _check_duplicate_rate(session),
    ]


# ── Coverage analysis ─────────────────────────────────────────────────


def compute_coverage(session: Session) -> CoverageReport:
    """Compute data completeness coverage."""
    total = session.query(func.count(SkillRow.id)).scalar()
    if total == 0:
        return CoverageReport()

    report = CoverageReport(total_skills=total)

    # Count versions with each field populated
    report.with_summary = session.execute(
        text("SELECT COUNT(*) FROM versions WHERE summary IS NOT NULL AND summary != ''")
    ).scalar()

    report.with_domain = session.execute(
        text("SELECT COUNT(*) FROM versions WHERE domain_primary IS NOT NULL AND domain_primary != ''")
    ).scalar()

    report.with_capabilities = session.execute(text("SELECT COUNT(DISTINCT version_id_fk) FROM capabilities")).scalar()

    report.with_tags = session.execute(text("SELECT COUNT(DISTINCT version_id_fk) FROM tags")).scalar()

    report.with_quality_score = session.execute(
        text("SELECT COUNT(*) FROM versions WHERE quality IS NOT NULL AND quality != '{}' AND quality != 'null'")
    ).scalar()

    report.with_security_assessment = session.execute(
        text("SELECT COUNT(*) FROM versions WHERE security IS NOT NULL AND security != '{}' AND security != 'null'")
    ).scalar()

    report.with_license = session.execute(
        text("SELECT COUNT(*) FROM versions WHERE license IS NOT NULL AND license != '{}' AND license != 'null'")
    ).scalar()

    report.with_dependencies = session.execute(
        text(
            "SELECT COUNT(*) FROM versions WHERE (inferred_dependencies IS NOT NULL AND inferred_dependencies != '[]' AND inferred_dependencies != 'null') OR (declared_dependencies IS NOT NULL AND declared_dependencies != '[]' AND declared_dependencies != 'null')"
        )
    ).scalar()

    report.with_compatibility = session.execute(
        text(
            "SELECT COUNT(*) FROM versions WHERE compatibility IS NOT NULL AND compatibility != '{}' AND compatibility != 'null'"
        )
    ).scalar()

    report.with_raw_content = session.execute(
        text("SELECT COUNT(*) FROM versions WHERE raw_content IS NOT NULL AND raw_content != ''")
    ).scalar()

    report.compute()
    return report


# ── Gap analysis ──────────────────────────────────────────────────────


def compute_gaps(session: Session, limit: int = 50) -> GapAnalysis:
    """Identify missing or incomplete data."""
    gaps = GapAnalysis()

    # Missing summary
    rows = session.execute(
        text("SELECT skill_id FROM versions WHERE summary IS NULL OR summary = '' LIMIT :lim"), {"lim": limit}
    ).fetchall()
    gaps.missing_summary = [r[0] for r in rows]

    # Missing domain
    rows = session.execute(
        text("SELECT skill_id FROM versions WHERE domain_primary IS NULL OR domain_primary = '' LIMIT :lim"),
        {"lim": limit},
    ).fetchall()
    gaps.missing_domain = [r[0] for r in rows]

    # Uncategorized capabilities
    rows = session.execute(
        text("SELECT DISTINCT name FROM capabilities WHERE taxonomy_path IS NULL OR taxonomy_path = '' LIMIT :lim"),
        {"lim": limit},
    ).fetchall()
    gaps.uncategorized_capabilities = [r[0] for r in rows]

    # Broken quality (invalid JSON or missing overall_score)
    rows = session.execute(
        text(
            "SELECT skill_id FROM versions WHERE quality IS NOT NULL AND quality != '{}' AND json_extract(quality, '$.overall_score') IS NULL LIMIT :lim"
        ),
        {"lim": limit},
    ).fetchall()
    gaps.broken_quality = [r[0] for r in rows]

    # Empty repos
    rows = session.execute(text("SELECT url FROM repositories WHERE skill_count = 0 OR skill_count IS NULL")).fetchall()
    gaps.empty_repos = [r[0] for r in rows]

    # Stale repos (no successful sync)
    rows = session.execute(text("SELECT url FROM repositories WHERE last_successful_sync IS NULL")).fetchall()
    gaps.stale_repos = [r[0] for r in rows]

    # High risk skills
    rows = session.execute(
        text(
            "SELECT skill_id FROM versions WHERE json_extract(security, '$.risk_level') IN ('HIGH', 'CRITICAL') LIMIT :lim"
        ),
        {"lim": limit},
    ).fetchall()
    gaps.high_risk_skills = [r[0] for r in rows]

    return gaps


# ── Quality distribution ──────────────────────────────────────────────


def compute_quality_distribution(session: Session) -> QualityDistribution:
    """Compute quality score distribution."""
    dist = QualityDistribution()

    scores_raw = session.execute(
        text("SELECT skill_id, json_extract(quality, '$.overall_score') as score FROM versions WHERE score IS NOT NULL")
    ).fetchall()

    if not scores_raw:
        return dist

    scores = [(r[0], float(r[1])) for r in scores_raw if r[1] is not None]
    if not scores:
        return dist

    scores.sort(key=lambda x: x[1])
    vals = [s[1] for s in scores]
    n = len(vals)

    dist.min = round(vals[0], 3)
    dist.max = round(vals[-1], 3)
    dist.mean = round(sum(vals) / n, 3)
    dist.median = round(vals[n // 2], 3)
    dist.p25 = round(vals[n // 4], 3)
    dist.p75 = round(vals[3 * n // 4], 3)

    # Histogram: 0.0-0.1, 0.1-0.2, ..., 0.9-1.0
    buckets = {f"{i / 10:.1f}-{(i + 1) / 10:.1f}": 0 for i in range(10)}
    for _, v in scores:
        idx = min(int(v * 10), 9)
        buckets[f"{idx / 10:.1f}-{(idx + 1) / 10:.1f}"] += 1
    dist.histogram = buckets

    # Top and bottom skills
    skill_ids = [s[0] for s in scores]
    bottom_ids = skill_ids[:5]
    top_ids = skill_ids[-5:]

    if top_ids:
        top_rows = session.query(SkillRow).filter(SkillRow.id.in_(top_ids)).all()
        dist.top_skills = [
            {"id": s.id, "name": s.name, "score": next(v for sid, v in scores if sid == s.id)} for s in top_rows
        ]
        dist.top_skills.sort(key=lambda x: -x["score"])

    if bottom_ids:
        bottom_rows = session.query(SkillRow).filter(SkillRow.id.in_(bottom_ids)).all()
        dist.bottom_skills = [
            {"id": s.id, "name": s.name, "score": next(v for sid, v in scores if sid == s.id)} for s in bottom_rows
        ]
        dist.bottom_skills.sort(key=lambda x: x["score"])

    return dist


# ── Ecosystem health ──────────────────────────────────────────────────


def compute_ecosystem_health(session: Session) -> list[EcosystemHealth]:
    """Compute per-repository health metrics."""
    repos = session.query(RepoRow).all()
    results = []

    for repo in repos:
        health = EcosystemHealth(
            repo_url=repo.url or "",
            owner=repo.owner or "",
            name=repo.name or "",
            skill_count=repo.skill_count or 0,
            parser_compatible=repo.parser_compatibility or "",
            last_sync=repo.last_successful_sync,
            has_license=repo.license is not None and repo.license != "{}",
        )

        # Average quality for this repo's skills
        avg_q = session.execute(
            text(
                "SELECT AVG(json_extract(v.quality, '$.overall_score')) FROM versions v WHERE v.source_repo = :repo AND v.quality IS NOT NULL"
            ),
            {"repo": f"{repo.owner}/{repo.name}"},
        ).scalar()
        health.avg_quality = round(avg_q, 3) if avg_q else 0.0

        # Issues
        if health.skill_count == 0:
            health.issues.append("No skills indexed")
        if not health.has_license:
            health.issues.append("No license declared")
        if not health.last_sync:
            health.issues.append("Never synced")
        if health.avg_quality < 0.4 and health.skill_count > 0:
            health.issues.append(f"Low avg quality ({health.avg_quality})")

        results.append(health)

    results.sort(key=lambda x: -x.skill_count)
    return results


# ── Domain and category distributions ─────────────────────────────────


def compute_domain_distribution(session: Session) -> dict[str, int]:
    """Get skill count per domain."""
    rows = (
        session.query(VersionRow.domain_primary, func.count(VersionRow.id))
        .group_by(VersionRow.domain_primary)
        .order_by(func.count(VersionRow.id).desc())
        .all()
    )
    return {d or "unknown": c for d, c in rows}


def compute_category_distribution(session: Session) -> dict[str, int]:
    """Get capability count per taxonomy category."""
    rows = session.execute(
        text(
            "SELECT CASE WHEN taxonomy_path IS NULL OR taxonomy_path = '' THEN 'uncategorized' ELSE SUBSTR(taxonomy_path, 1, INSTR(taxonomy_path, '.') - 1) END as category, COUNT(*) FROM capabilities GROUP BY category ORDER BY COUNT(*) DESC"
        )
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def compute_risk_distribution(session: Session) -> dict[str, int]:
    """Get version count per security risk level."""
    rows = session.execute(
        text(
            "SELECT COALESCE(json_extract(security, '$.risk_level'), 'UNKNOWN') as risk, COUNT(*) FROM versions GROUP BY risk ORDER BY COUNT(*) DESC"
        )
    ).fetchall()
    return {r[0]: r[1] for r in rows}


# ── Agent compatibility summary ───────────────────────────────────────


def compute_agent_compatibility(session: Session) -> dict[str, dict[str, int]]:
    """Get compatibility level distribution per agent."""
    rows = session.execute(
        text(
            "SELECT compatibility FROM versions WHERE compatibility IS NOT NULL AND compatibility != '{}' AND compatibility != 'null'"
        )
    ).fetchall()

    agent_counts: dict[str, Counter] = defaultdict(Counter)
    for (compat_json,) in rows:
        try:
            compat = json.loads(compat_json) if isinstance(compat_json, str) else compat_json
            if isinstance(compat, dict):
                for agent, data in compat.items():
                    if isinstance(data, dict):
                        level = data.get("level", "UNKNOWN")
                        agent_counts[agent][level] += 1
        except (json.JSONDecodeError, TypeError):
            continue

    return {agent: dict(counts) for agent, counts in agent_counts.items()}


# ── Dependency risks ──────────────────────────────────────────────────


def compute_dependency_risks(session: Session) -> list[dict[str, Any]]:
    """Identify skills with dependency issues."""
    risks = []

    # Skills with many external dependencies (high coupling)
    rows = session.execute(
        text(
            "SELECT skill_id, inferred_dependencies FROM versions WHERE inferred_dependencies IS NOT NULL AND inferred_dependencies != '[]' AND inferred_dependencies != 'null'"
        )
    ).fetchall()

    for skill_id, deps_json in rows:
        try:
            deps = json.loads(deps_json) if isinstance(deps_json, str) else deps_json
            if not isinstance(deps, list):
                continue
            if len(deps) > 10:
                risks.append(
                    {
                        "skill_id": skill_id,
                        "issue": "high_coupling",
                        "detail": f"{len(deps)} external dependencies",
                        "severity": "warn",
                    }
                )
            # Check for API key requirements
            api_deps = [d for d in deps if isinstance(d, dict) and d.get("category") == "api"]
            if api_deps:
                risks.append(
                    {
                        "skill_id": skill_id,
                        "issue": "api_key_required",
                        "detail": f"Requires {len(api_deps)} API key(s): {', '.join(d.get('name', '?') for d in api_deps[:3])}",
                        "severity": "info",
                    }
                )
        except (json.JSONDecodeError, TypeError):
            continue

    return risks[:50]  # Limit output


# ── Duplicate summary ─────────────────────────────────────────────────


def compute_duplicate_summary(session: Session) -> dict[str, Any]:
    """Summarize duplicate detection results."""
    from skillsbank.db.persistence_models import RelationshipRow, SimilarityRow

    total_sims = session.query(func.count(SimilarityRow.id)).scalar()
    dup_rels = session.query(func.count(RelationshipRow.id)).filter(RelationshipRow.rel_type == "DUPLICATE").scalar()

    # Similarity distribution
    sim_dist = session.execute(
        text(
            "SELECT CASE WHEN overall_score >= 0.95 THEN 'exact' WHEN overall_score >= 0.80 THEN 'near' WHEN overall_score >= 0.60 THEN 'functional' ELSE 'related' END as category, COUNT(*) FROM similarities GROUP BY category"
        )
    ).fetchall()

    return {
        "total_similarities": total_sims,
        "duplicate_relationships": dup_rels,
        "distribution": {r[0]: r[1] for r in sim_dist},
    }


# ── Main analytics function ──────────────────────────────────────────


def run_full_analytics(session: Session) -> AnalyticsReport:
    """Run complete analytics suite and return a report."""
    report = AnalyticsReport(
        generated_at=datetime.now(UTC).isoformat(),
    )

    # Health checks
    report.checks = run_health_checks(session)

    # Coverage
    report.coverage = compute_coverage(session)

    # Gaps
    report.gaps = compute_gaps(session)

    # Quality
    report.quality = compute_quality_distribution(session)

    # Ecosystems
    report.ecosystems = compute_ecosystem_health(session)

    # Distributions
    report.domain_distribution = compute_domain_distribution(session)
    report.category_distribution = compute_category_distribution(session)
    report.risk_distribution = compute_risk_distribution(session)

    # Agent compatibility
    report.agent_compatibility = compute_agent_compatibility(session)

    # Dependency risks
    report.dependency_risks = compute_dependency_risks(session)

    # Duplicates
    report.duplicate_summary = compute_duplicate_summary(session)

    return report
