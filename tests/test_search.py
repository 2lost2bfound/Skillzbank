"""Tests for FTS5 search engine."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from skillsbank.db.base import Base
from skillsbank.db.persistence_models import (
    CapabilityRow,
    SkillRow,
    TagRow,
    VersionRow,
)
from skillsbank.search import (
    SearchFilters,
    SearchResponse,
    SearchResult,
    _build_skill_query,
    autocomplete,
    get_search_stats,
    rebuild_fts_index,
    search,
    search_by_capability,
    search_by_tag,
)


@pytest.fixture
def engine():
    """Create an in-memory SQLite engine."""
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    """Create a session with test data."""
    sess = Session(engine)

    # Add skills
    skills = [
        SkillRow(
            id="skill-001",
            name="code-review",
            canonical_key="mattpocock/skills/code-review",
            display_name="Code Review",
            lifecycle="active",
            is_current=True,
            primary_source="mattpocock/skills",
        ),
        SkillRow(
            id="skill-002",
            name="tdd",
            canonical_key="mattpocock/skills/tdd",
            display_name="Test-Driven Development",
            lifecycle="active",
            is_current=True,
            primary_source="mattpocock/skills",
        ),
        SkillRow(
            id="skill-003",
            name="security-audit",
            canonical_key="anthropics/skills/security-audit",
            display_name="Security Audit",
            lifecycle="active",
            is_current=True,
            primary_source="anthropics/skills",
        ),
        SkillRow(
            id="skill-004",
            name="frontend-design",
            canonical_key="anthropics/skills/frontend-design",
            display_name="Frontend Design",
            lifecycle="active",
            is_current=True,
            primary_source="anthropics/skills",
        ),
        SkillRow(
            id="skill-005",
            name="mcp-builder",
            canonical_key="anthropics/skills/mcp-builder",
            display_name="MCP Server Builder",
            lifecycle="active",
            is_current=True,
            primary_source="anthropics/skills",
        ),
    ]
    sess.add_all(skills)
    sess.flush()

    # Add versions
    versions = [
        VersionRow(
            skill_id="skill-001",
            version_id="v-001",
            name="code-review",
            summary="Two-axis review: Standards and Spec. Uses parallel sub-agents.",
            domain_primary="code_quality",
            source_repo="mattpocock/skills",
            source_type="SKILL.md",
        ),
        VersionRow(
            skill_id="skill-002",
            version_id="v-002",
            name="tdd",
            summary="Red-green-refactor loop for test-driven development.",
            domain_primary="testing",
            source_repo="mattpocock/skills",
            source_type="SKILL.md",
        ),
        VersionRow(
            skill_id="skill-003",
            version_id="v-003",
            name="security-audit",
            summary="Comprehensive security vulnerability scanning and threat modeling.",
            domain_primary="security",
            source_repo="anthropics/skills",
            source_type="SKILL.md",
            quality={"overall_score": 0.85},
            security={"risk_level": "LOW"},
        ),
        VersionRow(
            skill_id="skill-004",
            version_id="v-004",
            name="frontend-design",
            summary="Distinctive visual design with typography and anti-AI-slop principles.",
            domain_primary="ui_ux",
            source_repo="anthropics/skills",
            source_type="SKILL.md",
        ),
        VersionRow(
            skill_id="skill-005",
            version_id="v-005",
            name="mcp-builder",
            summary="Build MCP servers with TypeScript or Python. Tool naming and context management.",
            domain_primary="integration",
            source_repo="anthropics/skills",
            source_type="SKILL.md",
            compatibility={"mcp_compatible": True, "claude": "SUPPORTED"},
        ),
    ]
    sess.add_all(versions)
    sess.flush()

    # Add capabilities
    caps = [
        CapabilityRow(version_id_fk=1, name="code-review", canonical="code-review", taxonomy_path="code_quality"),
        CapabilityRow(version_id_fk=1, name="parallel-agents", canonical="parallel-agents", taxonomy_path="ai_ml"),
        CapabilityRow(version_id_fk=2, name="test-driven-development", canonical="tdd", taxonomy_path="testing"),
        CapabilityRow(
            version_id_fk=2, name="red-green-refactor", canonical="red-green-refactor", taxonomy_path="testing"
        ),
        CapabilityRow(version_id_fk=3, name="security-scan", canonical="security-scan", taxonomy_path="security"),
        CapabilityRow(version_id_fk=3, name="threat-modeling", canonical="threat-modeling", taxonomy_path="security"),
        CapabilityRow(version_id_fk=4, name="ui-design", canonical="ui-design", taxonomy_path="ui_ux"),
        CapabilityRow(version_id_fk=4, name="typography", canonical="typography", taxonomy_path="ui_ux"),
        CapabilityRow(version_id_fk=5, name="mcp-server", canonical="mcp-server", taxonomy_path="integration"),
        CapabilityRow(version_id_fk=5, name="tool-naming", canonical="tool-naming", taxonomy_path="integration"),
    ]
    sess.add_all(caps)
    sess.flush()

    # Add tags
    tags = [
        TagRow(version_id_fk=1, name="review", source="parser"),
        TagRow(version_id_fk=1, name="quality", source="parser"),
        TagRow(version_id_fk=2, name="testing", source="parser"),
        TagRow(version_id_fk=2, name="python", source="parser"),
        TagRow(version_id_fk=3, name="security", source="parser"),
        TagRow(version_id_fk=3, name="vulnerability", source="parser"),
        TagRow(version_id_fk=4, name="css", source="parser"),
        TagRow(version_id_fk=4, name="design", source="parser"),
        TagRow(version_id_fk=5, name="mcp", source="parser"),
        TagRow(version_id_fk=5, name="typescript", source="parser"),
    ]
    sess.add_all(tags)
    sess.commit()

    # Build FTS index
    rebuild_fts_index(sess)

    return sess


# ---------------------------------------------------------------------------
# Query building tests
# ---------------------------------------------------------------------------


class TestBuildQuery:
    def test_empty_query(self):
        assert _build_skill_query("") == ""
        assert _build_skill_query("   ") == ""

    def test_single_word(self):
        result = _build_skill_query("security")
        assert "security" in result

    def test_multiple_words(self):
        result = _build_skill_query("code review")
        assert "AND" in result
        assert "code" in result
        assert "review" in result

    def test_fts_syntax_passthrough(self):
        """Queries with special chars should pass through."""
        q = '"code review"'
        assert _build_skill_query(q) == q

    def test_boolean_operators(self):
        result = _build_skill_query("security OR testing")
        assert "OR" in result

    def test_prefix_matching(self):
        result = _build_skill_query("sec")
        assert "*" in result


# ---------------------------------------------------------------------------
# Index rebuild tests
# ---------------------------------------------------------------------------


class TestRebuildIndex:
    def test_rebuild_creates_tables(self, session):
        stats = rebuild_fts_index(session)
        assert stats["skills_indexed"] == 5
        assert stats["capabilities_indexed"] == 10
        assert stats["tags_indexed"] == 10

    def test_rebuild_idempotent(self, session):
        rebuild_fts_index(session)
        stats = rebuild_fts_index(session)
        assert stats["skills_indexed"] == 5


# ---------------------------------------------------------------------------
# Basic search tests
# ---------------------------------------------------------------------------


class TestSearch:
    def test_basic_search(self, session):
        resp = search(session, "code review")
        assert isinstance(resp, SearchResponse)
        assert resp.total >= 1
        assert any(r.skill_id == "skill-001" for r in resp.results)

    def test_search_by_domain(self, session):
        resp = search(session, "security")
        assert resp.total >= 1
        assert any(r.domain == "security" for r in resp.results)

    def test_search_no_results(self, session):
        resp = search(session, "nonexistent_xyz_skill")
        assert resp.total == 0
        assert resp.results == []

    def test_search_empty_query(self, session):
        resp = search(session, "")
        assert resp.total == 0

    def test_search_with_limit(self, session):
        resp = search(session, "test OR design OR security OR code", limit=2)
        assert len(resp.results) <= 2

    def test_search_result_fields(self, session):
        resp = search(session, "code review")
        assert resp.total >= 1
        r = resp.results[0]
        assert isinstance(r, SearchResult)
        assert r.skill_id
        assert r.name
        assert r.summary
        assert isinstance(r.bm25_score, float)
        assert isinstance(r.matched_fields, list)
        assert isinstance(r.capabilities, list)
        assert isinstance(r.tags, list)

    def test_search_quality_score_populated(self, session):
        resp = search(session, "security")
        security_results = [r for r in resp.results if r.domain == "security"]
        if security_results:
            assert security_results[0].quality_score > 0

    def test_search_capabilities_populated(self, session):
        resp = search(session, "code review")
        if resp.results:
            assert isinstance(resp.results[0].capabilities, list)

    def test_search_tags_populated(self, session):
        resp = search(session, "code review")
        if resp.results:
            assert isinstance(resp.results[0].tags, list)


# ---------------------------------------------------------------------------
# Filter tests
# ---------------------------------------------------------------------------


class TestSearchFilters:
    def test_filter_by_domain(self, session):
        filters = SearchFilters(domain="security")
        resp = search(session, "audit OR scan OR security", filters=filters)
        for r in resp.results:
            assert r.domain == "security"

    def test_filter_by_repo(self, session):
        filters = SearchFilters(repo="anthropics/skills")
        resp = search(session, "design OR security OR mcp", filters=filters)
        for r in resp.results:
            assert r.repo == "anthropics/skills"

    def test_filter_by_min_quality(self, session):
        filters = SearchFilters(min_quality=0.8)
        resp = search(session, "security", filters=filters)
        for r in resp.results:
            assert r.quality_score >= 0.8

    def test_filter_by_lifecycle(self, session):
        filters = SearchFilters(lifecycle="active")
        resp = search(session, "code OR test", filters=filters)
        # All test skills are active
        assert resp.total >= 1

    def test_filter_by_has_mcp(self, session):
        filters = SearchFilters(has_mcp=True)
        resp = search(session, "mcp OR builder", filters=filters)
        for r in resp.results:
            assert r.skill_id == "skill-005"

    def test_filter_no_results(self, session):
        filters = SearchFilters(domain="nonexistent")
        resp = search(session, "code review", filters=filters)
        assert resp.total == 0

    def test_combined_filters(self, session):
        filters = SearchFilters(
            repo="anthropics/skills",
            domain="security",
        )
        resp = search(session, "security OR audit", filters=filters)
        for r in resp.results:
            assert r.repo == "anthropics/skills"
            assert r.domain == "security"


# ---------------------------------------------------------------------------
# Facet tests
# ---------------------------------------------------------------------------


class TestFacets:
    def test_facets_included(self, session):
        resp = search(session, "code OR test OR design OR security OR mcp", include_facets=True)
        assert isinstance(resp.facets, dict)

    def test_facets_excluded(self, session):
        resp = search(session, "code review", include_facets=False)
        assert resp.facets == {}

    def test_facet_structure(self, session):
        resp = search(session, "code OR test OR design OR security OR mcp", include_facets=True)
        if resp.facets:
            for facet_name, facet_values in resp.facets.items():
                assert isinstance(facet_name, str)
                assert isinstance(facet_values, list)
                for value, count in facet_values:
                    assert isinstance(value, str)
                    assert isinstance(count, int)


# ---------------------------------------------------------------------------
# Capability / Tag search tests
# ---------------------------------------------------------------------------


class TestCapabilitySearch:
    def test_search_by_capability(self, session):
        results = search_by_capability(session, "security")
        assert len(results) >= 1
        assert any(r.skill_id == "skill-003" for r in results)

    def test_search_by_capability_no_results(self, session):
        results = search_by_capability(session, "nonexistent_xyz")
        assert len(results) == 0

    def test_capability_result_fields(self, session):
        results = search_by_capability(session, "tdd")
        if results:
            r = results[0]
            assert r.skill_id
            assert r.name
            assert "capabilities" in r.matched_fields


class TestTagSearch:
    def test_search_by_tag(self, session):
        results = search_by_tag(session, "security")
        assert len(results) >= 1

    def test_search_by_tag_no_results(self, session):
        results = search_by_tag(session, "nonexistent_xyz")
        assert len(results) == 0

    def test_tag_result_fields(self, session):
        results = search_by_tag(session, "mcp")
        if results:
            r = results[0]
            assert r.skill_id == "skill-005"
            assert "tags" in r.matched_fields


# ---------------------------------------------------------------------------
# Autocomplete tests
# ---------------------------------------------------------------------------


class TestAutocomplete:
    def test_autocomplete_basic(self, session):
        results = autocomplete(session, "code")
        assert len(results) >= 1
        assert any("code" in r.lower() for r in results)

    def test_autocomplete_short_prefix(self, session):
        results = autocomplete(session, "c")
        assert results == []

    def test_autocomplete_no_results(self, session):
        results = autocomplete(session, "zzz_nonexistent")
        assert results == []

    def test_autocomplete_limit(self, session):
        results = autocomplete(session, "code", limit=1)
        assert len(results) <= 1


# ---------------------------------------------------------------------------
# Stats tests
# ---------------------------------------------------------------------------


class TestSearchStats:
    def test_get_stats(self, session):
        stats = get_search_stats(session)
        assert "fts_skills" in stats
        assert "fts_capabilities" in stats
        assert "fts_tags" in stats
        assert stats["fts_skills"] == 5
        assert stats["fts_capabilities"] == 10
        assert stats["fts_tags"] == 10


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_search_with_special_characters(self, session):
        """Should not crash on special chars."""
        resp = search(session, "c++ / python @#$%")
        assert isinstance(resp, SearchResponse)

    def test_search_unicode(self, session):
        """Should handle unicode gracefully."""
        resp = search(session, "résumé über cool")
        assert isinstance(resp, SearchResponse)

    def test_search_very_long_query(self, session):
        """Should handle long queries."""
        long_q = " ".join(["word"] * 100)
        resp = search(session, long_q)
        assert isinstance(resp, SearchResponse)
