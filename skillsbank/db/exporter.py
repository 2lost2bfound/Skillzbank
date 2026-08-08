"""Export SQLite database back to registry.v3.json.

Semantically lossless round-trip: the exported JSON should be
structurally equivalent to the original v3 JSON.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from skillsbank.db.persistence_models import (
    RepoRow,
    SkillRow,
    VersionRow,
)


def _dt_str(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat() + "Z" if dt.tzinfo is None else dt.isoformat()


def _prov(value: Any, source: str = "unknown", confidence: float | None = None) -> dict:
    return {"value": value, "source": source, "confidence": confidence}


def export_skill(row: SkillRow) -> dict:
    return {
        "id": row.id,
        "canonical_key": row.canonical_key,
        "name": row.name,
        "display_name": row.display_name,
        "aliases": row.aliases or [],
        "lifecycle": row.lifecycle,
        "is_current": row.is_current,
        "primary_source": _prov(row.primary_source, "imported", row.primary_source_confidence),
        "primary_path": _prov(row.primary_path, "imported", row.primary_path_confidence),
        "first_seen_at": _dt_str(row.first_seen_at),
        "last_updated_at": _dt_str(row.last_updated_at),
        "metadata_quality": row.metadata_quality,
        "version_count": row.version_count,
        "current_version_id": row.current_version_id,
    }


def export_version(row: VersionRow) -> dict:
    caps = [
        {
            "name": c.name,
            "canonical": c.canonical,
            "taxonomy_path": c.taxonomy_path,
        }
        for c in (row.capabilities or [])
    ]
    tags = [{"name": t.name, "source": t.source} for t in (row.tags or [])]

    return {
        "skill_id": row.skill_id,
        "version_id": row.version_id,
        "source": {
            "repo": row.source_repo,
            "owner": row.source_repo.split("/")[0] if row.source_repo and "/" in row.source_repo else None,
            "repo_url": f"https://github.com/{row.source_repo}" if row.source_repo else None,
            "skill_path": row.source_path,
            "commit_sha": row.source_commit_sha,
            "branch": row.source_branch,
            "content_hash": row.source_content_hash,
            "source_type": row.source_type,
            "upstream_updated_at": None,
            "upstream_created_at": None,
        },
        "imported_at": _dt_str(row.imported_at),
        "last_checked_at": _dt_str(row.last_checked_at),
        "name": row.name,
        "display_name": row.display_name,
        "summary": row.summary,
        "long_description": row.long_description,
        "domain": {
            "primary": _prov(row.domain_primary, row.domain_primary_source),
            "secondary": row.domain_secondary or [],
            "source": row.domain_primary_source,
        },
        "capabilities": caps,
        "tags": tags,
        "input_shape": {
            "format": row.input_format,
            "required_fields": row.input_required_fields or [],
            "optional_fields": row.input_optional_fields or [],
            "json_schema": row.input_json_schema,
        },
        "output_shape": {
            "format": row.output_format,
            "json_schema": row.output_json_schema,
        },
        "declared_dependencies": row.declared_dependencies or [],
        "inferred_dependencies": row.inferred_dependencies or [],
        "runtime_requirements": row.runtime_requirements or {},
        "compatibility": row.compatibility or {},
        "install_methods": row.install_methods or [],
        "quality": row.quality or {},
        "security": row.security or {},
        "license": row.license or {},
        "raw_content": row.raw_content,
        "migration": row.migration or {},
        "ecosystem_metadata": row.ecosystem_metadata or {},
    }


def export_repo(row: RepoRow) -> dict:
    snaps = [
        {
            "snapshot_at": _dt_str(s.snapshot_at),
            "commit_sha": s.commit_sha,
            "stars": s.stars,
            "forks": s.forks,
            "open_issues": s.open_issues,
            "archived": s.archived,
            "default_branch": s.default_branch,
            "last_push": _dt_str(s.last_push),
            "skill_count": s.skill_count,
            "release_tag": s.release_tag,
            "notes": s.notes,
        }
        for s in (row.snapshots or [])
    ]

    return {
        "id": row.id,
        "url": row.url,
        "owner": row.owner,
        "name": row.name,
        "source_type": row.source_type,
        "license": row.license or {},
        "default_branch": row.default_branch,
        "description": row.description,
        "ecosystem": row.ecosystem,
        "parser_compatibility": row.parser_compatibility,
        "last_successful_sync": _dt_str(row.last_successful_sync),
        "sync_errors": row.sync_errors or [],
        "snapshots": snaps,
        "skill_count": row.skill_count,
    }


def export_sqlite_to_v3(session: Session, output_path: str | Path) -> dict:
    """Export the SQLite database to registry.v3.json.

    Args:
        session: SQLAlchemy session
        output_path: Where to write the JSON

    Returns:
        Dict with export statistics
    """
    # Load all skills
    skills = session.execute(select(SkillRow)).scalars().all()
    skill_dicts = [export_skill(s) for s in skills]

    # Load all versions with relationships eagerly
    versions = (
        session.execute(
            select(VersionRow).options(
                joinedload(VersionRow.capabilities),
                joinedload(VersionRow.tags),
            )
        )
        .unique()
        .scalars()
        .all()
    )
    version_dicts = [export_version(v) for v in versions]

    # Load all repos with snapshots
    repos = session.execute(select(RepoRow).options(joinedload(RepoRow.snapshots))).unique().scalars().all()
    repo_dicts = [export_repo(r) for r in repos]

    registry = {
        "schema_version": "3.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "skills": skill_dicts,
        "versions": version_dicts,
        "repositories": repo_dicts,
        "relationships": [],
        "similarities": [],
        "total_skills": len(skill_dicts),
        "total_versions": len(version_dicts),
        "total_repos": len(repo_dicts),
        "migrated_from": "sqlite_export",
        "migration_notes": [
            (f"Exported from SQLite: {len(skill_dicts)} skills, {len(version_dicts)} versions, {len(repo_dicts)} repos")
        ],
    }

    with open(output_path, "w") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)

    return {
        "skills_exported": len(skill_dicts),
        "versions_exported": len(version_dicts),
        "repos_exported": len(repo_dicts),
        "output_path": str(output_path),
    }
