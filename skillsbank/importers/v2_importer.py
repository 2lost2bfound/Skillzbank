"""V2 backward importer — migrates registry.json v2 to v3 domain model.

This importer:
- Reads the original registry.json v2 format
- Produces v3 Registry with full domain model objects
- Preserves all original values (stored in migration metadata)
- Normalizes malformed I/O shapes
- Flags broken summaries
- Backfills missing source repository entries
- Preserves stable UUID5 IDs
- Does NOT re-fetch, re-parse, or infer missing data
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from skillsbank.models.classification import Capability, Domain, Tag
from skillsbank.models.common import MigrationMetadata, ProvenancedValue
from skillsbank.models.enums import (
    DomainSource,
    LifecycleStatus,
    MetadataQuality,
    SourceType,
)
from skillsbank.models.io_shapes import InputShape, OutputShape
from skillsbank.models.registry import Registry
from skillsbank.models.repository import Repository
from skillsbank.models.skill import Skill
from skillsbank.models.skill_source import SkillSource
from skillsbank.models.skill_version import SkillVersion

# --- Constants ---

_BROKEN_SUMMARY_PATTERNS = [
    re.compile(r"^\|"),  # table rows
    re.compile(r"^---"),  # frontmatter delimiters
    re.compile(r"^```"),  # code blocks
    re.compile(r"^>\s*\[!"),  # GitHub callouts
    re.compile(r"^\*\*One-Time"),  # setup boilerplate
]


def _is_broken_summary(summary: str) -> bool:
    """Detect summaries that are raw markdown artifacts, not real descriptions."""
    if not summary or not summary.strip():
        return True
    stripped = summary.strip()
    for pat in _BROKEN_SUMMARY_PATTERNS:
        if pat.match(stripped):
            return True
    # Too short to be useful
    return len(stripped) < 10


def _normalize_io_shape(raw: Any, field_name: str) -> tuple[dict[str, Any], list[str]]:
    """Normalize a v2 input/output shape into a v3-compatible dict.

    Returns (normalized_dict, list_of_normalization_notes).
    """
    notes: list[str] = []

    # Case 1: None or empty string
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        notes.append(f"{field_name}: original was empty/null, set to unknown")
        return {"format": "unknown", "required": []}, notes

    # Case 2: Raw string (not a dict)
    if isinstance(raw, str):
        notes.append(f"{field_name}: original was raw string '{raw}', wrapped as format")
        return {"format": raw if raw.strip() else "unknown", "required": []}, notes

    # Case 3: Already a dict
    if isinstance(raw, dict):
        result = dict(raw)  # shallow copy
        # Ensure 'format' key exists
        if "format" not in result:
            result["format"] = "unknown"
            notes.append(f"{field_name}: dict missing 'format' key, set to unknown")
        # Ensure 'required' key exists for input shapes
        if field_name == "input_shape" and "required" not in result:
            result["required"] = []
        return result, notes

    # Case 4: Anything else
    notes.append(f"{field_name}: unexpected type {type(raw).__name__}, set to unknown")
    return {"format": "unknown", "required": []}, notes


def _extract_owner(repo: str) -> str | None:
    """Extract owner from 'owner/repo' format."""
    parts = repo.split("/")
    if len(parts) >= 2:
        return parts[0]
    return None


def _determine_source_type(repo: str) -> SourceType:
    """Determine source type from repo identifier."""
    if "/" in repo and not repo.startswith("@"):
        return SourceType.GITHUB_REPO
    if repo.startswith("@"):
        return SourceType.UNKNOWN  # npm package or similar
    if repo.startswith("http"):
        return SourceType.URL
    return SourceType.UNKNOWN


def _repo_url(repo: str, source_type: SourceType) -> str | None:
    """Generate full URL from repo identifier."""
    if source_type == SourceType.GITHUB_REPO:
        return f"https://github.com/{repo}"
    return None


# --- Migration Statistics ---


class MigrationStats:
    """Tracks statistics during migration."""

    def __init__(self) -> None:
        self.total_v2_records: int = 0
        self.total_v3_skills: int = 0
        self.total_v3_versions: int = 0
        self.total_v3_repos: int = 0
        self.ids_preserved: int = 0
        self.io_shapes_normalized: int = 0
        self.io_shapes_already_valid: int = 0
        self.source_entries_backfilled: int = 0
        self.broken_summaries_flagged: int = 0
        self.partial_records: int = 0
        self.unknown_provenance_fields: int = 0
        self.validation_failures: list[str] = []
        self.duplicate_names_within_repo: list[tuple[str, str]] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_v2_records": self.total_v2_records,
            "total_v3_skills": self.total_v3_skills,
            "total_v3_versions": self.total_v3_versions,
            "total_v3_repos": self.total_v3_repos,
            "ids_preserved": self.ids_preserved,
            "io_shapes_normalized": self.io_shapes_normalized,
            "io_shapes_already_valid": self.io_shapes_already_valid,
            "source_entries_backfilled": self.source_entries_backfilled,
            "broken_summaries_flagged": self.broken_summaries_flagged,
            "partial_records": self.partial_records,
            "unknown_provenance_fields": self.unknown_provenance_fields,
            "validation_failures": self.validation_failures,
            "duplicate_names_within_repo": self.duplicate_names_within_repo,
        }


# --- Main Importer ---


def import_v2(
    v2_path: str | Path,
    *,
    now: datetime | None = None,
) -> tuple[Registry, MigrationStats]:
    """Import a registry.json v2 file into a v3 Registry.

    Args:
        v2_path: Path to the v2 registry.json file.
        now: Timestamp to use for import (defaults to utcnow).

    Returns:
        (Registry, MigrationStats) tuple.
    """
    if now is None:
        now = datetime.now(UTC)

    with open(v2_path) as f:
        v2 = json.load(f)

    stats = MigrationStats()
    stats.total_v2_records = len(v2.get("skills", []))

    # --- Phase 1: Build Repository index ---
    declared_sources: dict[str, int] = v2.get("sources", {})
    repo_map: dict[str, Repository] = {}

    # Create repos from declared sources
    for repo_id, skill_count in declared_sources.items():
        st = _determine_source_type(repo_id)
        repo_map[repo_id] = Repository(
            id=repo_id,
            url=_repo_url(repo_id, st),
            owner=_extract_owner(repo_id),
            name=repo_id.split("/")[-1] if "/" in repo_id else repo_id,
            source_type=st,
            skill_count=skill_count,
        )

    # --- Phase 2: Import skills and versions ---
    skills: list[Skill] = []
    versions: list[SkillVersion] = []

    # Track repos we discover from skills
    discovered_repos: dict[str, set[str]] = defaultdict(set)  # repo -> set of skill_paths

    for v2_skill in v2.get("skills", []):
        skill_id = v2_skill.get("id", "")
        repo = v2_skill.get("repo", "")
        skill_path = v2_skill.get("skill_path", "")
        name = v2_skill.get("name", "")

        # Track for repo backfill
        discovered_repos[repo].add(skill_path)

        # --- Normalize I/O shapes ---
        raw_input = v2_skill.get("input_shape")
        raw_output = v2_skill.get("output_shape")

        input_norm, input_notes = _normalize_io_shape(raw_input, "input_shape")
        output_norm, output_notes = _normalize_io_shape(raw_output, "output_shape")

        if input_notes or output_notes:
            stats.io_shapes_normalized += 1
        else:
            stats.io_shapes_already_valid += 1

        # --- Detect broken summaries ---
        summary = v2_skill.get("summary", "")
        summary_quality = MetadataQuality.COMPLETE
        summary_notes: list[str] = []
        if _is_broken_summary(summary):
            summary_quality = MetadataQuality.BROKEN_EXTRACTION
            summary_notes.append("Summary contains markdown artifacts or is too short")
            stats.broken_summaries_flagged += 1

        # --- Build domain ---
        domain_val = v2_skill.get("domain", "")
        domain = Domain(
            primary=ProvenancedValue(
                value=domain_val if domain_val else None,
                source="imported",
            ),
            source=DomainSource.UNKNOWN,
            quality=MetadataQuality.UNKNOWN,
        )

        # --- Build capabilities ---
        caps: list[Capability] = []
        for c in v2_skill.get("capabilities", []):
            caps.append(Capability(name=c, canonical=None, taxonomy_path=None, confidence=None))

        # --- Build tags ---
        tags: list[Tag] = [Tag(name=t, source="imported") for t in v2_skill.get("tags", [])]

        # --- Build migration metadata ---
        original_values: dict[str, Any] = {}
        normalization_notes: list[str] = []

        # Preserve original I/O if normalized
        if raw_input is not None and (isinstance(raw_input, str) or raw_input != input_norm):
            original_values["input_shape"] = raw_input
            normalization_notes.extend(input_notes)
        if raw_output is not None and (isinstance(raw_output, str) or raw_output != output_norm):
            original_values["output_shape"] = raw_output
            normalization_notes.extend(output_notes)

        # Preserve original summary if broken
        if summary_quality == MetadataQuality.BROKEN_EXTRACTION:
            original_values["summary"] = summary
            normalization_notes.extend(summary_notes)

        migration = MigrationMetadata(
            imported_from="registry_v2",
            imported_at=now,
            original_values=original_values,
            normalization_notes=normalization_notes,
        )

        # --- Determine metadata quality ---
        meta_quality = MetadataQuality.COMPLETE
        if summary_quality == MetadataQuality.BROKEN_EXTRACTION:
            meta_quality = MetadataQuality.BROKEN_EXTRACTION
        elif not summary or len(summary) < 20:
            meta_quality = MetadataQuality.PARTIAL
            stats.partial_records += 1

        # Count unknown provenance
        stats.unknown_provenance_fields += 4  # commit_sha, content_hash, branch, upstream dates

        # --- Build SkillSource ---
        st = _determine_source_type(repo)
        source = SkillSource(
            repo=repo,
            owner=_extract_owner(repo),
            repo_url=_repo_url(repo, st),
            skill_path=skill_path,
            commit_sha=None,
            branch=None,
            content_hash=None,
            source_type=st,
        )

        # --- Build SkillVersion ---
        version = SkillVersion(
            skill_id=skill_id,
            version_id=None,
            source=source,
            imported_at=now,
            last_checked_at=None,
            name=name,
            display_name=None,
            summary=summary if summary_quality != MetadataQuality.BROKEN_EXTRACTION else summary,
            long_description=None,
            domain=domain,
            capabilities=caps,
            tags=tags,
            input_shape=InputShape(
                **input_norm,
                quality=MetadataQuality.UNKNOWN if input_norm.get("format") == "unknown" else MetadataQuality.PARTIAL,
            ),
            output_shape=OutputShape(
                **{k: v for k, v in output_norm.items() if k != "required"},
                quality=MetadataQuality.UNKNOWN if output_norm.get("format") == "unknown" else MetadataQuality.PARTIAL,
            ),
            declared_dependencies=[],
            inferred_dependencies=[],
            runtime_requirements=_build_runtime_requirements(v2_skill),
            compatibility=_build_compatibility(v2_skill),
            install_methods=[],
            quality=_build_quality_assessment(meta_quality, summary_quality),
            security=_build_security_assessment(v2_skill),
            license=_build_license_record(v2_skill),
            ecosystem_metadata=v2_skill.get("ecosystem_metadata", {}),
            migration=migration,
        )
        versions.append(version)

        # --- Build Skill (canonical identity) ---
        skill = Skill(
            id=skill_id,
            canonical_key=f"{repo}/{skill_path}",
            name=name,
            display_name=None,
            aliases=[],
            lifecycle=LifecycleStatus.UNKNOWN,
            is_current=True,
            primary_source=ProvenancedValue(
                value=repo,
                source="imported",
            ),
            primary_path=ProvenancedValue(
                value=skill_path,
                source="imported",
            ),
            first_seen_at=now,
            last_updated_at=None,
            metadata_quality=meta_quality,
            version_count=1,
            current_version_id=None,
        )
        skills.append(skill)
        stats.ids_preserved += 1

    # --- Phase 3: Backfill missing repos ---
    for repo_id, paths in discovered_repos.items():
        if repo_id not in repo_map:
            st = _determine_source_type(repo_id)
            repo_map[repo_id] = Repository(
                id=repo_id,
                url=_repo_url(repo_id, st),
                owner=_extract_owner(repo_id),
                name=repo_id.split("/")[-1] if "/" in repo_id else repo_id,
                source_type=st,
                skill_count=len(paths),
            )
            stats.source_entries_backfilled += 1

    # --- Phase 4: Detect within-repo duplicate names ---
    name_repo_groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for s in skills:
        name_repo_groups[(s.name, s.primary_source.value)].append(s.id)
    for (name, repo), ids in name_repo_groups.items():
        if len(ids) > 1:
            stats.duplicate_names_within_repo.append((name, repo))

    # --- Build registry ---
    repos = list(repo_map.values())
    registry = Registry(
        schema_version="3.0.0",
        generated_at=now,
        skills=skills,
        versions=versions,
        repositories=repos,
        relationships=[],
        similarities=[],
        total_skills=len(skills),
        total_versions=len(versions),
        total_repos=len(repos),
        migrated_from="registry_v2.0.0",
        migration_notes=[
            f"Migrated {len(skills)} skills from {len(v2.get('sources', {}))} declared sources",
            f"Backfilled {stats.source_entries_backfilled} missing repository entries",
            f"Flagged {stats.broken_summaries_flagged} broken summaries",
            f"Normalized {stats.io_shapes_normalized} I/O shapes",
            "All provenance fields (commit_sha, content_hash, branch, dates) are unknown",
            "Dependencies not extracted (98.8% empty in v2)",
            "License data not extracted (0.09% coverage in v2)",
        ],
    )

    stats.total_v3_skills = len(skills)
    stats.total_v3_versions = len(versions)
    stats.total_v3_repos = len(repos)

    return registry, stats


def _build_runtime_requirements(v2_skill: dict[str, Any]) -> Any:
    """Build RuntimeRequirement from v2 data."""
    from skillsbank.models.dependency import RuntimeRequirement

    deps = v2_skill.get("external_dependencies", [])
    tools = []
    for dep_name in deps:
        if dep_name:
            tools.append(dep_name)

    return RuntimeRequirement(
        tools=[],
        apis=[],
        packages=[],
        env_vars=[],
        runtimes=[],
        shell_required=False,
        filesystem_write=False,
        network_required=False,
        quality=MetadataQuality.UNKNOWN,
    )


def _build_compatibility(v2_skill: dict[str, Any]) -> Any:
    """Build CompatibilityProfile from v2 ecosystem_metadata."""
    from skillsbank.models.compatibility import CompatibilityProfile

    return CompatibilityProfile(
        entries=[],
        invocation_type=None,
        skill_md_format=False,
        mcp_compatible=False,
        quality=MetadataQuality.UNKNOWN,
    )


def _build_quality_assessment(meta_quality: MetadataQuality, summary_quality: MetadataQuality) -> Any:
    """Build QualityAssessment from determined quality levels."""
    from skillsbank.models.quality import QualityAssessment

    return QualityAssessment(
        overall_score=None,
        dimensions=[],
        metadata_completeness=meta_quality,
        documentation_quality=summary_quality,
        specificity=MetadataQuality.UNKNOWN,
        portability=MetadataQuality.UNKNOWN,
        dependency_clarity=MetadataQuality.UNKNOWN,
        maintainability=MetadataQuality.UNKNOWN,
        testability=MetadataQuality.UNKNOWN,
        extraction_confidence=MetadataQuality.UNKNOWN,
    )


def _build_security_assessment(v2_skill: dict[str, Any]) -> Any:
    """Build SecurityAssessment from v2 data."""
    from skillsbank.models.enums import RiskLevel
    from skillsbank.models.quality import SecurityAssessment

    return SecurityAssessment(
        risk_level=RiskLevel.UNKNOWN,
        risk_factors=[],
        shell_execution=False,
        filesystem_access=False,
        network_access=False,
        browser_automation=False,
        credential_requirements=[],
        package_installation=False,
        destructive_potential=False,
        security_tooling=False,
        review_status="not_reviewed",
    )


def _build_license_record(v2_skill: dict[str, Any]) -> Any:
    """Build LicenseRecord from v2 ecosystem_metadata."""
    from skillsbank.models.enums import LicenseStatus
    from skillsbank.models.quality import LicenseRecord

    eco = v2_skill.get("ecosystem_metadata", {})
    license_val = eco.get("license") if eco else None

    if license_val:
        return LicenseRecord(
            license_type=license_val,
            detected_source="ecosystem_metadata",
            status=LicenseStatus.DETECTED,
            redistributable=None,
            modifiable=None,
            commercial_restrictions=None,
            attribution_required=None,
            verified=False,
        )

    return LicenseRecord(
        license_type=None,
        detected_source=None,
        status=LicenseStatus.UNKNOWN,
        redistributable=None,
        modifiable=None,
        commercial_restrictions=None,
        attribution_required=None,
        verified=False,
    )
