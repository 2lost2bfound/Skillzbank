"""Tests for Phase 2: SQLite persistence and round-trip integrity.

These are *integration* tests — they import the full 5.67 MB registry
and are therefore slow.  Run them explicitly with:

    pytest -m integration
    pytest -m slow
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest
from sqlalchemy import create_engine, select

from skillsbank.db.base import Base
from skillsbank.db.exporter import export_sqlite_to_v3
from skillsbank.db.importer import import_v3_to_sqlite
from skillsbank.db.persistence_models import (
    CapabilityRow,
    RepoRow,
    SkillRow,
    TagRow,
    VersionRow,
)

pytestmark = [pytest.mark.slow, pytest.mark.integration]

V3_PATH = os.path.join(os.path.dirname(__file__), "..", "registry.v3.json")


# ---------------------------------------------------------------------------
# Session-scoped fixture: import the registry ONCE per test session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _imported_engine(tmp_path_factory):
    """Import the registry once and share the engine across all tests in this module."""
    db_path = str(tmp_path_factory.mktemp("data") / "roundtrip.db")
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    from skillsbank.db.engine import get_session

    session = get_session(engine)
    import_v3_to_sqlite(session, V3_PATH)
    session.commit()
    yield engine
    session.close()


@pytest.fixture()
def db_session(_imported_engine):
    """Yield a *fresh* session bound to the pre-imported engine.

    Each test gets its own session (transaction isolation) but shares the
    underlying imported data, so the expensive import only runs once.
    """
    from skillsbank.db.engine import get_session

    session = get_session(_imported_engine)
    yield session
    session.close()


@pytest.fixture(scope="module")
def v3_data():
    """Load the v3 JSON for reference (module-scoped — file doesn't change)."""
    with open(V3_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Import verification
# ---------------------------------------------------------------------------


class TestImportV3:
    """Test importing v3 JSON into SQLite."""

    def test_import_all_skills(self, db_session):
        """All 1,065 skills must be imported."""
        count = db_session.execute(select(SkillRow)).scalars().all()
        assert len(count) == 1065

    def test_import_all_versions(self, db_session):
        """All 1,065 versions must be imported."""
        count = db_session.execute(select(VersionRow)).scalars().all()
        assert len(count) == 1065

    def test_import_all_repos(self, db_session):
        """All 36 repos must be imported."""
        count = db_session.execute(select(RepoRow)).scalars().all()
        assert len(count) == 36

    def test_ids_preserved(self, db_session, v3_data):
        """All skill IDs must survive the round-trip."""
        db_ids = {r.id for r in db_session.execute(select(SkillRow)).scalars().all()}
        json_ids = {s["id"] for s in v3_data["skills"]}
        assert db_ids == json_ids

    def test_capabilities_imported(self, db_session):
        """Capabilities must be extracted into searchable rows."""
        count = db_session.execute(select(CapabilityRow)).scalars().all()
        assert len(count) > 0

    def test_tags_imported(self, db_session):
        """Tags must be extracted into searchable rows."""
        count = db_session.execute(select(TagRow)).scalars().all()
        assert len(count) > 0

    def test_fk_enforced(self, db_session):
        """Version FK to skill must be valid."""
        versions = db_session.execute(select(VersionRow)).scalars().all()
        skill_ids = {r.id for r in db_session.execute(select(SkillRow)).scalars().all()}
        for v in versions:
            assert v.skill_id in skill_ids, f"Version {v.version_id} references missing skill {v.skill_id}"

    def test_idempotent_import(self, db_session):
        """All 1,065 skills must be present."""
        skill_count = db_session.execute(select(SkillRow)).scalars().all()
        assert len(skill_count) == 1065


# ---------------------------------------------------------------------------
# Export verification
# ---------------------------------------------------------------------------


class TestExportV3:
    """Test exporting SQLite back to v3 JSON."""

    def test_export_skill_count(self, db_session):
        """Exported JSON must have all skills."""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            out_path = f.name
        try:
            result = export_sqlite_to_v3(db_session, out_path)
            assert result["skills_exported"] == 1065
        finally:
            os.unlink(out_path)

    def test_export_version_count(self, db_session):
        """Exported JSON must have all versions."""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            out_path = f.name
        try:
            result = export_sqlite_to_v3(db_session, out_path)
            assert result["versions_exported"] == 1065
        finally:
            os.unlink(out_path)

    def test_export_repo_count(self, db_session):
        """Exported JSON must have all repos."""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            out_path = f.name
        try:
            result = export_sqlite_to_v3(db_session, out_path)
            assert result["repos_exported"] == 36
        finally:
            os.unlink(out_path)

    def test_export_validates_as_v3(self, db_session):
        """Exported JSON must have v3 schema structure."""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            out_path = f.name
        try:
            export_sqlite_to_v3(db_session, out_path)
            with open(out_path) as f:
                data = json.load(f)
            assert data["schema_version"] == "3.0.0"
            assert "skills" in data
            assert "versions" in data
            assert "repositories" in data
            assert data["total_skills"] == 1065
        finally:
            os.unlink(out_path)


# ---------------------------------------------------------------------------
# Round-trip integrity
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Test v3 → SQLite → v3 round-trip integrity."""

    def test_roundtrip_ids_match(self, db_session, v3_data):
        """Skill IDs must survive the full round-trip."""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            out_path = f.name
        try:
            export_sqlite_to_v3(db_session, out_path)
            with open(out_path) as f:
                exported = json.load(f)
            original_ids = {s["id"] for s in v3_data["skills"]}
            exported_ids = {s["id"] for s in exported["skills"]}
            assert original_ids == exported_ids
        finally:
            os.unlink(out_path)

    def test_roundtrip_skill_names(self, db_session, v3_data):
        """Skill names must survive the round-trip."""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            out_path = f.name
        try:
            export_sqlite_to_v3(db_session, out_path)
            with open(out_path) as f:
                exported = json.load(f)
            orig_names = {s["id"]: s["name"] for s in v3_data["skills"]}
            exp_names = {s["id"]: s["name"] for s in exported["skills"]}
            assert orig_names == exp_names
        finally:
            os.unlink(out_path)

    def test_roundtrip_domain_primary(self, db_session, v3_data):
        """Domain primary values must survive the round-trip."""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            out_path = f.name
        try:
            export_sqlite_to_v3(db_session, out_path)
            with open(out_path) as f:
                exported = json.load(f)
            orig_domains = {}
            for v in v3_data["versions"]:
                dom = v.get("domain", {}).get("primary", {})
                val = dom.get("value") if isinstance(dom, dict) else dom
                orig_domains[v["skill_id"]] = val
            exp_domains = {}
            for v in exported["versions"]:
                dom = v.get("domain", {}).get("primary", {})
                val = dom.get("value") if isinstance(dom, dict) else dom
                exp_domains[v["skill_id"]] = val
            assert orig_domains == exp_domains
        finally:
            os.unlink(out_path)

    def test_roundtrip_capabilities(self, db_session, v3_data):
        """Capability counts must match after round-trip."""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            out_path = f.name
        try:
            export_sqlite_to_v3(db_session, out_path)
            with open(out_path) as f:
                exported = json.load(f)
            orig_total = sum(len(v.get("capabilities", [])) for v in v3_data["versions"])
            exp_total = sum(len(v.get("capabilities", [])) for v in exported["versions"])
            assert orig_total == exp_total
        finally:
            os.unlink(out_path)
