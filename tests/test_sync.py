"""Tests for incremental sync and change tracking."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from skillsbank.db.engine import get_session
from skillsbank.db.persistence_models import Base, CapabilityRow, SkillRow, TagRow, VersionRow
from skillsbank.sync import (
    ChangeType,
    IncomingSkill,
    apply_sync,
    compute_content_hash,
    compute_skill_hash,
    detect_changes,
    get_skill_history,
    get_sync_history,
)


@pytest.fixture
def db_session():
    """Create a fresh in-memory DB for each test."""
    engine = sa.create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    with get_session(engine) as session:
        yield session


def _make_incoming(
    skill_id="sk-1",
    name="test-skill",
    summary="A test skill",
    source_path="skills/test/SKILL.md",
    source_repo="owner/repo",
    raw_content=None,
    capabilities=None,
    tags=None,
    domain=None,
) -> IncomingSkill:
    return IncomingSkill(
        skill_id=skill_id,
        name=name,
        summary=summary,
        source_path=source_path,
        source_repo=source_repo,
        raw_content=raw_content,
        capabilities=capabilities or [],
        tags=tags or [],
        domain=domain,
    )


def _seed_skill(session, skill_id="sk-1", name="test-skill", summary="A test skill"):
    """Seed a skill + version into the DB."""
    skill = SkillRow(
        id=skill_id,
        name=name,
        display_name=name,
        lifecycle="current",
        is_current=True,
        primary_source="owner/repo",
        primary_path="skills/test/SKILL.md",
        version_count=1,
    )
    session.add(skill)
    session.flush()

    from skillsbank.sync import compute_skill_hash

    content_hash = compute_skill_hash(name, summary, "skills/test/SKILL.md")
    version = VersionRow(
        skill_id=skill_id,
        version_id=f"{skill_id}-v1",
        name=name,
        summary=summary,
        source_repo="owner/repo",
        source_path="skills/test/SKILL.md",
        source_content_hash=content_hash,
    )
    session.add(version)
    session.flush()
    return skill, version


# ── Hash computation tests ───────────────────────────────────────────────────


class TestHashing:
    def test_content_hash_deterministic(self):
        h1 = compute_content_hash("hello world")
        h2 = compute_content_hash("hello world")
        assert h1 == h2

    def test_content_hash_differs(self):
        h1 = compute_content_hash("hello")
        h2 = compute_content_hash("world")
        assert h1 != h2

    def test_skill_hash_includes_name(self):
        h1 = compute_skill_hash("skill-a", "summary", "path")
        h2 = compute_skill_hash("skill-b", "summary", "path")
        assert h1 != h2

    def test_skill_hash_includes_summary(self):
        h1 = compute_skill_hash("skill", "summary-a", "path")
        h2 = compute_skill_hash("skill", "summary-b", "path")
        assert h1 != h2

    def test_skill_hash_includes_path(self):
        h1 = compute_skill_hash("skill", "summary", "path-a")
        h2 = compute_skill_hash("skill", "summary", "path-b")
        assert h1 != h2

    def test_skill_hash_with_raw_content(self):
        h1 = compute_skill_hash("skill", "summary", "path", "content-a")
        h2 = compute_skill_hash("skill", "summary", "path", "content-b")
        assert h1 != h2

    def test_skill_hash_without_raw_content(self):
        h1 = compute_skill_hash("skill", "summary", "path")
        h2 = compute_skill_hash("skill", "summary", "path", None)
        assert h1 == h2


# ── Change detection tests ──────────────────────────────────────────────────


class TestDetectChanges:
    def test_empty_incoming(self, db_session):
        """No incoming skills → no changes."""
        result = detect_changes(db_session, [])
        assert result.skills_added == 0
        assert result.skills_modified == 0
        assert result.skills_removed == 0

    def test_new_skill_detected(self, db_session):
        """Incoming skill not in DB → ADDED."""
        incoming = [_make_incoming()]
        result = detect_changes(db_session, incoming)

        assert result.skills_added == 1
        assert result.skills_modified == 0
        assert result.skills_removed == 0
        assert len(result.changes) == 1
        assert result.changes[0].change_type == ChangeType.ADDED

    def test_unchanged_skill_detected(self, db_session):
        """Incoming skill identical to DB → UNCHANGED."""
        _seed_skill(db_session)
        incoming = [_make_incoming()]
        result = detect_changes(db_session, incoming)

        assert result.skills_unchanged == 1
        assert result.skills_added == 0
        assert result.skills_modified == 0

    def test_modified_summary_detected(self, db_session):
        """Incoming skill with changed summary → MODIFIED."""
        _seed_skill(db_session)
        incoming = [_make_incoming(summary="Updated summary")]
        result = detect_changes(db_session, incoming)

        assert result.skills_modified == 1
        assert any(c.change_type == ChangeType.MODIFIED and c.field_name == "summary" for c in result.changes)

    def test_modified_name_detected(self, db_session):
        """Incoming skill with changed name → MODIFIED."""
        _seed_skill(db_session)
        incoming = [_make_incoming(name="renamed-skill")]
        result = detect_changes(db_session, incoming)

        assert result.skills_modified == 1
        assert any(c.change_type == ChangeType.MODIFIED and c.field_name == "name" for c in result.changes)

    def test_moved_path_detected(self, db_session):
        """Incoming skill with changed path → MOVED."""
        _seed_skill(db_session)
        incoming = [_make_incoming(source_path="new/path/SKILL.md")]
        result = detect_changes(db_session, incoming)

        assert result.skills_modified == 1
        assert any(c.change_type == ChangeType.MOVED for c in result.changes)

    def test_removed_skill_detected(self, db_session):
        """Skill in DB but not incoming → REMOVED."""
        _seed_skill(db_session, skill_id="sk-old")
        result = detect_changes(db_session, [])

        assert result.skills_removed == 1
        assert any(c.change_type == ChangeType.REMOVED for c in result.changes)

    def test_mixed_changes(self, db_session):
        """Multiple skills with add, modify, remove, unchanged."""
        _seed_skill(db_session, skill_id="sk-keep", name="keep")
        _seed_skill(db_session, skill_id="sk-mod", name="modify-me")
        _seed_skill(db_session, skill_id="sk-del", name="delete-me")

        incoming = [
            _make_incoming(skill_id="sk-keep", name="keep"),  # unchanged
            _make_incoming(skill_id="sk-mod", name="modify-me", summary="new!"),  # modified
            _make_incoming(skill_id="sk-new", name="brand-new"),  # added
            # sk-del removed
        ]
        result = detect_changes(db_session, incoming)

        assert result.skills_added == 1
        assert result.skills_modified == 1
        assert result.skills_removed == 1
        assert result.skills_unchanged == 1


# ── Apply sync tests ────────────────────────────────────────────────────────


class TestApplySync:
    def test_apply_addition(self, db_session):
        """New skill gets added to DB."""
        incoming = [_make_incoming()]
        result = apply_sync(db_session, incoming)

        assert result.skills_added == 1
        skill = db_session.get(SkillRow, "sk-1")
        assert skill is not None
        assert skill.name == "test-skill"
        assert skill.version_count == 1

    def test_apply_modification(self, db_session):
        """Modified skill gets new version."""
        _seed_skill(db_session)
        incoming = [_make_incoming(summary="Updated!")]
        result = apply_sync(db_session, incoming)

        assert result.skills_modified == 1
        skill = db_session.get(SkillRow, "sk-1")
        assert skill.version_count == 2

    def test_apply_removal_archives(self, db_session):
        """Removed skill gets archived, not deleted."""
        _seed_skill(db_session)
        result = apply_sync(db_session, [])

        assert result.skills_removed == 1
        skill = db_session.get(SkillRow, "sk-1")
        assert skill is not None
        assert skill.lifecycle == "archived"
        assert skill.is_current is False

    def test_dry_run_no_changes(self, db_session):
        """Dry run detects but doesn't apply changes."""
        incoming = [_make_incoming()]
        result = apply_sync(db_session, incoming, dry_run=True)

        assert result.skills_added == 1
        skill = db_session.get(SkillRow, "sk-1")
        assert skill is None  # not actually added

    def test_capabilities_added(self, db_session):
        """Capabilities get stored with new skill."""
        incoming = [_make_incoming(capabilities=["code-review", "testing"])]
        apply_sync(db_session, incoming)

        caps = (
            db_session.execute(sa.select(CapabilityRow).where(CapabilityRow.version_id_fk.is_not(None))).scalars().all()
        )
        cap_names = {c.name for c in caps}
        assert "code-review" in cap_names
        assert "testing" in cap_names

    def test_tags_added(self, db_session):
        """Tags get stored with new skill."""
        incoming = [_make_incoming(tags=["python", "testing"])]
        apply_sync(db_session, incoming)

        tags = db_session.execute(sa.select(TagRow).where(TagRow.version_id_fk.is_not(None))).scalars().all()
        tag_names = {t.name for t in tags}
        assert "python" in tag_names
        assert "testing" in tag_names

    def test_changelog_stored(self, db_session):
        """Sync changes get stored in changelog."""
        incoming = [_make_incoming()]
        result = apply_sync(db_session, incoming)

        history = get_sync_history(db_session)
        assert len(history) >= 1
        assert history[0]["sync_id"] == result.sync_id

    def test_idempotent_sync(self, db_session):
        """Running same sync twice produces no changes on second run."""
        incoming = [_make_incoming()]
        apply_sync(db_session, incoming)

        result2 = apply_sync(db_session, incoming)
        assert result2.skills_added == 0
        assert result2.skills_modified == 0
        assert result2.skills_unchanged == 1


# ── History tests ───────────────────────────────────────────────────────────


class TestHistory:
    def test_get_sync_history_empty(self, db_session):
        """No syncs yet → empty history."""
        history = get_sync_history(db_session)
        assert history == []

    def test_get_skill_history(self, db_session):
        """Get history for a specific skill."""
        incoming = [_make_incoming()]
        apply_sync(db_session, incoming)

        # Modify it
        incoming2 = [_make_incoming(summary="changed")]
        apply_sync(db_session, incoming2)

        history = get_skill_history(db_session, "sk-1")
        assert len(history) >= 2  # ADDED + MODIFIED
        change_types = {h["change_type"] for h in history}
        assert "ADDED" in change_types

    def test_get_skill_history_empty(self, db_session):
        """No history for unknown skill."""
        history = get_skill_history(db_session, "nonexistent")
        assert history == []
