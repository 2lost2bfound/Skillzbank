"""Tests for duplicate detection engine."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from skillsbank.db.base import Base
from skillsbank.db.persistence_models import (
    CapabilityRow,
    RelationshipRow,
    SimilarityRow,
    SkillRow,
    VersionRow,
)
from skillsbank.dedup import (
    SkillFingerprint,
    compare,
    detect_duplicates,
    get_duplicates_for_skill,
    score_capabilities,
    score_content,
    score_name,
    score_source,
    score_summary,
)


@pytest.fixture
def db():
    """In-memory SQLite database."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def _insert_skill(
    session: Session,
    skill_id: str,
    name: str,
    summary: str = "",
    caps: list[str] | None = None,
    content_hash: str | None = None,
    source_repo: str = "owner/repo",
    source_path: str = "skills/foo/SKILL.md",
):
    """Helper to insert a minimal skill with version and capabilities."""
    skill = SkillRow(
        id=skill_id,
        canonical_key=name.lower().replace(" ", "-"),
        name=name,
        display_name=name,
        lifecycle="active",
        is_current=True,
        primary_source=source_repo,
        primary_path=source_path,
        metadata_quality="unknown",
        version_count=1,
        current_version_id=f"v-{skill_id}",
    )
    session.add(skill)

    version = VersionRow(
        skill_id=skill_id,
        version_id=f"v-{skill_id}",
        name=name,
        summary=summary,
        source_repo=source_repo,
        source_path=source_path,
        source_content_hash=content_hash,
        domain_primary="unknown",
        imported_at=datetime.now(UTC),
    )
    session.add(version)
    session.flush()

    for cap_name in caps or []:
        session.add(
            CapabilityRow(
                version_id_fk=version.id,
                name=cap_name,
                canonical=cap_name.lower(),
            )
        )
    session.flush()


# ---------------------------------------------------------------------------
# Unit tests — individual scorers
# ---------------------------------------------------------------------------


class TestScorers:
    def test_score_name_identical(self):
        a = SkillFingerprint("a", "code review", set(), set(), None, "")
        b = SkillFingerprint("b", "code review", set(), set(), None, "")
        assert score_name(a, b) == pytest.approx(1.0)

    def test_score_name_similar(self):
        a = SkillFingerprint("a", "code review tool", set(), set(), None, "")
        b = SkillFingerprint("b", "code review helper", set(), set(), None, "")
        s = score_name(a, b)
        assert 0.6 < s < 1.0

    def test_score_name_different(self):
        a = SkillFingerprint("a", "security audit", set(), set(), None, "")
        b = SkillFingerprint("b", "animation maker", set(), set(), None, "")
        assert score_name(a, b) < 0.3

    def test_score_summary_jaccard(self):
        a = SkillFingerprint("a", "", {"review", "code", "quality"}, set(), None, "")
        b = SkillFingerprint("b", "", {"review", "code", "test"}, set(), None, "")
        # intersection={review,code}=2, union={review,code,quality,test}=4 → 0.5
        assert score_summary(a, b) == pytest.approx(0.5)

    def test_score_summary_empty(self):
        a = SkillFingerprint("a", "", set(), set(), None, "")
        b = SkillFingerprint("b", "", {"review"}, set(), None, "")
        assert score_summary(a, b) == 0.0

    def test_score_capabilities_jaccard(self):
        a = SkillFingerprint("a", "", set(), {"code-review", "testing"}, None, "")
        b = SkillFingerprint("b", "", set(), {"code-review", "debugging"}, None, "")
        # intersection=1, union=3 → 0.333
        assert score_capabilities(a, b) == pytest.approx(1 / 3, rel=1e-3)

    def test_score_content_match(self):
        a = SkillFingerprint("a", "", set(), set(), "abc123", "")
        b = SkillFingerprint("b", "", set(), set(), "abc123", "")
        assert score_content(a, b) == 1.0

    def test_score_content_mismatch(self):
        a = SkillFingerprint("a", "", set(), set(), "abc123", "")
        b = SkillFingerprint("b", "", set(), set(), "def456", "")
        assert score_content(a, b) == 0.0

    def test_score_content_none(self):
        a = SkillFingerprint("a", "", set(), set(), None, "")
        b = SkillFingerprint("b", "", set(), set(), None, "")
        assert score_content(a, b) == 0.0

    def test_score_source_same(self):
        a = SkillFingerprint("a", "", set(), set(), None, "owner/repo/skills/foo")
        b = SkillFingerprint("b", "", set(), set(), None, "owner/repo/skills/foo")
        assert score_source(a, b) == 1.0

    def test_score_source_different(self):
        a = SkillFingerprint("a", "", set(), set(), None, "owner/repo/skills/foo")
        b = SkillFingerprint("b", "", set(), set(), None, "other/repo/skills/bar")
        assert score_content(a, b) == 0.0


# ---------------------------------------------------------------------------
# Unit tests — pairwise comparison
# ---------------------------------------------------------------------------


class TestCompare:
    def test_exact_duplicate_via_content_hash(self):
        a = SkillFingerprint("a", "security scan", {"scan", "vuln"}, {"security"}, "hash1", "r/p")
        b = SkillFingerprint("b", "security scanner", {"scan", "vulnerability"}, {"security"}, "hash1", "r/q")
        result = compare(a, b)
        assert result.classification == "EXACT_DUPLICATE"
        assert result.overall_score >= 0.95

    def test_near_duplicate_high_similarity(self):
        a = SkillFingerprint("a", "code review", {"review", "code", "quality"}, {"code-review"}, None, "r1")
        b = SkillFingerprint("b", "code review tool", {"review", "code", "quality"}, {"code-review"}, None, "r1")
        result = compare(a, b)
        assert result.classification in ("EXACT_DUPLICATE", "NEAR_DUPLICATE")
        assert result.overall_score >= 0.80

    def test_functional_overlap(self):
        a = SkillFingerprint(
            "a",
            "security audit tool",
            {"security", "audit", "vulnerability", "scan"},
            {"security-audit", "vulnerability-scanning"},
            None,
            "r1",
        )
        b = SkillFingerprint(
            "b",
            "security testing tool",
            {"security", "penetration", "test", "scan"},
            {"security-testing", "vulnerability-scanning"},
            None,
            "r2",
        )
        result = compare(a, b)
        assert result.overall_score > 0.0
        # Shared capabilities
        assert result.dimensions["capabilities"] > 0.0
        # Shared summary tokens
        assert result.dimensions["summary"] > 0.0

    def test_unrelated_skills(self):
        a = SkillFingerprint("a", "animation maker", {"animation", "svg"}, {"animation"}, None, "r1")
        b = SkillFingerprint("b", "database schema", {"database", "sql"}, {"database-design"}, None, "r2")
        result = compare(a, b)
        assert result.classification == "UNRELATED"
        assert result.overall_score < 0.40

    def test_source_bonus(self):
        a = SkillFingerprint("a", "code review", {"review"}, {"code-review"}, None, "owner/repo/skills/x")
        b = SkillFingerprint("b", "code review", {"review"}, {"code-review"}, None, "owner/repo/skills/x")
        result = compare(a, b)
        assert result.overall_score >= 0.90

    def test_dimensions_present(self):
        a = SkillFingerprint("a", "test", {"test"}, {"testing"}, None, "r1")
        b = SkillFingerprint("b", "test", {"test"}, {"testing"}, None, "r2")
        result = compare(a, b)
        assert set(result.dimensions.keys()) == {"name", "summary", "capabilities", "content", "source"}


# ---------------------------------------------------------------------------
# Integration tests — DB-level detection
# ---------------------------------------------------------------------------


class TestDetection:
    def test_detect_exact_duplicates(self, db):
        _insert_skill(db, "s1", "Security Scanner", "Scan for vulnerabilities", ["security"], content_hash="hash-abc")
        _insert_skill(
            db, "s2", "Security Scanner Pro", "Scan for security vulnerabilities", ["security"], content_hash="hash-abc"
        )
        _insert_skill(db, "s3", "Animation Maker", "Create SVG animations", ["animation"])
        db.commit()

        stats = detect_duplicates(db, min_score=0.0)
        assert stats.skills_scanned == 3
        assert stats.pairs_compared == 3  # C(3,2)=3
        assert stats.exact_duplicates >= 1  # s1==s2 via content_hash

    def test_detect_near_duplicates(self, db):
        _insert_skill(db, "s1", "Code Review Tool", "Automated code review for quality", ["code-review"])
        _insert_skill(db, "s2", "Code Review Helper", "Automated code review for quality", ["code-review"])
        _insert_skill(db, "s3", "Database Schema", "Design database schemas", ["database-design"])
        db.commit()

        stats = detect_duplicates(db, min_score=0.40)
        # s1 and s2 should be near-duplicates
        assert stats.near_duplicates + stats.exact_duplicates >= 1

    def test_detect_unrelated_not_flagged(self, db):
        _insert_skill(db, "s1", "Security Audit", "Comprehensive security testing", ["security-audit"])
        _insert_skill(db, "s2", "Animation Creator", "Make SVG animations", ["animation"])
        db.commit()

        stats = detect_duplicates(db, min_score=0.80)
        assert stats.exact_duplicates == 0
        assert stats.near_duplicates == 0

    def test_similarity_rows_stored(self, db):
        _insert_skill(db, "s1", "Test Skill", "A test skill", ["testing"], content_hash="h1")
        _insert_skill(db, "s2", "Test Skill Clone", "A test skill", ["testing"], content_hash="h1")
        db.commit()

        detect_duplicates(db, min_score=0.0)
        rows = db.query(SimilarityRow).all()
        assert len(rows) >= 1
        row = rows[0]
        assert row.overall_score > 0
        assert row.classification is not None
        assert row.dimensions is not None

    def test_relationship_rows_for_duplicates(self, db):
        _insert_skill(db, "s1", "Skill A", "Description A", ["cap-a"], content_hash="same-hash")
        _insert_skill(db, "s2", "Skill A Copy", "Description A", ["cap-a"], content_hash="same-hash")
        db.commit()

        detect_duplicates(db, min_score=0.0)
        rels = db.query(RelationshipRow).all()
        # At least one DUPLICATE relationship
        assert len(rels) >= 1
        assert rels[0].rel_type == "DUPLICATE"
        assert rels[0].confidence >= 0.95

    def test_get_duplicates_for_skill(self, db):
        _insert_skill(db, "s1", "My Skill", "Does things", ["cap-a"], content_hash="h1")
        _insert_skill(db, "s2", "My Skill Copy", "Does things", ["cap-a"], content_hash="h1")
        _insert_skill(db, "s3", "Other Skill", "Different", ["cap-b"])
        db.commit()

        detect_duplicates(db, min_score=0.0)
        dups = get_duplicates_for_skill(db, "s1", min_score=0.40)
        dup_ids = [d["other_skill_id"] for d in dups]
        assert "s2" in dup_ids
        assert "s3" not in dup_ids

    def test_empty_db(self, db):
        stats = detect_duplicates(db)
        assert stats.skills_scanned == 0
        assert stats.pairs_compared == 0
        assert stats.duration_seconds >= 0

    def test_single_skill(self, db):
        _insert_skill(db, "s1", "Only Skill", "Lonely")
        db.commit()
        stats = detect_duplicates(db)
        assert stats.skills_scanned == 1
        assert stats.pairs_compared == 0
