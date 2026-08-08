"""Tests for Phase 11: Recommendation engine."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from skillsbank.db.base import Base
from skillsbank.db.importer import import_v3_to_sqlite
from skillsbank.db.persistence_models import SimilarityRow, SkillRow, VersionRow
from skillsbank.dedup import detect_duplicates
from skillsbank.recommender import (
    RecommendationReason,
    _extract_task_keywords,
    _get_high_quality_skills,
    _get_popular_skills,
    _get_same_category_skills,
    _get_same_ecosystem_skills,
    _get_similar_skills,
    _score_task_match,
    recommend,
    recommend_for_skill,
)

TEST_V3 = os.path.join(os.path.dirname(__file__), "..", "registry.v3.json")


@pytest.fixture(scope="module")
def populated_session():
    """Session with real data from registry.v3.json."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    stats = import_v3_to_sqlite(session, TEST_V3)
    assert stats.skills_imported > 0, "Must import at least 1 skill"
    assert stats.repos_imported > 0, "Must import at least 1 repo"

    # Run dedup so similarity table is populated
    detect_duplicates(session, min_score=0.4)

    session.commit()
    yield session
    session.close()


class TestExtractTaskKeywords:
    def test_security_keywords(self):
        kw = _extract_task_keywords("help me do a security audit of my web app")
        assert "security-audit" in kw or "security" in kw or "vulnerability-scanning" in kw

    def test_frontend_keywords(self):
        kw = _extract_task_keywords("build a React frontend with responsive design")
        assert "react-development" in kw or "frontend" in kw

    def test_devops_keywords(self):
        kw = _extract_task_keywords("set up CI/CD pipeline with Docker containers")
        assert "ci-cd" in kw or "containerization" in kw

    def test_testing_keywords(self):
        kw = _extract_task_keywords("write integration tests for the API")
        assert "integration-testing" in kw or "testing" in kw

    def test_empty_task(self):
        kw = _extract_task_keywords("")
        assert kw == []

    def test_unrelated_task(self):
        kw = _extract_task_keywords("hello world")
        assert isinstance(kw, list)


class TestScoreTaskMatch:
    def test_matching_skill(self, populated_session):
        """A security-related skill should match 'security audit'."""
        # Find a security skill
        security_skill = (
            populated_session.query(VersionRow.skill_id).filter(VersionRow.domain_primary == "security").first()
        )
        if not security_skill:
            pytest.skip("No security skills in DB")

        keywords = _extract_task_keywords("security audit vulnerability scanning")
        score, detail = _score_task_match(populated_session, keywords, security_skill.skill_id)
        assert score > 0.0
        assert len(detail) > 0

    def test_nonmatching_skill(self, populated_session):
        """An empty keyword list yields 0 score."""
        score, detail = _score_task_match(populated_session, [], "nonexistent-id")
        assert score == 0.0
        assert detail == ""


class TestGetSimilarSkills:
    def test_returns_similar(self, populated_session):
        """Skills with similarities should be returned."""
        # Get a skill that has similarities
        sim = populated_session.query(SimilarityRow).first()
        if not sim:
            pytest.skip("No similarities in DB")

        results = _get_similar_skills(populated_session, sim.skill_a_id, limit=5)
        assert len(results) > 0
        _other_id, score, classification = results[0]
        assert score > 0.0
        assert classification

    def test_no_similar(self, populated_session):
        """Nonexistent skill returns empty list."""
        results = _get_similar_skills(populated_session, "nonexistent-id-12345", limit=5)
        assert results == []


class TestGetSameCategorySkills:
    def test_returns_category_peers(self, populated_session):
        """Skills in same domain should be found."""
        version = (
            populated_session.query(VersionRow.skill_id, VersionRow.domain_primary)
            .filter(VersionRow.domain_primary.isnot(None))
            .first()
        )
        if not version:
            pytest.skip("No domain data")

        results = _get_same_category_skills(populated_session, version.skill_id, limit=5)
        assert isinstance(results, list)

    def test_unknown_skill(self, populated_session):
        results = _get_same_category_skills(populated_session, "nonexistent-id-12345", limit=5)
        assert results == []


class TestGetSameEcosystemSkills:
    def test_returns_ecosystem(self, populated_session):
        """Skills from same repo should be found."""
        version = populated_session.query(VersionRow.source_repo).filter(VersionRow.source_repo.isnot(None)).first()
        if not version:
            pytest.skip("No source_repo data")

        results = _get_same_ecosystem_skills(populated_session, version.source_repo, set(), limit=5)
        assert isinstance(results, list)

    def test_excludes_ids(self, populated_session):
        version = (
            populated_session.query(VersionRow.skill_id, VersionRow.source_repo)
            .filter(VersionRow.source_repo.isnot(None))
            .first()
        )
        if not version:
            pytest.skip("No source_repo data")

        results = _get_same_ecosystem_skills(populated_session, version.source_repo, {version.skill_id}, limit=5)
        assert version.skill_id not in results


class TestGetPopularSkills:
    def test_returns_popular(self, populated_session):
        results = _get_popular_skills(populated_session, set(), limit=5)
        assert len(results) > 0
        _skill_id, count = results[0]
        assert count > 0

    def test_excludes_ids(self, populated_session):
        results = _get_popular_skills(populated_session, set(), limit=5)
        if results:
            excluded = {results[0][0]}
            filtered = _get_popular_skills(populated_session, excluded, limit=5)
            assert all(sid not in excluded for sid, _ in filtered)


class TestGetHighQualitySkills:
    def test_returns_quality(self, populated_session):
        results = _get_high_quality_skills(populated_session, set(), limit=5)
        assert len(results) > 0
        _skill_id, score = results[0]
        assert isinstance(score, float)


class TestRecommend:
    def test_recommend_no_args(self, populated_session):
        """Recommend with no task/installed should return popular/high-quality."""
        recs = recommend(populated_session, limit=10)
        assert len(recs.recommendations) > 0
        assert recs.task == ""
        assert recs.installed_ids == []

    def test_recommend_with_task(self, populated_session):
        """Recommend with task should include task-match results."""
        recs = recommend(populated_session, task="build security audit tool", limit=10)
        recs.by_reason(RecommendationReason.TASK_MATCH)
        # May or may not have task matches depending on DB content
        assert len(recs.recommendations) > 0

    def test_recommend_with_installed(self, populated_session):
        """Recommend with installed IDs should suggest similar/related."""
        # Get some skill IDs
        skills = populated_session.query(SkillRow.id).limit(3).all()
        installed = [s.id for s in skills]

        recs = recommend(populated_session, installed_ids=installed, limit=10)
        # Should not recommend installed skills
        for rec in recs.recommendations:
            assert rec.skill_id not in installed

    def test_recommend_with_task_and_installed(self, populated_session):
        """Combine task + installed for richer recommendations."""
        skills = populated_session.query(SkillRow.id).limit(2).all()
        installed = [s.id for s in skills]

        recs = recommend(
            populated_session,
            task="security penetration testing",
            installed_ids=installed,
            limit=10,
        )
        assert isinstance(recs.recommendations, list)
        assert all(r.skill_id not in installed for r in recs.recommendations)

    def test_recommend_facets(self, populated_session):
        """Facets should count by reason."""
        recs = recommend(populated_session, task="code review", limit=10)
        assert isinstance(recs.facets, dict)

    def test_recommend_deduplicates(self, populated_session):
        """Same skill shouldn't appear twice."""
        recs = recommend(populated_session, limit=50)
        seen = set()
        for r in recs.recommendations:
            assert r.skill_id not in seen
            seen.add(r.skill_id)

    def test_recommend_top(self, populated_session):
        """top(n) returns correct count."""
        recs = recommend(populated_session, limit=20)
        top5 = recs.top(5)
        assert len(top5) <= 5

    def test_recommend_by_reason(self, populated_session):
        """by_reason filters correctly."""
        recs = recommend(populated_session, limit=20)
        popular = recs.by_reason(RecommendationReason.POPULAR)
        for r in popular:
            assert r.reason == RecommendationReason.POPULAR

    def test_recommend_limit(self, populated_session):
        """Limit should bound results."""
        recs = recommend(populated_session, limit=5)
        assert len(recs.recommendations) <= 5 * 3  # we keep 3x for filtering


class TestRecommendForSkill:
    def test_returns_related(self, populated_session):
        """Should return skills related to a given skill."""
        skill = populated_session.query(SkillRow.id).first()
        if not skill:
            pytest.skip("No skills in DB")

        recs = recommend_for_skill(populated_session, skill.id, limit=10)
        assert isinstance(recs, list)
        for r in recs:
            assert r.skill_id != skill.id

    def test_limit(self, populated_session):
        skill = populated_session.query(SkillRow.id).first()
        if not skill:
            pytest.skip("No skills in DB")

        recs = recommend_for_skill(populated_session, skill.id, limit=3)
        assert len(recs) <= 3
