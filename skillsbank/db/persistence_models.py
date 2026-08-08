"""SQLAlchemy persistence models for SkillsBank.

Design: relational columns for core searchable fields (id, name, repo,
domain, capabilities, tags), JSON blobs for complex nested structures
(quality, security, dependencies, I/O shapes, ecosystem_metadata).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from skillsbank.db.base import Base


class SkillRow(Base):
    """Canonical skill identity — mirrors Skill domain model."""

    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    canonical_key: Mapped[str | None] = mapped_column(String(512), index=True)
    name: Mapped[str] = mapped_column(String(512), index=True)
    display_name: Mapped[str | None] = mapped_column(String(512))
    aliases: Mapped[list | None] = mapped_column(JSON, default=list)
    lifecycle: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    primary_source: Mapped[str | None] = mapped_column(String(512), index=True)
    primary_source_confidence: Mapped[float | None] = mapped_column(Float)
    primary_path: Mapped[str | None] = mapped_column(String(1024))
    primary_path_confidence: Mapped[float | None] = mapped_column(Float)

    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    metadata_quality: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    version_count: Mapped[int] = mapped_column(Integer, default=0)
    current_version_id: Mapped[str | None] = mapped_column(String(36))

    versions: Mapped[list[VersionRow]] = relationship(back_populates="skill", cascade="all, delete-orphan")


class VersionRow(Base):
    """A specific imported version — mirrors SkillVersion domain model."""

    __tablename__ = "versions"
    __table_args__ = (
        UniqueConstraint("skill_id", "version_id", name="uq_skill_version"),
        Index("ix_versions_domain_repo", "domain_primary", "source_repo"),
        Index("ix_versions_skill_version", "skill_id", "version_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[str] = mapped_column(String(36), ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[str | None] = mapped_column(String(36), index=True)

    source_repo: Mapped[str | None] = mapped_column(String(512), index=True)
    source_path: Mapped[str | None] = mapped_column(String(1024))
    source_commit_sha: Mapped[str | None] = mapped_column(String(64))
    source_branch: Mapped[str | None] = mapped_column(String(256))
    source_content_hash: Mapped[str | None] = mapped_column(String(128))
    source_type: Mapped[str] = mapped_column(String(32), default="unknown")
    imported_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime)

    name: Mapped[str] = mapped_column(String(512))
    display_name: Mapped[str | None] = mapped_column(String(512))
    summary: Mapped[str | None] = mapped_column(Text)
    long_description: Mapped[str | None] = mapped_column(Text)

    domain_primary: Mapped[str | None] = mapped_column(String(256), index=True)
    domain_primary_source: Mapped[str] = mapped_column(String(32), default="unknown")
    domain_secondary: Mapped[list | None] = mapped_column(JSON, default=list)

    input_format: Mapped[str] = mapped_column(String(32), default="unknown")
    output_format: Mapped[str] = mapped_column(String(32), default="unknown")
    input_json_schema: Mapped[dict | None] = mapped_column(JSON)
    output_json_schema: Mapped[dict | None] = mapped_column(JSON)
    input_required_fields: Mapped[list | None] = mapped_column(JSON, default=list)
    input_optional_fields: Mapped[list | None] = mapped_column(JSON, default=list)

    runtime_requirements: Mapped[dict | None] = mapped_column(JSON)
    compatibility: Mapped[dict | None] = mapped_column(JSON)
    install_methods: Mapped[list | None] = mapped_column(JSON, default=list)
    declared_dependencies: Mapped[list | None] = mapped_column(JSON, default=list)
    inferred_dependencies: Mapped[list | None] = mapped_column(JSON, default=list)

    quality: Mapped[dict | None] = mapped_column(JSON)
    security: Mapped[dict | None] = mapped_column(JSON)
    license: Mapped[dict | None] = mapped_column(JSON)

    raw_content: Mapped[str | None] = mapped_column(Text)
    migration: Mapped[dict | None] = mapped_column(JSON)
    ecosystem_metadata: Mapped[dict | None] = mapped_column(JSON, default=dict)

    skill: Mapped[SkillRow] = relationship(back_populates="versions")
    capabilities: Mapped[list[CapabilityRow]] = relationship(back_populates="version", cascade="all, delete-orphan")
    tags: Mapped[list[TagRow]] = relationship(back_populates="version", cascade="all, delete-orphan")


class CapabilityRow(Base):
    """Searchable capability entry linked to a version."""

    __tablename__ = "capabilities"
    __table_args__ = (
        UniqueConstraint("version_id_fk", "name", name="uq_version_capability"),
        Index("ix_capabilities_version_name", "version_id_fk", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id_fk: Mapped[int] = mapped_column(Integer, ForeignKey("versions.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    canonical: Mapped[str | None] = mapped_column(String(256), index=True)
    taxonomy_path: Mapped[str | None] = mapped_column(String(512))

    version: Mapped[VersionRow] = relationship(back_populates="capabilities")


class TagRow(Base):
    """Searchable tag entry linked to a version."""

    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("version_id_fk", "name", "source", name="uq_version_tag"),
        Index("ix_tags_version_name", "version_id_fk", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id_fk: Mapped[int] = mapped_column(Integer, ForeignKey("versions.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    source: Mapped[str] = mapped_column(String(64), default="imported")

    version: Mapped[VersionRow] = relationship(back_populates="tags")


class RepoRow(Base):
    """Source repository — mirrors Repository domain model."""

    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(512), primary_key=True)
    url: Mapped[str | None] = mapped_column(String(1024))
    owner: Mapped[str | None] = mapped_column(String(256), index=True)
    name: Mapped[str | None] = mapped_column(String(256))
    source_type: Mapped[str] = mapped_column(String(32), default="unknown")
    license: Mapped[dict | None] = mapped_column(JSON)
    default_branch: Mapped[str | None] = mapped_column(String(256))
    description: Mapped[str | None] = mapped_column(Text)
    ecosystem: Mapped[str | None] = mapped_column(String(64), index=True)
    parser_compatibility: Mapped[str | None] = mapped_column(String(128))
    last_successful_sync: Mapped[datetime | None] = mapped_column(DateTime)
    sync_errors: Mapped[list | None] = mapped_column(JSON, default=list)
    skill_count: Mapped[int] = mapped_column(Integer, default=0)

    snapshots: Mapped[list[RepoSnapshotRow]] = relationship(back_populates="repo", cascade="all, delete-orphan")


class RepoSnapshotRow(Base):
    """Point-in-time repository snapshot."""

    __tablename__ = "repo_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_id: Mapped[str] = mapped_column(String(512), ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime)
    commit_sha: Mapped[str | None] = mapped_column(String(64))
    stars: Mapped[int | None] = mapped_column(Integer)
    forks: Mapped[int | None] = mapped_column(Integer)
    open_issues: Mapped[int | None] = mapped_column(Integer)
    archived: Mapped[bool | None] = mapped_column(Boolean)
    default_branch: Mapped[str | None] = mapped_column(String(256))
    last_push: Mapped[datetime | None] = mapped_column(DateTime)
    skill_count: Mapped[int] = mapped_column(Integer, default=0)
    release_tag: Mapped[str | None] = mapped_column(String(256))
    notes: Mapped[str | None] = mapped_column(Text)

    repo: Mapped[RepoRow] = relationship(back_populates="snapshots")


class RelationshipRow(Base):
    """Skill-to-skill relationship."""

    __tablename__ = "relationships"
    __table_args__ = (UniqueConstraint("source_id", "target_id", "rel_type", name="uq_relationship"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    target_id: Mapped[str] = mapped_column(String(36), ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    rel_type: Mapped[str] = mapped_column(String(64), index=True)
    confidence: Mapped[float | None] = mapped_column(Float)
    evidence: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)


class SimilarityRow(Base):
    """Computed similarity between two skills."""

    __tablename__ = "similarities"
    __table_args__ = (UniqueConstraint("skill_a_id", "skill_b_id", name="uq_similarity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_a_id: Mapped[str] = mapped_column(String(36), ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    skill_b_id: Mapped[str] = mapped_column(String(36), ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    overall_score: Mapped[float] = mapped_column(Float, index=True)
    dimensions: Mapped[dict | None] = mapped_column(JSON)
    classification: Mapped[str | None] = mapped_column(String(64))
    computed_at: Mapped[datetime | None] = mapped_column(DateTime)
