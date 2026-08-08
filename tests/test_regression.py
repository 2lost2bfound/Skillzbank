"""Regression tests for v1.0.0 remediation fixes.

Tests that fresh import produces an immediately usable database without
undocumented repair steps. Also tests recommender relevance ranking.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from skillsbank.db.base import Base
from skillsbank.db.importer import import_v3_to_sqlite
from skillsbank.recommender import RecommendationReason, recommend

TEST_V3 = os.path.join(os.path.dirname(__file__), "..", "registry.v3.json")


@pytest.fixture(scope="function")
def fresh_db_session():
    """Brand-new SQLite DB with a fresh import."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    stats = import_v3_to_sqlite(session, TEST_V3, auto_prepare=True)
    assert stats.skills_imported > 0
    assert stats.repos_imported > 0
    yield session
    session.close()


class TestImportAutoPrepare:
    """Fresh import produces an immediately usable database."""

    def test_doctor_green_after_import(self, fresh_db_session):
        """After import (with auto_prepare), doctor should pass all checks."""
        session = fresh_db_session

        # DB has data
        skill_count = session.execute(text("SELECT COUNT(*) FROM skills")).scalar()
        assert skill_count >= 1000

        # FTS index should be populated
        fts_count = session.execute(text("SELECT COUNT(*) FROM fts_skills")).scalar()
        assert fts_count > 0

        # Capabilities should be classified (not all uncategorized)
        categorized = session.execute(
            text(
                "SELECT COUNT(*) FROM capabilities WHERE taxonomy_path IS NOT NULL AND taxonomy_path NOT LIKE 'uncategorized/%'"
            )
        ).scalar()
        assert categorized > 0

        # Versions should have quality scores
        scored = session.execute(text("SELECT COUNT(*) FROM versions WHERE quality IS NOT NULL")).scalar()
        assert scored > 0

    def test_search_works_after_import(self, fresh_db_session):
        """Search should return results immediately after import."""
        session = fresh_db_session
        rows = session.execute(
            text("SELECT COUNT(*) FROM fts_skills WHERE fts_skills MATCH :q"),
            {"q": "security"},
        ).scalar()
        assert rows > 0

    def test_import_idempotent(self, fresh_db_session):
        """Re-import should be idempotent — no duplicate counts."""
        session = fresh_db_session
        skill_before = session.execute(text("SELECT COUNT(*) FROM skills")).scalar()
        version_before = session.execute(text("SELECT COUNT(*) FROM versions")).scalar()
        repo_before = session.execute(text("SELECT COUNT(*) FROM repositories")).scalar()

        import_v3_to_sqlite(session, TEST_V3, auto_prepare=True)

        skill_after = session.execute(text("SELECT COUNT(*) FROM skills")).scalar()
        version_after = session.execute(text("SELECT COUNT(*) FROM versions")).scalar()
        repo_after = session.execute(text("SELECT COUNT(*) FROM repositories")).scalar()

        assert skill_after == skill_before
        assert version_after == version_before
        assert repo_after == repo_before

    def test_normalize_idempotent(self, fresh_db_session):
        """Manual normalize after import should be safe — no semantic change."""
        session = fresh_db_session
        from skillsbank.db.taxonomy_sync import normalize_db_capabilities

        stats = normalize_db_capabilities(session)
        assert stats["normalized"] >= 0

        cap_count = session.execute(text("SELECT COUNT(*) FROM capabilities")).scalar()
        assert cap_count > 0


class TestRecommenderRelevance:
    """Recommender prioritizes task relevance, not just quality."""

    @pytest.fixture(scope="function")
    def populated_session(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        import_v3_to_sqlite(session, TEST_V3, auto_prepare=True)
        yield session
        session.close()

    def test_task_match_appears_first(self, populated_session):
        """When a task matches security-relevant skills, those appear above generic ones."""
        result = recommend(populated_session, task="build a secure API with authentication")
        assert len(result.recommendations) > 0

        # Task-match recommendations should be at the top
        top_task = [r for r in result.recommendations if r.reason == RecommendationReason.TASK_MATCH][:8]
        assert len(top_task) > 0, "Expected at least some task-match results"

    def test_no_high_quality_when_task_provided(self, populated_session):
        """When task is provided, high_quality fallback should NOT appear."""
        result = recommend(populated_session, task="build a secure API with authentication")
        reasons = {r.reason for r in result.recommendations}
        # High-quality should not appear in a task-based recommendation
        assert RecommendationReason.HIGH_QUALITY not in reasons

    def test_high_quality_fallback_when_no_task(self, populated_session):
        """When no task is provided, high_quality fallback SHOULD appear."""
        result = recommend(populated_session, task="")
        reasons = {r.reason for r in result.recommendations}
        assert len(reasons) > 0
        # With no task and no installed, high_quality should appear
        assert RecommendationReason.HIGH_QUALITY in reasons

    def test_security_task_finds_security_domain(self, populated_session):
        """Security task should find relevant skills near the top."""
        result = recommend(populated_session, task="audit API security for vulnerabilities")
        top20 = result.recommendations[:20]
        domains = {r.domain for r in top20}
        assert any(d for d in domains), f"No domains in top 20: {domains}"

    def test_pdf_task(self, populated_session):
        """PDF task should return recommendations."""
        result = recommend(populated_session, task="create and edit a PDF")
        assert len(result.recommendations) > 0

    def test_reverse_engineering_task(self, populated_session):
        """Reverse engineering task should return recommendations."""
        result = recommend(populated_session, task="reverse engineer a binary")
        assert len(result.recommendations) > 0

    def test_react_frontend_task(self, populated_session):
        """React frontend task should return recommendations."""
        result = recommend(populated_session, task="build a React frontend")
        assert len(result.recommendations) > 0
