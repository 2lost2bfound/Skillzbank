"""Repository and RepositorySnapshot models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from skillsbank.models.enums import SourceType
from skillsbank.models.quality import LicenseRecord


class RepositorySnapshot(BaseModel):
    """A point-in-time snapshot of repository metadata."""

    snapshot_at: datetime = Field(
        description="When this snapshot was taken",
    )
    commit_sha: str | None = Field(
        default=None,
        description="HEAD commit at snapshot time",
    )
    stars: int | None = Field(default=None, ge=0)
    forks: int | None = Field(default=None, ge=0)
    open_issues: int | None = Field(default=None, ge=0)
    archived: bool | None = Field(default=None)
    default_branch: str | None = Field(default=None)
    last_push: datetime | None = Field(default=None)
    skill_count: int = Field(
        default=0,
        ge=0,
        description="Number of skills found at snapshot time",
    )
    release_tag: str | None = Field(default=None)
    notes: str | None = Field(default=None)

    model_config = {"extra": "forbid"}


class Repository(BaseModel):
    """A source repository that contains skills."""

    id: str = Field(
        description="Repository identifier, e.g. 'mattpocock/skills'",
    )
    url: str | None = Field(
        default=None,
        description="Full repository URL",
    )
    owner: str | None = Field(default=None)
    name: str | None = Field(default=None)
    source_type: SourceType = Field(
        default=SourceType.UNKNOWN,
        description="Type of source",
    )
    license: LicenseRecord = Field(
        default_factory=lambda: LicenseRecord(),
        description="Repository-level license",
    )
    default_branch: str | None = Field(default=None)
    description: str | None = Field(default=None)
    ecosystem: str | None = Field(
        default=None,
        description="Primary ecosystem: claude, codex, generic, etc.",
    )
    parser_compatibility: str | None = Field(
        default=None,
        description="Which parser works with this repo",
    )
    last_successful_sync: datetime | None = Field(
        default=None,
    )
    sync_errors: list[str] = Field(default_factory=list)
    snapshots: list[RepositorySnapshot] = Field(
        default_factory=list,
        description="Historical snapshots",
    )
    skill_count: int = Field(
        default=0,
        ge=0,
        description="Current known skill count",
    )

    model_config = {"extra": "forbid"}
