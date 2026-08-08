"""Import registry.v3.json into SQLite database.

Semantically lossless: every field from the JSON is persisted either
in a relational column or a JSON blob.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from skillsbank.db.persistence_models import (
    CapabilityRow,
    RepoRow,
    RepoSnapshotRow,
    SkillRow,
    TagRow,
    VersionRow,
)


class ImportStats:
    """Statistics from a v3-to-SQLite import."""

    def __init__(self) -> None:
        self.skills_imported = 0
        self.versions_imported = 0
        self.repos_imported = 0
        self.capabilities_imported = 0
        self.tags_imported = 0
        self.snapshots_imported = 0
        self.errors: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "skills_imported": self.skills_imported,
            "versions_imported": self.versions_imported,
            "repos_imported": self.repos_imported,
            "capabilities_imported": self.capabilities_imported,
            "tags_imported": self.tags_imported,
            "snapshots_imported": self.snapshots_imported,
            "errors": self.errors,
        }


def _parse_dt(val: str | None) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(val)
    except (ValueError, AttributeError):
        return None


def _extract_provenance(prov: dict | None) -> tuple[Any, float | None]:
    """Extract value and confidence from a ProvenancedValue dict."""
    if prov is None:
        return None, None
    if isinstance(prov, dict):
        return prov.get("value"), prov.get("confidence")
    return str(prov), None


def import_skill(session: Session, skill_data: dict) -> SkillRow:
    """Import a single skill into the session."""
    src_val, src_conf = _extract_provenance(skill_data.get("primary_source"))
    path_val, path_conf = _extract_provenance(skill_data.get("primary_path"))

    row = SkillRow(
        id=skill_data["id"],
        canonical_key=skill_data.get("canonical_key"),
        name=skill_data["name"],
        display_name=skill_data.get("display_name"),
        aliases=skill_data.get("aliases", []),
        lifecycle=skill_data.get("lifecycle", "unknown"),
        is_current=skill_data.get("is_current", True),
        primary_source=src_val,
        primary_source_confidence=src_conf,
        primary_path=path_val,
        primary_path_confidence=path_conf,
        first_seen_at=_parse_dt(skill_data.get("first_seen_at")),
        last_updated_at=_parse_dt(skill_data.get("last_updated_at")),
        metadata_quality=skill_data.get("metadata_quality", "UNKNOWN"),
        version_count=skill_data.get("version_count", 0),
        current_version_id=skill_data.get("current_version_id"),
    )
    session.merge(row)
    return row


def import_version(session: Session, ver_data: dict) -> tuple[VersionRow, int, int]:
    """Import a single skill version into the session.

    Returns:
        Tuple of (VersionRow, capability_count, tag_count)
    """
    # Idempotency: delete existing version with same (skill_id, version_id)
    skill_id = ver_data["skill_id"]
    version_id = ver_data.get("version_id")
    existing = session.query(VersionRow).filter_by(skill_id=skill_id, version_id=version_id).first()
    if existing:
        session.delete(existing)
        session.flush()

    source = ver_data.get("source", {})
    domain = ver_data.get("domain", {})
    inp = ver_data.get("input_shape", {})
    out = ver_data.get("output_shape", {})

    primary_domain = domain.get("primary", {})
    domain_name = primary_domain.get("value") if isinstance(primary_domain, dict) else primary_domain
    domain_src = primary_domain.get("source", "unknown") if isinstance(primary_domain, dict) else "unknown"
    secondary = domain.get("secondary", [])

    row = VersionRow(
        skill_id=ver_data["skill_id"],
        version_id=ver_data.get("version_id"),
        source_repo=source.get("repo"),
        source_path=source.get("skill_path"),
        source_commit_sha=source.get("commit_sha"),
        source_branch=source.get("branch"),
        source_content_hash=source.get("content_hash"),
        source_type=source.get("source_type", "unknown"),
        imported_at=_parse_dt(ver_data.get("imported_at")),
        last_checked_at=_parse_dt(ver_data.get("last_checked_at")),
        name=ver_data.get("name", ""),
        display_name=ver_data.get("display_name"),
        summary=ver_data.get("summary"),
        long_description=ver_data.get("long_description"),
        domain_primary=domain_name,
        domain_primary_source=domain_src,
        domain_secondary=secondary,
        input_format=inp.get("format", "unknown"),
        output_format=out.get("format", "unknown"),
        input_json_schema=inp.get("json_schema"),
        output_json_schema=out.get("json_schema"),
        input_required_fields=inp.get("required_fields", []),
        input_optional_fields=inp.get("optional_fields", []),
        runtime_requirements=ver_data.get("runtime_requirements"),
        compatibility=ver_data.get("compatibility"),
        install_methods=ver_data.get("install_methods", []),
        declared_dependencies=ver_data.get("declared_dependencies", []),
        inferred_dependencies=ver_data.get("inferred_dependencies", []),
        quality=ver_data.get("quality"),
        security=ver_data.get("security"),
        license=ver_data.get("license"),
        raw_content=ver_data.get("raw_content"),
        migration=ver_data.get("migration"),
        ecosystem_metadata=ver_data.get("ecosystem_metadata", {}),
    )
    session.add(row)
    session.flush()  # get row.id for FK

    cap_count = 0
    tag_count = 0

    # Import capabilities
    for cap in ver_data.get("capabilities", []):
        cap_name = cap.get("name", "") if isinstance(cap, dict) else str(cap)
        cap_row = CapabilityRow(
            version_id_fk=row.id,
            name=cap_name,
            canonical=cap.get("canonical") if isinstance(cap, dict) else None,
            taxonomy_path=cap.get("taxonomy_path") if isinstance(cap, dict) else None,
        )
        session.add(cap_row)
        cap_count += 1

    # Import tags
    for tag in ver_data.get("tags", []):
        tag_name = tag.get("name", "") if isinstance(tag, dict) else str(tag)
        tag_source = tag.get("source", "imported") if isinstance(tag, dict) else "imported"
        tag_row = TagRow(
            version_id_fk=row.id,
            name=tag_name,
            source=tag_source,
        )
        session.add(tag_row)
        tag_count += 1

    return row, cap_count, tag_count


def import_repo(session: Session, repo_data: dict) -> RepoRow:
    """Import a single repository into the session."""
    row = RepoRow(
        id=repo_data["id"],
        url=repo_data.get("url"),
        owner=repo_data.get("owner"),
        name=repo_data.get("name"),
        source_type=repo_data.get("source_type", "unknown"),
        license=repo_data.get("license"),
        default_branch=repo_data.get("default_branch"),
        description=repo_data.get("description"),
        ecosystem=repo_data.get("ecosystem"),
        parser_compatibility=repo_data.get("parser_compatibility"),
        last_successful_sync=_parse_dt(repo_data.get("last_successful_sync")),
        sync_errors=repo_data.get("sync_errors", []),
        skill_count=repo_data.get("skill_count", 0),
    )
    session.merge(row)
    session.flush()

    # Clear existing snapshots for idempotency
    session.query(RepoSnapshotRow).filter_by(repo_id=row.id).delete()

    for snap in repo_data.get("snapshots", []):
        snap_row = RepoSnapshotRow(
            repo_id=row.id,
            snapshot_at=_parse_dt(snap.get("snapshot_at")) or datetime.now(UTC),
            commit_sha=snap.get("commit_sha"),
            stars=snap.get("stars"),
            forks=snap.get("forks"),
            open_issues=snap.get("open_issues"),
            archived=snap.get("archived"),
            default_branch=snap.get("default_branch"),
            last_push=_parse_dt(snap.get("last_push")),
            skill_count=snap.get("skill_count", 0),
            release_tag=snap.get("release_tag"),
            notes=snap.get("notes"),
        )
        session.add(snap_row)

    return row


def import_v3_to_sqlite(session: Session, v3_path: str | Path) -> ImportStats:
    """Import a registry.v3.json file into the SQLite database.

    Args:
        session: SQLAlchemy session (caller manages transaction)
        v3_path: Path to registry.v3.json

    Returns:
        ImportStats with counts and errors
    """
    stats = ImportStats()

    with open(v3_path) as f:
        data = json.load(f)

    # Import repositories first (no FK dependencies)
    for repo_data in data.get("repositories", []):
        try:
            import_repo(session, repo_data)
            stats.repos_imported += 1
        except Exception as e:
            stats.errors.append(f"repo {repo_data.get('id')}: {e}")

    # Import skills
    for skill_data in data.get("skills", []):
        try:
            import_skill(session, skill_data)
            stats.skills_imported += 1
        except Exception as e:
            stats.errors.append(f"skill {skill_data.get('id')}: {e}")

    # Import versions (depends on skills)
    for ver_data in data.get("versions", []):
        try:
            _, cap_count, tag_count = import_version(session, ver_data)
            stats.versions_imported += 1
            stats.capabilities_imported += cap_count
            stats.tags_imported += tag_count
        except Exception as e:
            stats.errors.append(f"version {ver_data.get('skill_id')}:{ver_data.get('version_id')}: {e}")

    session.commit()
    return stats
