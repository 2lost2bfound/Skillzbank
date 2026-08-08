"""SkillSource — the origin location of a skill."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from skillsbank.models.enums import SourceType


class SkillSource(BaseModel):
    """Where a skill lives upstream."""

    repo: str = Field(
        description="Repository identifier, e.g. mattpocock/skills",
    )
    owner: str | None = Field(
        default=None,
        description="Repository owner, e.g. mattpocock",
    )
    repo_url: str | None = Field(
        default=None,
        description="Full repository URL",
    )
    skill_path: str = Field(
        description="Path to the skill file within the repository",
    )
    commit_sha: str | None = Field(
        default=None,
        description="Git commit SHA at time of import",
    )
    branch: str | None = Field(
        default=None,
        description="Git branch or tag",
    )
    content_hash: str | None = Field(
        default=None,
        description="SHA256 hash of the skill file content",
    )
    source_type: SourceType = Field(
        default=SourceType.UNKNOWN,
        description="Type of source",
    )
    upstream_created_at: datetime | None = Field(
        default=None,
        description="When the skill file was created upstream",
    )
    upstream_updated_at: datetime | None = Field(
        default=None,
        description="When the skill file was last updated upstream",
    )

    model_config = {"extra": "forbid"}
