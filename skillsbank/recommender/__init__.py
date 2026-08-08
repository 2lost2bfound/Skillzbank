"""Recommendation engine: suggest skills based on context, installed skills, and task descriptions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from skillsbank.db.persistence_models import (
    CapabilityRow,
    RepoRow,
    SimilarityRow,
    SkillRow,
    TagRow,
    VersionRow,
)
from skillsbank.taxonomy import classify_capability


class RecommendationReason(str, Enum):
    SIMILAR = "similar"
    COMPLEMENTARY = "complementary"
    POPULAR = "popular"
    HIGH_QUALITY = "high_quality"
    TASK_MATCH = "task_match"
    SAME_ECOSYSTEM = "same_ecosystem"
    SAME_CATEGORY = "same_category"
    TRENDING = "trending"


@dataclass
class Recommendation:
    skill_id: str
    name: str
    summary: str
    score: float
    reason: RecommendationReason
    reason_detail: str
    source_repo: str = ""
    domain: str = ""
    quality_score: float = 0.0
    version_id: int = 0


@dataclass
class RecommendationSet:
    task: str
    installed_ids: list[str]
    recommendations: list[Recommendation]
    facets: dict[str, int] = field(default_factory=dict)

    def top(self, n: int = 10) -> list[Recommendation]:
        return self.recommendations[:n]

    def by_reason(self, reason: RecommendationReason) -> list[Recommendation]:
        return [r for r in self.recommendations if r.reason == reason]


# ── Task-to-capability mapping ──────────────────────────────────────────

TASK_KEYWORDS: dict[str, list[str]] = {
    "security": ["security-audit", "vulnerability-scanning", "penetration-testing", "threat-modeling", "code-audit"],
    "frontend": ["react-development", "ui-design", "css-styling", "component-building", "responsive-design"],
    "backend": ["api-design", "database-design", "server-architecture", "microservices"],
    "devops": ["ci-cd", "containerization", "infrastructure-as-code", "monitoring", "deployment"],
    "testing": ["test-writing", "test-strategy", "qa-automation", "integration-testing", "unit-testing"],
    "tests": ["test-writing", "test-strategy", "qa-automation", "integration-testing", "unit-testing"],
    "test": ["test-writing", "test-strategy", "qa-automation", "integration-testing", "unit-testing"],
    "data": ["data-analysis", "etl-pipeline", "data-visualization", "sql-queries"],
    "ai": ["llm-integration", "prompt-engineering", "model-evaluation", "rag-system"],
    "documentation": ["documentation-writing", "technical-writing", "api-documentation"],
    "research": ["research", "web-research", "literature-review"],
    "code quality": ["code-review", "refactoring", "static-analysis", "linting"],
    "architecture": ["architecture-design", "system-design", "domain-modeling"],
    "performance": ["performance-optimization", "profiling", "caching"],
    "mobile": ["ios-development", "android-development", "cross-platform"],
    "database": ["sql-optimization", "schema-design", "migration-management"],
    "cloud": ["aws-services", "gcp-services", "azure-services", "serverless"],
    "automation": ["task-automation", "workflow-automation", "scripting"],
    "design": ["visual-design", "ui-design", "design-systems"],
    "api": ["api-design", "rest-api", "graphql", "api-testing"],
    "git": ["git-workflow", "version-control", "branching-strategy"],
    "docker": ["containerization", "docker-compose", "image-building"],
}


def _extract_task_keywords(task: str) -> list[str]:
    """Extract capability keywords from a task description."""
    task_lower = task.lower()
    matched: list[str] = []
    for keyword, capabilities in TASK_KEYWORDS.items():
        if keyword in task_lower:
            matched.extend(capabilities)
    # Also extract individual significant words
    words = re.findall(r"[a-z]{4,}", task_lower)
    stopwords = {
        "with",
        "from",
        "this",
        "that",
        "have",
        "been",
        "will",
        "would",
        "could",
        "should",
        "their",
        "there",
        "where",
        "when",
        "what",
        "which",
        "about",
        "after",
        "before",
        "between",
        "through",
        "during",
        "without",
        "again",
        "further",
        "then",
        "once",
        "using",
        "create",
        "build",
        "make",
        "write",
        "find",
        "help",
        "need",
        "want",
        "like",
        "just",
        "also",
        "very",
        "some",
        "each",
        "every",
        "both",
        "more",
        "most",
        "other",
        "into",
        "over",
        "only",
        "than",
        "them",
        "these",
        "those",
        "such",
        "well",
        "back",
        "much",
        "still",
        "even",
        "here",
        "give",
        "take",
        "come",
        "keep",
        "look",
        "good",
        "best",
        "first",
        "last",
        "long",
        "great",
        "little",
        "right",
        "high",
        "different",
        "small",
        "large",
        "next",
        "early",
        "young",
        "important",
        "public",
        "same",
        "able",
    }
    for w in words:
        if w not in stopwords and len(w) >= 5:
            matched.append(w)
    return list(set(matched))


# ── Scoring functions ────────────────────────────────────────────────────


def _score_task_match(
    session: Session,
    task_keywords: list[str],
    candidate_id: str,
) -> tuple[float, str]:
    """Score how well a candidate matches the task keywords. Returns (score, detail)."""
    if not task_keywords:
        return 0.0, ""

    # Get candidate capabilities
    caps = (
        session.query(CapabilityRow.canonical, CapabilityRow.name)
        .join(VersionRow, CapabilityRow.version_id_fk == VersionRow.id)
        .filter(VersionRow.skill_id == candidate_id)
        .all()
    )
    cap_names = {c.canonical or c.name for c in caps}

    # Get candidate tags
    tags = (
        session.query(TagRow.name)
        .join(VersionRow, TagRow.version_id_fk == VersionRow.id)
        .filter(VersionRow.skill_id == candidate_id)
        .all()
    )
    tag_names = {t.name for t in tags}

    # Get candidate summary/domain
    version = (
        session.query(VersionRow.summary, VersionRow.domain_primary).filter(VersionRow.skill_id == candidate_id).first()
    )
    summary_text = ""
    domain_text = ""
    if version:
        summary_text = (version.summary or "").lower()
        domain_text = (version.domain_primary or "").lower()

    matches = 0
    matched_terms = []
    for kw in task_keywords:
        kw_lower = kw.lower()
        # Check capabilities
        if any(kw_lower in cap for cap in cap_names):
            matches += 2
            matched_terms.append(kw)
        # Check tags
        elif any(kw_lower in tag for tag in tag_names):
            matches += 1.5
            matched_terms.append(kw)
        # Check summary
        elif kw_lower in summary_text:
            matches += 1
            matched_terms.append(kw)
        # Check domain
        elif kw_lower in domain_text:
            matches += 0.5
            matched_terms.append(kw)

    if not matched_terms:
        return 0.0, ""

    score = min(matches / (len(task_keywords) * 2), 1.0)
    detail = f"matched: {', '.join(matched_terms[:5])}"
    return score, detail


def _get_similar_skills(
    session: Session,
    skill_id: str,
    limit: int = 10,
) -> list[tuple[str, float, str]]:
    """Get similar skills from the similarity table."""
    rows = (
        session.query(SimilarityRow)
        .filter((SimilarityRow.skill_a_id == skill_id) | (SimilarityRow.skill_b_id == skill_id))
        .order_by(SimilarityRow.overall_score.desc())
        .limit(limit)
        .all()
    )
    results = []
    for row in rows:
        other_id = row.skill_b_id if row.skill_a_id == skill_id else row.skill_a_id
        results.append((other_id, row.overall_score, row.classification or "similar"))
    return results


def _get_same_category_skills(
    session: Session,
    skill_id: str,
    limit: int = 10,
) -> list[str]:
    """Get skills in the same primary domain/category."""
    version = session.query(VersionRow.domain_primary).filter(VersionRow.skill_id == skill_id).first()
    if not version or not version.domain_primary:
        return []

    domain = version.domain_primary
    rows = (
        session.query(VersionRow.skill_id)
        .join(SkillRow, VersionRow.skill_id == SkillRow.id)
        .filter(
            VersionRow.domain_primary == domain,
            VersionRow.skill_id != skill_id,
            SkillRow.lifecycle != "archived",
        )
        .limit(limit)
        .all()
    )
    return [r.skill_id for r in rows]


def _get_same_ecosystem_skills(
    session: Session,
    source_repo: str,
    exclude_ids: set[str],
    limit: int = 10,
) -> list[str]:
    """Get skills from the same repo/ecosystem."""
    rows = (
        session.query(VersionRow.skill_id)
        .join(SkillRow, VersionRow.skill_id == SkillRow.id)
        .filter(
            VersionRow.source_repo == source_repo,
            SkillRow.lifecycle != "archived",
        )
        .limit(limit + len(exclude_ids))
        .all()
    )
    return [r.skill_id for r in rows if r.skill_id not in exclude_ids][:limit]


def _get_popular_skills(
    session: Session,
    exclude_ids: set[str],
    limit: int = 10,
) -> list[tuple[str, float]]:
    """Get popular skills by repo stars and quality score."""
    rows = (
        session.query(
            SkillRow.id,
            SkillRow.version_count,
        )
        .filter(SkillRow.lifecycle != "archived")
        .order_by(SkillRow.version_count.desc())
        .limit(limit + len(exclude_ids))
        .all()
    )
    return [(r.id, float(r.version_count)) for r in rows if r.id not in exclude_ids][:limit]


def _get_high_quality_skills(
    session: Session,
    exclude_ids: set[str],
    limit: int = 10,
) -> list[tuple[str, float]]:
    """Get highest quality skills from DB."""
    rows = (
        session.query(
            VersionRow.skill_id,
            VersionRow.quality,
        )
        .join(SkillRow, VersionRow.skill_id == SkillRow.id)
        .filter(SkillRow.lifecycle != "archived")
        .all()
    )
    scored = []
    for r in rows:
        if r.skill_id in exclude_ids:
            continue
        quality = r.quality or {}
        if isinstance(quality, dict):
            overall = quality.get("overall_score", 0.0) if quality.get("overall_score") is not None else 0.0
        else:
            overall = 0.0
        scored.append((r.skill_id, float(overall)))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]


# ── Main recommendation function ────────────────────────────────────────


def recommend(
    session: Session,
    task: str = "",
    installed_ids: list[str] | None = None,
    limit: int = 20,
    include_reasons: list[RecommendationReason] | None = None,
) -> RecommendationSet:
    """Generate skill recommendations.

    Args:
        session: Database session
        task: Natural language task description
        installed_ids: IDs of skills the user already has
        limit: Max recommendations to return
        include_reasons: Filter to specific recommendation reasons (None = all)
    """
    installed = set(installed_ids or [])
    all_recs: list[Recommendation] = []

    # ── Task-match recommendations ──
    if task:
        task_keywords = _extract_task_keywords(task)
        if task_keywords:
            # Search candidates by FTS first, then score
            candidates = session.query(SkillRow.id, SkillRow.name).filter(SkillRow.lifecycle != "archived").all()
            for cand in candidates:
                if cand.id in installed:
                    continue
                score, detail = _score_task_match(session, task_keywords, cand.id)
                if score > 0.1:
                    version = session.query(VersionRow).filter(VersionRow.skill_id == cand.id).first()
                    all_recs.append(
                        Recommendation(
                            skill_id=cand.id,
                            name=cand.name,
                            summary=version.summary if version else "",
                            score=score * 0.4,  # task match weight
                            reason=RecommendationReason.TASK_MATCH,
                            reason_detail=detail,
                            source_repo=version.source_repo if version else "",
                            domain=version.domain_primary if version else "",
                            quality_score=_extract_quality_score(version),
                            version_id=version.id if version else 0,
                        )
                    )

    # ── Similar-skill recommendations (from dedup) ──
    for installed_id in list(installed)[:10]:  # limit to first 10 installed
        similar = _get_similar_skills(session, installed_id, limit=5)
        for other_id, sim_score, classification in similar:
            if other_id in installed:
                continue
            version = session.query(VersionRow).filter(VersionRow.skill_id == other_id).first()
            all_recs.append(
                Recommendation(
                    skill_id=other_id,
                    name=version.name if version else other_id,
                    summary=version.summary if version else "",
                    score=sim_score * 0.25,
                    reason=RecommendationReason.SIMILAR,
                    reason_detail=f"similar to {installed_id} ({classification})",
                    source_repo=version.source_repo if version else "",
                    domain=version.domain_primary if version else "",
                    quality_score=_extract_quality_score(version),
                    version_id=version.id if version else 0,
                )
            )

    # ── Same-category recommendations ──
    for installed_id in list(installed)[:5]:
        category_ids = _get_same_category_skills(session, installed_id, limit=5)
        for other_id in category_ids:
            if other_id in installed:
                continue
            version = session.query(VersionRow).filter(VersionRow.skill_id == other_id).first()
            all_recs.append(
                Recommendation(
                    skill_id=other_id,
                    name=version.name if version else other_id,
                    summary=version.summary if version else "",
                    score=0.15,
                    reason=RecommendationReason.SAME_CATEGORY,
                    reason_detail=f"same domain as {installed_id}",
                    source_repo=version.source_repo if version else "",
                    domain=version.domain_primary if version else "",
                    quality_score=_extract_quality_score(version),
                    version_id=version.id if version else 0,
                )
            )

    # ── Same-ecosystem recommendations ──
    for installed_id in list(installed)[:5]:
        version = session.query(VersionRow.source_repo).filter(VersionRow.skill_id == installed_id).first()
        if version and version.source_repo:
            eco_ids = _get_same_ecosystem_skills(session, version.source_repo, installed, limit=3)
            for other_id in eco_ids:
                other_version = session.query(VersionRow).filter(VersionRow.skill_id == other_id).first()
                all_recs.append(
                    Recommendation(
                        skill_id=other_id,
                        name=other_version.name if other_version else other_id,
                        summary=other_version.summary if other_version else "",
                        score=0.10,
                        reason=RecommendationReason.SAME_ECOSYSTEM,
                        reason_detail=f"from {version.source_repo}",
                        source_repo=version.source_repo,
                        domain=other_version.domain_primary if other_version else "",
                        quality_score=_extract_quality_score(other_version),
                        version_id=other_version.id if other_version else 0,
                    )
                )

    # ── Popular / high-quality fallbacks ──
    if not installed or len(all_recs) < limit:
        popular = _get_popular_skills(session, installed, limit=10)
        for skill_id, pop_score in popular:
            # Avoid duplicates
            if any(r.skill_id == skill_id for r in all_recs):
                continue
            version = session.query(VersionRow).filter(VersionRow.skill_id == skill_id).first()
            norm_score = min(pop_score / 10.0, 1.0) * 0.15
            all_recs.append(
                Recommendation(
                    skill_id=skill_id,
                    name=version.name if version else skill_id,
                    summary=version.summary if version else "",
                    score=norm_score,
                    reason=RecommendationReason.POPULAR,
                    reason_detail=f"version_count={int(pop_score)}",
                    source_repo=version.source_repo if version else "",
                    domain=version.domain_primary if version else "",
                    quality_score=_extract_quality_score(version),
                    version_id=version.id if version else 0,
                )
            )

    if not installed or len(all_recs) < limit:
        high_q = _get_high_quality_skills(session, installed, limit=10)
        for skill_id, q_score in high_q:
            if any(r.skill_id == skill_id for r in all_recs):
                continue
            version = session.query(VersionRow).filter(VersionRow.skill_id == skill_id).first()
            all_recs.append(
                Recommendation(
                    skill_id=skill_id,
                    name=version.name if version else skill_id,
                    summary=version.summary if version else "",
                    score=q_score * 0.20,
                    reason=RecommendationReason.HIGH_QUALITY,
                    reason_detail=f"quality={q_score:.2f}",
                    source_repo=version.source_repo if version else "",
                    domain=version.domain_primary if version else "",
                    quality_score=q_score,
                    version_id=version.id if version else 0,
                )
            )

    # ── Deduplicate by skill_id, keeping highest score ──
    best: dict[str, Recommendation] = {}
    for rec in all_recs:
        if rec.skill_id in installed:
            continue
        if include_reasons and rec.reason not in include_reasons:
            continue
        existing = best.get(rec.skill_id)
        if not existing or rec.score > existing.score:
            best[rec.skill_id] = rec

    # Sort by score descending
    sorted_recs = sorted(best.values(), key=lambda r: r.score, reverse=True)

    # Build facets
    facets: dict[str, int] = {}
    for rec in sorted_recs:
        reason_key = rec.reason.value
        facets[reason_key] = facets.get(reason_key, 0) + 1

    return RecommendationSet(
        task=task,
        installed_ids=list(installed),
        recommendations=sorted_recs[: limit * 3],  # keep more for filtering
        facets=facets,
    )


def _extract_quality_score(version: VersionRow | None) -> float:
    """Extract overall quality score from version quality JSON."""
    if not version or not version.quality:
        return 0.0
    quality = version.quality
    if isinstance(quality, dict):
        val = quality.get("overall_score")
        return float(val) if val is not None else 0.0
    return 0.0


def recommend_for_skill(
    session: Session,
    skill_id: str,
    limit: int = 10,
) -> list[Recommendation]:
    """Recommend skills similar/complementary to a specific skill."""
    recs: list[Recommendation] = []

    # Similar skills
    similar = _get_similar_skills(session, skill_id, limit=limit)
    for other_id, score, classification in similar:
        version = session.query(VersionRow).filter(VersionRow.skill_id == other_id).first()
        recs.append(
            Recommendation(
                skill_id=other_id,
                name=version.name if version else other_id,
                summary=version.summary if version else "",
                score=score,
                reason=RecommendationReason.SIMILAR,
                reason_detail=f"{classification}",
                source_repo=version.source_repo if version else "",
                domain=version.domain_primary if version else "",
                quality_score=_extract_quality_score(version),
                version_id=version.id if version else 0,
            )
        )

    # Same category
    category_ids = _get_same_category_skills(session, skill_id, limit=limit)
    seen = {r.skill_id for r in recs}
    for other_id in category_ids:
        if other_id in seen:
            continue
        version = session.query(VersionRow).filter(VersionRow.skill_id == other_id).first()
        recs.append(
            Recommendation(
                skill_id=other_id,
                name=version.name if version else other_id,
                summary=version.summary if version else "",
                score=0.15,
                reason=RecommendationReason.SAME_CATEGORY,
                reason_detail="same domain",
                source_repo=version.source_repo if version else "",
                domain=version.domain_primary if version else "",
                quality_score=_extract_quality_score(version),
                version_id=version.id if version else 0,
            )
        )

    recs.sort(key=lambda r: r.score, reverse=True)
    return recs[:limit]
