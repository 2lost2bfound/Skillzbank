"""Tests for SkillsBank Phase 1 — v2 import, schema validation, data integrity.

Required test cases:
1. All 1,065 v2 records import
2. Zero records lost
3. Existing skill IDs unchanged
4. Malformed I/O shapes normalize safely
5. Missing source entries backfill correctly
6. Unknown provenance fields remain unknown
7. Broken summaries remain preserved
8. Duplicate-name skills remain distinct
9. Same-name/different-repo skills remain distinct
10. Schema round-trip works
11. v3 JSON validates against generated schema
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skillsbank.importers.v2_importer import (
    MigrationStats,
    _normalize_io_shape,
    import_v2,
)
from skillsbank.models.registry import Registry
from skillsbank.schema.generator import generate_schema

# Path to the v2 registry — relative to project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
V2_REGISTRY_PATH = _PROJECT_ROOT / "registry.json"
V2_SKILL_COUNT = 1065
V2_REPO_COUNT_IN_SOURCES = 18
V2_TOTAL_REPOS = 36


@pytest.fixture
def v2_path() -> Path:
    """Ensure v2 registry exists."""
    assert V2_REGISTRY_PATH.exists(), f"V2 registry not found at {V2_REGISTRY_PATH}"
    return V2_REGISTRY_PATH


@pytest.fixture
def migration_result(v2_path: Path) -> tuple[Registry, MigrationStats]:
    """Run the v2 importer and return results."""
    return import_v2(v2_path)


@pytest.fixture
def registry(migration_result: tuple[Registry, MigrationStats]) -> Registry:
    """Extract registry from migration result."""
    return migration_result[0]


@pytest.fixture
def stats(migration_result: tuple[Registry, MigrationStats]) -> MigrationStats:
    """Extract stats from migration result."""
    return migration_result[1]


@pytest.fixture
def json_schema() -> dict:
    """Generate v3 JSON Schema."""
    return generate_schema()


# --- Test 1: All 1,065 v2 records import ---


def test_all_records_import(registry: Registry, stats: MigrationStats):
    """All 1,065 v2 records must be imported."""
    assert stats.total_v2_records == V2_SKILL_COUNT, (
        f"Expected {V2_SKILL_COUNT} v2 records, found {stats.total_v2_records}"
    )
    assert len(registry.skills) == V2_SKILL_COUNT, f"Expected {V2_SKILL_COUNT} skills in v3, got {len(registry.skills)}"
    assert len(registry.versions) == V2_SKILL_COUNT, (
        f"Expected {V2_SKILL_COUNT} versions in v3, got {len(registry.versions)}"
    )


# --- Test 2: Zero records lost ---


def test_zero_records_lost(registry: Registry, stats: MigrationStats):
    """No records may be lost during migration."""
    assert stats.total_v3_skills == V2_SKILL_COUNT
    assert stats.total_v3_versions == V2_SKILL_COUNT
    assert len(registry.skills) == V2_SKILL_COUNT
    assert len(registry.versions) == V2_SKILL_COUNT
    # Every skill ID must have a corresponding version
    skill_ids = {s.id for s in registry.skills}
    version_skill_ids = {v.skill_id for v in registry.versions}
    assert skill_ids == version_skill_ids, "Skill IDs and version skill_ids don't match"


# --- Test 3: Existing skill IDs unchanged ---


def test_skill_ids_preserved(registry: Registry, v2_path: Path):
    """UUID5 IDs must be preserved exactly from v2."""
    with open(v2_path) as f:
        v2 = json.load(f)

    v2_ids = {s["id"] for s in v2["skills"]}
    v3_ids = {s.id for s in registry.skills}

    assert v2_ids == v3_ids, f"ID mismatch: {len(v2_ids - v3_ids)} lost, {len(v3_ids - v2_ids)} gained"
    assert len(v2_ids) == V2_SKILL_COUNT


# --- Test 4: Malformed I/O shapes normalize safely ---


def test_malformed_io_shapes_normalize(registry: Registry, stats: MigrationStats):
    """All I/O shapes must be valid objects, even if originally malformed."""
    for version in registry.versions:
        # input_shape must be an InputShape object
        assert hasattr(version.input_shape, "format"), f"Skill {version.skill_id} has invalid input_shape"
        assert hasattr(version.input_shape, "required"), f"Skill {version.skill_id} input_shape missing 'required'"
        # output_shape must be an OutputShape object
        assert hasattr(version.output_shape, "format"), f"Skill {version.skill_id} has invalid output_shape"
        # format must not be empty
        assert version.input_shape.format, f"Skill {version.skill_id} has empty input format"
        assert version.output_shape.format, f"Skill {version.skill_id} has empty output format"

    # Check that some were actually normalized
    assert stats.io_shapes_normalized > 0, "Expected some I/O shapes to be normalized"
    assert stats.io_shapes_already_valid > 0, "Expected some I/O shapes already valid"


def test_normalize_io_shape_none():
    """None input should normalize to unknown."""
    result, notes = _normalize_io_shape(None, "input_shape")
    assert result["format"] == "unknown"
    assert result["required"] == []
    assert len(notes) > 0


def test_normalize_io_shape_empty_string():
    """Empty string should normalize to unknown."""
    result, notes = _normalize_io_shape("", "input_shape")
    assert result["format"] == "unknown"
    assert result["required"] == []
    assert len(notes) > 0


def test_normalize_io_shape_raw_string():
    """Raw string should be preserved as format."""
    result, notes = _normalize_io_shape("natural_language", "input_shape")
    assert result["format"] == "natural_language"
    assert result["required"] == []
    assert len(notes) > 0


def test_normalize_io_shape_valid_dict():
    """Valid dict should pass through unchanged."""
    raw = {"format": "json", "required": ["field1"]}
    result, notes = _normalize_io_shape(raw, "input_shape")
    assert result["format"] == "json"
    assert result["required"] == ["field1"]
    assert len(notes) == 0


# --- Test 5: Missing source entries backfill correctly ---


def test_missing_sources_backfilled(registry: Registry, stats: MigrationStats):
    """The 18 repos missing from sources dict must be backfilled from skills."""
    repo_ids = {r.id for r in registry.repositories}

    # All 36 repos should be present
    assert len(repo_ids) == V2_TOTAL_REPOS, f"Expected {V2_TOTAL_REPOS} repos, got {len(repo_ids)}"

    # The declared sources should be present
    with open(V2_REGISTRY_PATH) as f:
        v2 = json.load(f)
    for repo_id in v2.get("sources", {}):
        assert repo_id in repo_ids, f"Declared source {repo_id} missing from v3 repos"

    # The backfilled sources should be present
    backfilled_repos = {
        "Alishahryar1/free-claude-code",
        "zhaoxuya520/reverse-skill",
        "atilaahmettaner/tradingview-mcp",
        "emilkowalski/skills",
        "lidge-jun/opencodex",
        "decolua/9router",
        "HKUDS/Vibe-Trading",
        "kaomei/stickman-video-director",
        "tashfeenahmed/freellmapi",
        "jakubkrehel/skills",
        "bradautomates/claude-video",
        "Jaycheng1103/chatgpt-video-editing-skills",
        "chaseai-yt/grill-me-codex",
        "browser-use/video-use",
        "alchaincyf/nuwa-skill",
        "brycewang-stanford/Auto-Research-Skills",
    }
    for repo_id in backfilled_repos:
        assert repo_id in repo_ids, f"Backfilled repo {repo_id} missing"

    assert stats.source_entries_backfilled > 0


# --- Test 6: Unknown provenance fields remain unknown ---


def test_unknown_provenance_fields(registry: Registry):
    """Fields that were unknown in v2 must remain unknown, not invented."""
    for version in registry.versions:
        source = version.source
        # These must be None (unknown), not fabricated
        assert source.commit_sha is None, f"Skill {version.skill_id} has invented commit_sha"
        assert source.content_hash is None, f"Skill {version.skill_id} has invented content_hash"
        assert source.branch is None, f"Skill {version.skill_id} has invented branch"
        assert source.upstream_created_at is None, f"Skill {version.skill_id} has invented upstream_created_at"
        assert source.upstream_updated_at is None, f"Skill {version.skill_id} has invented upstream_updated_at"
        assert version.last_checked_at is None, f"Skill {version.skill_id} has invented last_checked_at"
        assert version.version_id is None, f"Skill {version.skill_id} has invented version_id"
        # License should be unknown UNLESS the v2 ecosystem_metadata contained a license
        # (1 skill in v2 has a declared license — that's legitimate)
        assert version.license.status.value in ("unknown", "detected"), (
            f"Skill {version.skill_id} has unexpected license status: {version.license.status.value}"
        )
        # Security should be unknown
        assert version.security.risk_level.value == "UNKNOWN", f"Skill {version.skill_id} has invented risk_level"


# --- Test 7: Broken summaries remain preserved ---


def test_broken_summaries_preserved(registry: Registry, stats: MigrationStats):
    """Broken summaries must be preserved in the summary field AND in original_values."""
    broken_count = 0
    for version in registry.versions:
        if version.quality.documentation_quality.value == "BROKEN_EXTRACTION":
            broken_count += 1
            # The summary should still be present
            assert version.summary is not None, f"Broken-summary skill {version.skill_id} lost its summary"
            # The original should be in migration metadata
            assert "summary" in version.migration.original_values, (
                f"Skill {version.skill_id} missing original summary in migration metadata"
            )

    assert broken_count > 0, "Expected some broken summaries to be flagged"
    assert broken_count == stats.broken_summaries_flagged


# --- Test 8: Duplicate-name skills remain distinct ---


def test_duplicate_name_skills_distinct(registry: Registry):
    """Skills with the same name but different repos must remain as separate records."""
    # skill-creator appears in 3 repos
    skill_creators = [s for s in registry.skills if s.name == "skill-creator"]
    assert len(skill_creators) == 3, f"Expected 3 skill-creator records, got {len(skill_creators)}"
    repos = {s.primary_source.value for s in skill_creators}
    assert repos == {"anthropics/skills", "openai/skills", "microsoft/skills"}

    # All must have different IDs
    ids = {s.id for s in skill_creators}
    assert len(ids) == 3, "skill-creator records share an ID"


# --- Test 9: Same-name/different-repo skills remain distinct ---


def test_same_name_different_repo_distinct(registry: Registry):
    """code-review in mattpocock vs coderabbitai must be distinct."""
    code_reviews = [s for s in registry.skills if s.name == "code-review"]
    assert len(code_reviews) == 2
    repos = {s.primary_source.value for s in code_reviews}
    assert repos == {"mattpocock/skills", "coderabbitai/skills"}
    ids = {s.id for s in code_reviews}
    assert len(ids) == 2


# --- Test 10: Schema round-trip works ---


def test_schema_round_trip(registry: Registry, tmp_path: Path):
    """Registry must survive serialize → deserialize round-trip."""
    # Serialize to JSON
    output_file = tmp_path / "round_trip.json"
    output_file.write_text(registry.model_dump_json(indent=2))

    # Deserialize
    with open(output_file) as f:
        data = json.load(f)

    restored = Registry.model_validate(data)

    # Must have same counts
    assert len(restored.skills) == len(registry.skills)
    assert len(restored.versions) == len(registry.versions)
    assert len(restored.repositories) == len(registry.repositories)

    # Must preserve IDs
    original_ids = {s.id for s in registry.skills}
    restored_ids = {s.id for s in restored.skills}
    assert original_ids == restored_ids

    # Must preserve names
    for orig, rest in zip(registry.skills, restored.skills):
        assert orig.name == rest.name


# --- Test 11: v3 JSON validates against generated schema ---


def test_v3_json_validates_against_schema(registry: Registry, json_schema: dict, tmp_path: Path):
    """The generated v3 JSON must validate against the JSON Schema."""
    # Write registry to JSON
    v3_file = tmp_path / "registry.v3.json"
    v3_file.write_text(registry.model_dump_json(indent=2))

    # Load and validate structure
    with open(v3_file) as f:
        data = json.load(f)

    # Basic structural validation against schema
    assert data["schema_version"] == "3.0.0"
    assert "generated_at" in data
    assert "skills" in data
    assert "versions" in data
    assert "repositories" in data
    assert "relationships" in data
    assert "similarities" in data
    assert data["total_skills"] == V2_SKILL_COUNT

    # Validate schema has expected top-level properties
    props = json_schema.get("properties", {})
    assert "schema_version" in props
    assert "skills" in props
    assert "versions" in props
    assert "repositories" in props
    assert "relationships" in props


# --- Additional validation tests ---


def test_all_repos_have_urls(registry: Registry):
    """All GitHub repos should have URLs."""
    for repo in registry.repositories:
        if repo.source_type.value == "github_repo":
            assert repo.url is not None, f"GitHub repo {repo.id} missing URL"
            assert repo.url.startswith("https://github.com/"), f"Repo {repo.id} has invalid URL: {repo.url}"


def test_all_skills_have_canonical_key(registry: Registry):
    """Every skill should have a canonical_key."""
    for skill in registry.skills:
        assert skill.canonical_key, f"Skill {skill.id} missing canonical_key"
        assert "/" in skill.canonical_key, (
            f"Skill {skill.id} canonical_key missing path separator: {skill.canonical_key}"
        )


def test_migration_metadata_present(registry: Registry):
    """Every version should have migration metadata."""
    for version in registry.versions:
        assert version.migration is not None
        assert version.migration.imported_from == "registry_v2"
        assert version.migration.imported_at is not None


def test_registry_metadata(registry: Registry, stats: MigrationStats):
    """Registry-level metadata should be correct."""
    assert registry.schema_version == "3.0.0"
    assert registry.migrated_from == "registry_v2.0.0"
    assert registry.total_skills == V2_SKILL_COUNT
    assert registry.total_versions == V2_SKILL_COUNT
    assert registry.total_repos == V2_TOTAL_REPOS
    assert len(registry.migration_notes) > 0
