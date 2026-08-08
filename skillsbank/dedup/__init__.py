"""Duplicate detection engine — multi-dimensional skill similarity.

Dimensions compared:
  1. name       — normalized string similarity (SequenceMatcher)
  2. summary    — token-set Jaccard overlap
  3. capabilities — canonical capability Jaccard overlap
  4. content    — exact content-hash match
  5. source     — same repo + path bonus

Classification thresholds:
  EXACT_DUPLICATE   : content_hash match OR overall >= 0.95
  NEAR_DUPLICATE    : overall >= 0.80
  FUNCTIONAL_OVERLAP: overall >= 0.60
  RELATED           : overall >= 0.40
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from skillsbank.db.persistence_models import (
    CapabilityRow,
    RelationshipRow,
    SimilarityRow,
    SkillRow,
    VersionRow,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLASSIFICATION_THRESHOLDS = {
    "EXACT_DUPLICATE": 0.95,
    "NEAR_DUPLICATE": 0.80,
    "FUNCTIONAL_OVERLAP": 0.60,
    "RELATED": 0.40,
}

DIMENSION_WEIGHTS = {
    "name": 0.30,
    "summary": 0.20,
    "capabilities": 0.35,
    "content": 0.10,
    "source": 0.05,
}

TOKEN_RE = re.compile(r"\w+", re.UNICODE)


# ---------------------------------------------------------------------------
# Skill fingerprint — pre-computed for efficient pairwise comparison
# ---------------------------------------------------------------------------


@dataclass
class SkillFingerprint:
    """Pre-computed similarity inputs for a single skill."""

    skill_id: str
    name_normalized: str
    summary_tokens: set[str]
    capability_names: set[str]
    content_hash: str | None
    source_key: str  # "owner/repo/path"


def _normalize_name(name: str) -> str:
    """Lowercase, strip non-alphanumeric, collapse whitespace."""
    return re.sub(r"[^a-z0-9\s]", "", name.lower()).strip()


def _tokenize(text: str | None) -> set[str]:
    """Extract lowercase word tokens."""
    if not text:
        return set()
    return {m.group().lower() for m in TOKEN_RE.finditer(text)}


def build_fingerprint(
    skill: SkillRow,
    version: VersionRow | None,
    caps: list[CapabilityRow],
) -> SkillFingerprint:
    """Build a fingerprint from DB rows."""
    summary = version.summary if version else None
    content_hash = version.source_content_hash if version else None
    source_repo = version.source_repo if version else ""
    source_path = version.source_path if version else ""

    return SkillFingerprint(
        skill_id=skill.id,
        name_normalized=_normalize_name(skill.name or skill.display_name or ""),
        summary_tokens=_tokenize(summary),
        capability_names={c.canonical or c.name.lower() for c in caps},
        content_hash=content_hash,
        source_key=f"{source_repo}/{source_path}".lower(),
    )


# ---------------------------------------------------------------------------
# Similarity scorers — one per dimension
# ---------------------------------------------------------------------------


def score_name(a: SkillFingerprint, b: SkillFingerprint) -> float:
    """String similarity of normalized names."""
    if not a.name_normalized or not b.name_normalized:
        return 0.0
    return SequenceMatcher(None, a.name_normalized, b.name_normalized).ratio()


def score_summary(a: SkillFingerprint, b: SkillFingerprint) -> float:
    """Jaccard overlap of summary token sets."""
    if not a.summary_tokens or not b.summary_tokens:
        return 0.0
    intersection = a.summary_tokens & b.summary_tokens
    union = a.summary_tokens | b.summary_tokens
    return len(intersection) / len(union) if union else 0.0


def score_capabilities(a: SkillFingerprint, b: SkillFingerprint) -> float:
    """Jaccard overlap of canonical capability names."""
    if not a.capability_names or not b.capability_names:
        return 0.0
    intersection = a.capability_names & b.capability_names
    union = a.capability_names | b.capability_names
    return len(intersection) / len(union) if union else 0.0


def score_content(a: SkillFingerprint, b: SkillFingerprint) -> float:
    """1.0 if content hashes match and are non-empty, else 0.0."""
    if a.content_hash and b.content_hash and a.content_hash == b.content_hash:
        return 1.0
    return 0.0


def score_source(a: SkillFingerprint, b: SkillFingerprint) -> float:
    """1.0 if same source key (same repo + path), else 0.0."""
    if a.source_key and b.source_key and a.source_key == b.source_key:
        return 1.0
    return 0.0


DIMENSION_SCORERS = {
    "name": score_name,
    "summary": score_summary,
    "capabilities": score_capabilities,
    "content": score_content,
    "source": score_source,
}


# ---------------------------------------------------------------------------
# Pairwise comparison result
# ---------------------------------------------------------------------------


@dataclass
class ComparisonResult:
    """Full similarity comparison between two skills."""

    skill_a_id: str
    skill_b_id: str
    dimensions: dict[str, float] = field(default_factory=dict)
    overall_score: float = 0.0
    classification: str = "UNRELATED"

    def to_similarity_row(self) -> dict:
        """Convert to dict matching SimilarityRow columns."""
        return {
            "skill_a_id": self.skill_a_id,
            "skill_b_id": self.skill_b_id,
            "overall_score": round(self.overall_score, 6),
            "dimensions": self.dimensions,
            "classification": self.classification,
            "computed_at": datetime.now(UTC),
        }

    def to_relationship_row(self, rel_type: str = "DUPLICATE") -> dict | None:
        """Convert to RelationshipRow dict if classification warrants it."""
        if self.classification in ("EXACT_DUPLICATE", "NEAR_DUPLICATE"):
            return {
                "source_id": self.skill_a_id,
                "target_id": self.skill_b_id,
                "rel_type": rel_type,
                "confidence": round(self.overall_score, 4),
                "evidence": self.dimensions,
                "created_at": datetime.now(UTC),
            }
        return None


# ---------------------------------------------------------------------------
# Comparison engine
# ---------------------------------------------------------------------------


def compare(
    a: SkillFingerprint,
    b: SkillFingerprint,
    weights: dict[str, float] | None = None,
) -> ComparisonResult:
    """Compute multi-dimensional similarity between two fingerprints."""
    w = weights or DIMENSION_WEIGHTS
    dims: dict[str, float] = {}

    for dim_name, scorer in DIMENSION_SCORERS.items():
        dims[dim_name] = round(scorer(a, b), 6)

    overall = sum(dims[d] * w.get(d, 0.0) for d in dims)

    # Content-hash exact match overrides
    if dims.get("content", 0) >= 1.0:
        overall = max(overall, 0.99)
    # Same source with high name match boosts
    if dims.get("source", 0) >= 1.0 and dims.get("name", 0) > 0.7:
        overall = max(overall, 0.90)

    classification = "UNRELATED"
    for cls_name, threshold in sorted(CLASSIFICATION_THRESHOLDS.items(), key=lambda x: -x[1]):
        if overall >= threshold:
            classification = cls_name
            break

    return ComparisonResult(
        skill_a_id=a.skill_id,
        skill_b_id=b.skill_id,
        dimensions=dims,
        overall_score=round(overall, 6),
        classification=classification,
    )


# ---------------------------------------------------------------------------
# Batch detection — full DB scan
# ---------------------------------------------------------------------------


@dataclass
class DetectionStats:
    """Results from a full duplicate detection run."""

    skills_scanned: int = 0
    pairs_compared: int = 0
    exact_duplicates: int = 0
    near_duplicates: int = 0
    functional_overlaps: int = 0
    related: int = 0
    similarities_stored: int = 0
    relationships_stored: int = 0
    duration_seconds: float = 0.0


def _load_fingerprints(session: Session) -> list[SkillFingerprint]:
    """Load all skills and build fingerprints."""
    skills = session.execute(select(SkillRow)).scalars().all()
    fingerprints: list[SkillFingerprint] = []

    for skill in skills:
        # Get current version (or first)
        version = None
        if skill.current_version_id:
            version = session.execute(
                select(VersionRow).where(VersionRow.version_id == skill.current_version_id)
            ).scalar_one_or_none()
        if version is None:
            version = session.execute(
                select(VersionRow).where(VersionRow.skill_id == skill.id).limit(1)
            ).scalar_one_or_none()

        # Get capabilities
        caps: list[CapabilityRow] = []
        if version:
            caps = list(
                session.execute(select(CapabilityRow).where(CapabilityRow.version_id_fk == version.id)).scalars().all()
            )

        fingerprints.append(build_fingerprint(skill, version, caps))

    return fingerprints


def detect_duplicates(
    session: Session,
    min_score: float = 0.40,
    weights: dict[str, float] | None = None,
    batch_size: int = 500,
) -> DetectionStats:
    """Run full pairwise duplicate detection on all skills in DB.

    Only computes upper triangle (a < b) to avoid redundant comparisons.
    Stores results in similarities and relationships tables.
    """
    import time

    start = time.monotonic()
    stats = DetectionStats()

    fps = _load_fingerprints(session)
    stats.skills_scanned = len(fps)

    # Pre-group by content_hash for exact-match fast path
    hash_groups: dict[str, list[int]] = {}
    for i, fp in enumerate(fps):
        if fp.content_hash:
            hash_groups.setdefault(fp.content_hash, []).append(i)

    # Batch results
    sim_batch: list[dict] = []
    rel_batch: list[dict] = []

    def flush_batches():
        nonlocal sim_batch, rel_batch
        if sim_batch:
            session.bulk_insert_mappings(SimilarityRow, sim_batch)
            stats.similarities_stored += len(sim_batch)
            sim_batch = []
        if rel_batch:
            session.bulk_insert_mappings(RelationshipRow, rel_batch)
            stats.relationships_stored += len(rel_batch)
            rel_batch = []
        session.flush()

    n = len(fps)
    for i in range(n):
        for j in range(i + 1, n):
            stats.pairs_compared += 1

            result = compare(fps[i], fps[j], weights)

            if result.overall_score >= min_score:
                sim_batch.append(result.to_similarity_row())

                rel = result.to_relationship_row()
                if rel:
                    rel_batch.append(rel)

                if result.classification == "EXACT_DUPLICATE":
                    stats.exact_duplicates += 1
                elif result.classification == "NEAR_DUPLICATE":
                    stats.near_duplicates += 1
                elif result.classification == "FUNCTIONAL_OVERLAP":
                    stats.functional_overlaps += 1
                elif result.classification == "RELATED":
                    stats.related += 1

            if len(sim_batch) >= batch_size:
                flush_batches()

    flush_batches()

    stats.duration_seconds = round(time.monotonic() - start, 3)
    return stats


def get_duplicates_for_skill(
    session: Session,
    skill_id: str,
    min_score: float = 0.40,
) -> list[dict]:
    """Get all known duplicates/similar skills for a given skill ID."""
    rows = (
        session.execute(
            select(SimilarityRow).where(
                and_(
                    SimilarityRow.skill_a_id == skill_id,
                    SimilarityRow.overall_score >= min_score,
                )
            )
        )
        .scalars()
        .all()
    )

    # Also check reverse direction
    rows += (
        session.execute(
            select(SimilarityRow).where(
                and_(
                    SimilarityRow.skill_b_id == skill_id,
                    SimilarityRow.overall_score >= min_score,
                )
            )
        )
        .scalars()
        .all()
    )

    return [
        {
            "other_skill_id": r.skill_b_id if r.skill_a_id == skill_id else r.skill_a_id,
            "overall_score": r.overall_score,
            "classification": r.classification,
            "dimensions": r.dimensions,
        }
        for r in rows
    ]
