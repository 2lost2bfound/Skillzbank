"""Skill — the canonical identity of an agent skill."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from skillsbank.models.common import ProvenancedValue
from skillsbank.models.enums import LifecycleStatus, MetadataQuality


class Skill(BaseModel):
    """Canonical identity of a skill, independent of any specific version.

    A Skill persists across name changes, repo moves, content updates,
    and schema migrations. Its stable identity is the UUID5 id.
    """

    # Identity (immutable)
    id: str = Field(
        description="Stable UUID5 identifier, derived from canonical URL",
    )
    canonical_key: str | None = Field(
        default=None,
        description="Human-readable canonical key, e.g. 'mattpocock/skills/code-review'",
    )

    # Display (current best-known values)
    name: str = Field(
        description="Current canonical name",
    )
    display_name: str | None = Field(
        default=None,
        description="Human-friendly display name",
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Known aliases for this skill",
    )

    # Lifecycle
    lifecycle: LifecycleStatus = Field(
        default=LifecycleStatus.UNKNOWN,
        description="Current lifecycle status",
    )
    is_current: bool = Field(
        default=True,
        description="Whether this skill is considered current/active",
    )

    # Provenance
    primary_source: ProvenancedValue = Field(
        description="Primary source repo (owner/repo)",
    )
    primary_path: ProvenancedValue = Field(
        description="Primary skill path in repo",
    )

    # Lifecycle timestamps
    first_seen_at: datetime | None = Field(
        default=None,
        description="When this skill was first imported",
    )
    last_updated_at: datetime | None = Field(
        default=None,
        description="When this skill was last updated",
    )

    # Quality summary
    metadata_quality: MetadataQuality = Field(
        default=MetadataQuality.UNKNOWN,
        description="Overall metadata quality status",
    )

    # Version tracking
    version_count: int = Field(
        default=0,
        description="Number of imported versions",
    )
    current_version_id: str | None = Field(
        default=None,
        description="ID of the current/latest version",
    )

    model_config = {"extra": "forbid"}
