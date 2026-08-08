"""Incremental sync and change tracking for SkillsBank.

Compares incoming skill data against stored state using content hashes
to detect additions, modifications, and removals. Tracks all changes
in a changelog for auditability.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Session

from skillsbank.db.persistence_models import (
    CapabilityRow,
    RepoRow,
    SkillRow,
    TagRow,
    VersionRow,
)


class ChangeType(str, Enum):
    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    REMOVED = "REMOVED"
    MOVED = "MOVED"
    RENAMED = "RENAMED"
    UNCHANGED = "UNCHANGED"


@dataclass
class ChangeRecord:
    """A single detected change."""

    change_type: ChangeType
    entity_type: str  # "skill", "version", "repo", "capability", "tag"
    entity_id: str
    field_name: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    details: str | None = None


@dataclass
class SyncResult:
    """Result of a sync operation."""

    sync_id: str
    started_at: datetime
    completed_at: datetime | None = None
    skills_added: int = 0
    skills_modified: int = 0
    skills_removed: int = 0
    skills_unchanged: int = 0
    versions_added: int = 0
    versions_modified: int = 0
    repos_added: int = 0
    repos_modified: int = 0
    changes: list[ChangeRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_skill_hash(
    name: str,
    summary: str,
    source_path: str,
    raw_content: str | None = None,
) -> str:
    """Compute a composite hash for a skill based on key fields."""
    parts = [name, summary or "", source_path or ""]
    if raw_content:
        parts.append(raw_content)
    combined = "|".join(parts)
    return compute_content_hash(combined)


def _get_existing_hashes(session: Session) -> dict[str, dict]:
    """Get content hashes and metadata for all existing skills."""
    stmt = sa.select(
        SkillRow.id,
        SkillRow.name,
        SkillRow.primary_source,
        VersionRow.source_path,
        VersionRow.source_content_hash,
        VersionRow.summary,
        VersionRow.name.label("version_name"),
    ).join(VersionRow, SkillRow.id == VersionRow.skill_id)

    result = session.execute(stmt)
    existing = {}
    for row in result:
        skill_id = row.id
        if skill_id not in existing:
            existing[skill_id] = {
                "id": skill_id,
                "name": row.name,
                "source": row.primary_source,
                "path": row.source_path,
                "content_hash": row.source_content_hash,
                "summary": row.summary,
                "version_name": row.version_name,
            }
    return existing


def _get_existing_repos(session: Session) -> dict[str, dict]:
    """Get metadata for all existing repos."""
    stmt = sa.select(RepoRow)
    repos = session.execute(stmt).scalars().all()
    return {
        repo.id: {
            "id": repo.id,
            "url": repo.url,
            "owner": repo.owner,
            "name": repo.name,
            "description": repo.description,
            "skill_count": repo.skill_count,
        }
        for repo in repos
    }


@dataclass
class IncomingSkill:
    """Skill data from a fresh parse/fetch."""

    skill_id: str
    name: str
    summary: str
    source_path: str
    source_repo: str
    raw_content: str | None = None
    capabilities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    domain: str | None = None


def detect_changes(
    session: Session,
    incoming: list[IncomingSkill],
) -> SyncResult:
    """Compare incoming skills against DB state and detect changes.

    Returns a SyncResult with all detected changes without applying them.
    """
    sync_id = uuid.uuid4().hex[:12]
    result = SyncResult(
        sync_id=sync_id,
        started_at=datetime.now(UTC),
    )

    existing = _get_existing_hashes(session)
    incoming_map = {s.skill_id: s for s in incoming}

    # Check for modifications and additions
    for skill in incoming:
        if skill.skill_id in existing:
            ex = existing[skill.skill_id]
            old_hash = compute_skill_hash(ex["name"], ex["summary"] or "", ex["path"] or "")
            new_hash = compute_skill_hash(skill.name, skill.summary, skill.source_path, skill.raw_content)

            if old_hash != new_hash:
                result.skills_modified += 1
                result.changes.append(
                    ChangeRecord(
                        change_type=ChangeType.MODIFIED,
                        entity_type="skill",
                        entity_id=skill.skill_id,
                        field_name="content_hash",
                        old_value=old_hash,
                        new_value=new_hash,
                        details=f"Content changed for {skill.name}",
                    )
                )

                # Detect specific field changes
                if ex["name"] != skill.name:
                    result.changes.append(
                        ChangeRecord(
                            change_type=ChangeType.MODIFIED,
                            entity_type="skill",
                            entity_id=skill.skill_id,
                            field_name="name",
                            old_value=ex["name"],
                            new_value=skill.name,
                        )
                    )
                if (ex["summary"] or "") != skill.summary:
                    result.changes.append(
                        ChangeRecord(
                            change_type=ChangeType.MODIFIED,
                            entity_type="skill",
                            entity_id=skill.skill_id,
                            field_name="summary",
                            old_value=ex["summary"],
                            new_value=skill.summary,
                        )
                    )
                if (ex["path"] or "") != skill.source_path:
                    result.changes.append(
                        ChangeRecord(
                            change_type=ChangeType.MOVED,
                            entity_type="skill",
                            entity_id=skill.skill_id,
                            field_name="source_path",
                            old_value=ex["path"],
                            new_value=skill.source_path,
                        )
                    )
            else:
                result.skills_unchanged += 1
        else:
            result.skills_added += 1
            result.changes.append(
                ChangeRecord(
                    change_type=ChangeType.ADDED,
                    entity_type="skill",
                    entity_id=skill.skill_id,
                    details=f"New skill: {skill.name}",
                )
            )

    # Check for removals
    for skill_id, ex in existing.items():
        if skill_id not in incoming_map:
            result.skills_removed += 1
            result.changes.append(
                ChangeRecord(
                    change_type=ChangeType.REMOVED,
                    entity_type="skill",
                    entity_id=skill_id,
                    details=f"Skill removed: {ex['name']}",
                )
            )

    result.completed_at = datetime.now(UTC)
    return result


def apply_sync(
    session: Session,
    incoming: list[IncomingSkill],
    dry_run: bool = False,
) -> SyncResult:
    """Apply sync changes to the database.

    If dry_run=True, detects changes but doesn't apply them.
    """
    result = detect_changes(session, incoming)

    if dry_run:
        return result

    incoming_map = {s.skill_id: s for s in incoming}
    _get_existing_hashes(session)

    # Apply additions
    for change in result.changes:
        if change.change_type == ChangeType.ADDED and change.entity_type == "skill":
            skill_data = incoming_map.get(change.entity_id)
            if skill_data:
                _add_skill(session, skill_data)
                result.versions_added += 1

    # Apply modifications (deduplicate by skill_id to avoid double-increment)
    modified_ids = set()
    for change in result.changes:
        if change.change_type == ChangeType.MODIFIED and change.entity_type == "skill":
            if change.entity_id not in modified_ids:
                modified_ids.add(change.entity_id)
                skill_data = incoming_map.get(change.entity_id)
                if skill_data:
                    _update_skill(session, change.entity_id, skill_data)
                    result.versions_added += 1

    # Apply removals (mark as archived, don't delete)
    for change in result.changes:
        if change.change_type == ChangeType.REMOVED and change.entity_type == "skill":
            _archive_skill(session, change.entity_id)

    # Store changelog
    _store_changelog(session, result)

    session.commit()
    result.completed_at = datetime.now(UTC)
    return result


def _add_skill(session: Session, skill: IncomingSkill) -> SkillRow:
    """Add a new skill with its first version."""
    now = datetime.now(UTC)
    skill_row = SkillRow(
        id=skill.skill_id,
        name=skill.name,
        display_name=skill.name,
        lifecycle="current",
        is_current=True,
        primary_source=skill.source_repo,
        primary_path=skill.source_path,
        first_seen_at=now,
        last_updated_at=now,
        metadata_quality="UNKNOWN",
        version_count=1,
    )
    session.add(skill_row)
    session.flush()

    content_hash = compute_skill_hash(skill.name, skill.summary, skill.source_path, skill.raw_content)
    version_row = VersionRow(
        skill_id=skill.skill_id,
        version_id=skill.skill_id + "-v1",
        name=skill.name,
        summary=skill.summary,
        source_repo=skill.source_repo,
        source_path=skill.source_path,
        source_content_hash=content_hash,
        domain_primary=skill.domain,
        raw_content=skill.raw_content,
        imported_at=now,
    )
    session.add(version_row)
    session.flush()

    # Add capabilities
    for cap_name in skill.capabilities:
        cap = CapabilityRow(
            version_id_fk=version_row.id,
            name=cap_name,
        )
        session.add(cap)

    # Add tags
    for tag_name in skill.tags:
        tag = TagRow(
            version_id_fk=version_row.id,
            name=tag_name,
        )
        session.add(tag)

    return skill_row


def _update_skill(session: Session, skill_id: str, skill: IncomingSkill) -> None:
    """Update an existing skill by creating a new version."""
    skill_row = session.get(SkillRow, skill_id)
    if not skill_row:
        return

    now = datetime.now(UTC)
    skill_row.last_updated_at = now
    skill_row.version_count = (skill_row.version_count or 0) + 1
    skill_row.name = skill.name

    content_hash = compute_skill_hash(skill.name, skill.summary, skill.source_path, skill.raw_content)
    version_row = VersionRow(
        skill_id=skill_id,
        version_id=f"{skill_id}-v{skill_row.version_count}",
        name=skill.name,
        summary=skill.summary,
        source_repo=skill.source_repo,
        source_path=skill.source_path,
        source_content_hash=content_hash,
        domain_primary=skill.domain,
        raw_content=skill.raw_content,
        imported_at=now,
    )
    session.add(version_row)
    session.flush()

    for cap_name in skill.capabilities:
        cap = CapabilityRow(version_id_fk=version_row.id, name=cap_name)
        session.add(cap)

    for tag_name in skill.tags:
        tag = TagRow(version_id_fk=version_row.id, name=tag_name)
        session.add(tag)


def _archive_skill(session: Session, skill_id: str) -> None:
    """Mark a skill as archived (soft delete)."""
    skill_row = session.get(SkillRow, skill_id)
    if skill_row:
        skill_row.lifecycle = "archived"
        skill_row.is_current = False
        skill_row.last_updated_at = datetime.now(UTC)


def _store_changelog(session: Session, result: SyncResult) -> None:
    """Store change records in a changelog table.

    Creates the table if it doesn't exist.
    """
    # Create changelog table if not exists
    session.execute(
        sa.text("""
        CREATE TABLE IF NOT EXISTS sync_changelog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_id TEXT NOT NULL,
            change_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            field_name TEXT,
            old_value TEXT,
            new_value TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    )

    for change in result.changes:
        session.execute(
            sa.text("""
            INSERT INTO sync_changelog
                (sync_id, change_type, entity_type, entity_id, field_name, old_value, new_value, details)
            VALUES
                (:sync_id, :change_type, :entity_type, :entity_id, :field_name, :old_value, :new_value, :details)
        """),
            {
                "sync_id": result.sync_id,
                "change_type": change.change_type.value,
                "entity_type": change.entity_type,
                "entity_id": change.entity_id,
                "field_name": change.field_name,
                "old_value": change.old_value,
                "new_value": change.new_value,
                "details": change.details,
            },
        )


def get_sync_history(session: Session, limit: int = 10) -> list[dict]:
    """Get recent sync history from changelog."""
    session.execute(
        sa.text("""
        CREATE TABLE IF NOT EXISTS sync_changelog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_id TEXT NOT NULL,
            change_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            field_name TEXT,
            old_value TEXT,
            new_value TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    )

    result = session.execute(
        sa.text("""
        SELECT sync_id, change_type, COUNT(*) as count, MIN(created_at) as started_at
        FROM sync_changelog
        GROUP BY sync_id, change_type
        ORDER BY started_at DESC
        LIMIT :limit
    """),
        {"limit": limit * 5},
    )  # Multiple change types per sync

    rows = result.fetchall()
    syncs: dict[str, dict] = {}
    for row in rows:
        sid = row[0]
        if sid not in syncs:
            syncs[sid] = {"sync_id": sid, "started_at": row[3], "changes": {}}
        syncs[sid]["changes"][row[1]] = row[2]

    return list(syncs.values())[:limit]


def get_skill_history(session: Session, skill_id: str) -> list[dict]:
    """Get change history for a specific skill."""
    session.execute(
        sa.text("""
        CREATE TABLE IF NOT EXISTS sync_changelog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_id TEXT NOT NULL,
            change_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            field_name TEXT,
            old_value TEXT,
            new_value TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    )

    result = session.execute(
        sa.text("""
        SELECT change_type, field_name, old_value, new_value, details, created_at
        FROM sync_changelog
        WHERE entity_id = :skill_id
        ORDER BY created_at DESC
    """),
        {"skill_id": skill_id},
    )

    return [
        {
            "change_type": row[0],
            "field_name": row[1],
            "old_value": row[2],
            "new_value": row[3],
            "details": row[4],
            "created_at": row[5],
        }
        for row in result.fetchall()
    ]
