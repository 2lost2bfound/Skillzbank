"""Registry — the top-level container for all SkillsBank data."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from skillsbank.models.relationship import Relationship, SimilarityRecord
from skillsbank.models.repository import Repository
from skillsbank.models.skill import Skill
from skillsbank.models.skill_version import SkillVersion


class Registry(BaseModel):
    """Top-level SkillsBank registry container.

    Holds all skills, versions, repositories, and relationships.
    This is the root object that gets serialized to registry.v3.json.
    """

    schema_version: str = Field(
        default="3.0.0",
        description="Registry schema version",
    )
    generated_at: datetime = Field(
        description="When this registry was generated",
    )

    # Core collections
    skills: list[Skill] = Field(
        default_factory=list,
        description="Canonical skill identities",
    )
    versions: list[SkillVersion] = Field(
        default_factory=list,
        description="All skill versions",
    )
    repositories: list[Repository] = Field(
        default_factory=list,
        description="Source repositories",
    )

    # Relationships
    relationships: list[Relationship] = Field(
        default_factory=list,
        description="Skill-to-skill relationships",
    )
    similarities: list[SimilarityRecord] = Field(
        default_factory=list,
        description="Computed similarity records",
    )

    # Statistics
    total_skills: int = Field(default=0, ge=0)
    total_versions: int = Field(default=0, ge=0)
    total_repos: int = Field(default=0, ge=0)

    # Migration
    migrated_from: str | None = Field(
        default=None,
        description="Source registry version this was migrated from",
    )
    migration_notes: list[str] = Field(
        default_factory=list,
        description="Notes about the migration process",
    )

    model_config = {"extra": "forbid"}
