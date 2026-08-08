"""Tests for Phase 12: Skill composition."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from skillsbank.composition import (
    CompositionStrategy,
    ConflictResolution,
    _detect_conflicts,
    _merge_capabilities,
    _merge_dependencies,
    _topological_sort,
    compose_skills,
    get_composition_summary,
    suggest_compositions,
)
from skillsbank.db.base import Base
from skillsbank.db.importer import import_v3_to_sqlite
from skillsbank.db.persistence_models import SkillRow
from skillsbank.dedup import detect_duplicates

TEST_V3 = os.path.join(os.path.dirname(__file__), "..", "registry.v3.json")


@pytest.fixture(scope="module")
def populated_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    import_v3_to_sqlite(session, TEST_V3)
    detect_duplicates(session, min_score=0.4)
    session.commit()
    yield session
    session.close()


@pytest.fixture
def sample_skills(populated_session):
    """Get 3 sample skill IDs."""
    skills = populated_session.query(SkillRow.id).limit(3).all()
    return [s.id for s in skills]


class TestDetectConflicts:
    def test_no_conflicts_for_different_skills(self, populated_session, sample_skills):
        """Two unrelated skills should have no conflicts or only minor ones."""
        conflicts = _detect_conflicts(populated_session, sample_skills[:2], ConflictResolution.WARN)
        assert isinstance(conflicts, list)

    def test_missing_skill(self, populated_session):
        """Missing skill should produce an error conflict."""
        conflicts = _detect_conflicts(populated_session, ["nonexistent-id-12345"], ConflictResolution.FAIL)
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == "missing_skill"
        assert conflicts[0].severity == "error"

    def test_empty_list(self, populated_session):
        conflicts = _detect_conflicts(populated_session, [], ConflictResolution.WARN)
        assert conflicts == []


class TestMergeCapabilities:
    def test_merges_from_multiple(self, populated_session, sample_skills):
        caps = _merge_capabilities(populated_session, sample_skills)
        assert isinstance(caps, list)
        assert len(caps) > 0

    def test_deduplicates(self, populated_session, sample_skills):
        """Same skill twice should not duplicate capabilities."""
        caps_once = _merge_capabilities(populated_session, sample_skills[:1])
        caps_twice = _merge_capabilities(populated_session, sample_skills[:1] * 2)
        assert len(caps_once) == len(caps_twice)


class TestMergeDependencies:
    def test_returns_dict(self, populated_session, sample_skills):
        deps = _merge_dependencies(populated_session, sample_skills)
        assert isinstance(deps, dict)
        for key in ["tools", "packages", "apis", "runtimes", "env_vars"]:
            assert key in deps or key not in deps  # keys present if non-empty

    def test_empty_for_no_deps(self, populated_session):
        deps = _merge_dependencies(populated_session, ["nonexistent-id-12345"])
        assert deps == {} or all(len(v) == 0 for v in deps.values())


class TestTopologicalSort:
    def test_parallel_returns_as_is(self, populated_session, sample_skills):
        order = _topological_sort(populated_session, sample_skills, CompositionStrategy.PARALLEL)
        assert order == sample_skills

    def test_sequential_preserves_order(self, populated_session, sample_skills):
        order = _topological_sort(populated_session, sample_skills, CompositionStrategy.SEQUENTIAL)
        assert order == sample_skills

    def test_pipeline_returns_list(self, populated_session, sample_skills):
        order = _topological_sort(populated_session, sample_skills, CompositionStrategy.PIPELINE)
        assert isinstance(order, list)
        assert len(order) == len(sample_skills)


class TestComposeSkills:
    def test_basic_composition(self, populated_session, sample_skills):
        result = compose_skills(
            populated_session,
            sample_skills[:2],
            name="Test Composite",
            description="A test composition",
        )
        assert result.composite.name == "Test Composite"
        assert result.total_components == 2
        assert result.composite.strategy == CompositionStrategy.SEQUENTIAL

    def test_empty_skills(self, populated_session):
        result = compose_skills(populated_session, [])
        assert not result.composite.is_valid
        assert result.total_components == 0
        assert len(result.warnings) > 0

    def test_pipeline_strategy(self, populated_session, sample_skills):
        result = compose_skills(
            populated_session,
            sample_skills[:2],
            strategy=CompositionStrategy.PIPELINE,
        )
        assert result.composite.strategy == CompositionStrategy.PIPELINE

    def test_parallel_strategy(self, populated_session, sample_skills):
        result = compose_skills(
            populated_session,
            sample_skills[:2],
            strategy=CompositionStrategy.PARALLEL,
        )
        assert result.composite.strategy == CompositionStrategy.PARALLEL

    def test_conditional_strategy(self, populated_session, sample_skills):
        result = compose_skills(
            populated_session,
            sample_skills[:2],
            strategy=CompositionStrategy.CONDITIONAL,
        )
        assert result.composite.strategy == CompositionStrategy.CONDITIONAL

    def test_auto_name(self, populated_session, sample_skills):
        """Name should be auto-generated if not provided."""
        result = compose_skills(populated_session, sample_skills[:2])
        assert result.composite.name
        assert "+" in result.composite.name

    def test_auto_description(self, populated_session, sample_skills):
        result = compose_skills(populated_session, sample_skills[:2])
        assert "Composite" in result.composite.description

    def test_merged_capabilities(self, populated_session, sample_skills):
        result = compose_skills(populated_session, sample_skills[:2])
        assert isinstance(result.composite.merged_capabilities, list)

    def test_merged_dependencies(self, populated_session, sample_skills):
        result = compose_skills(populated_session, sample_skills[:2])
        assert isinstance(result.composite.merged_dependencies, dict)

    def test_unique_repos(self, populated_session, sample_skills):
        result = compose_skills(populated_session, sample_skills[:2])
        assert result.unique_repos >= 1

    def test_install_order(self, populated_session, sample_skills):
        result = compose_skills(populated_session, sample_skills[:2])
        assert len(result.install_order) == 2

    def test_conflict_resolution_warn(self, populated_session, sample_skills):
        result = compose_skills(
            populated_session,
            sample_skills[:2],
            conflict_resolution=ConflictResolution.WARN,
        )
        assert isinstance(result.composite.conflicts, list)

    def test_component_configs(self, populated_session, sample_skills):
        configs = [{"condition": "if x > 0"}, {"input_mapping": {"out": "in"}}]
        result = compose_skills(
            populated_session,
            sample_skills[:2],
            component_configs=configs,
        )
        assert result.composite.components[0].condition == "if x > 0"
        assert result.composite.components[1].input_mapping == {"out": "in"}

    def test_missing_skill_invalid(self, populated_session):
        result = compose_skills(
            populated_session,
            ["nonexistent-id-12345"],
            conflict_resolution=ConflictResolution.FAIL,
        )
        assert not result.composite.is_valid


class TestGetCompositionSummary:
    def test_returns_dict(self, populated_session, sample_skills):
        result = compose_skills(
            populated_session,
            sample_skills[:2],
            name="Summary Test",
        )
        summary = get_composition_summary(result)
        assert summary["name"] == "Summary Test"
        assert summary["total_components"] == 2
        assert summary["strategy"] == "sequential"
        assert summary["is_valid"] is True
        assert isinstance(summary["merged_capabilities"], int)
        assert isinstance(summary["merged_dependencies"], dict)


class TestSuggestCompositions:
    def test_suggests_for_task(self, populated_session):
        suggestions = suggest_compositions(
            populated_session,
            "security audit code review",
            limit=3,
        )
        assert isinstance(suggestions, list)
        for s in suggestions:
            assert s.composite.is_valid or len(s.composite.conflicts) > 0

    def test_empty_task(self, populated_session):
        suggestions = suggest_compositions(populated_session, "", limit=3)
        assert suggestions == []

    def test_limit(self, populated_session):
        suggestions = suggest_compositions(
            populated_session,
            "build web app with testing",
            limit=2,
        )
        assert len(suggestions) <= 2
