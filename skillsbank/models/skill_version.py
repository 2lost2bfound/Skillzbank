"""SkillVersion — a specific version/import of a skill."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from skillsbank.models.classification import Capability, Domain, Tag
from skillsbank.models.common import MigrationMetadata
from skillsbank.models.compatibility import CompatibilityProfile, InstallMethod
from skillsbank.models.dependency import Dependency, RuntimeRequirement
from skillsbank.models.io_shapes import InputShape, OutputShape
from skillsbank.models.quality import (
    LicenseRecord,
    QualityAssessment,
    SecurityAssessment,
)
from skillsbank.models.skill_source import SkillSource


class SkillVersion(BaseModel):
    """A specific imported version of a skill.

    Captures the exact state of a skill at a point in time,
    including all extracted metadata and provenance.
    """

    # Identity
    skill_id: str = Field(
        description="Canonical skill ID this version belongs to",
    )
    version_id: str | None = Field(
        default=None,
        description="Unique version identifier (e.g. content_hash or sequential)",
    )

    # Source
    source: SkillSource = Field(
        description="Where this version was imported from",
    )
    imported_at: datetime = Field(
        description="When this version was imported",
    )
    last_checked_at: datetime | None = Field(
        default=None,
        description="When upstream was last checked for changes",
    )

    # Display
    name: str = Field(description="Skill name as extracted")
    display_name: str | None = Field(
        default=None,
        description="Human-friendly display name",
    )
    summary: str | None = Field(
        default=None,
        description="Short description of the skill",
    )
    long_description: str | None = Field(
        default=None,
        description="Full description or body content",
    )

    # Classification
    domain: Domain = Field(
        default_factory=lambda: Domain(),
        description="Domain classification",
    )
    capabilities: list[Capability] = Field(
        default_factory=list,
        description="Skill capabilities",
    )
    tags: list[Tag] = Field(
        default_factory=list,
        description="Categorization tags",
    )

    # I/O
    input_shape: InputShape = Field(
        default_factory=lambda: InputShape(),
        description="Expected input format",
    )
    output_shape: OutputShape = Field(
        default_factory=lambda: OutputShape(),
        description="Produced output format",
    )

    # Dependencies
    declared_dependencies: list[Dependency] = Field(
        default_factory=list,
        description="Dependencies declared in the skill source",
    )
    inferred_dependencies: list[Dependency] = Field(
        default_factory=list,
        description="Dependencies inferred from content analysis",
    )
    runtime_requirements: RuntimeRequirement = Field(
        default_factory=lambda: RuntimeRequirement(),
        description="Aggregate runtime requirements",
    )

    # Compatibility
    compatibility: CompatibilityProfile = Field(
        default_factory=lambda: CompatibilityProfile(),
        description="Agent/ecosystem compatibility",
    )
    install_methods: list[InstallMethod] = Field(
        default_factory=list,
        description="Known installation methods",
    )

    # Quality
    quality: QualityAssessment = Field(
        default_factory=lambda: QualityAssessment(),
        description="Quality assessment",
    )
    security: SecurityAssessment = Field(
        default_factory=lambda: SecurityAssessment(),
        description="Security/risk assessment",
    )
    license: LicenseRecord = Field(
        default_factory=lambda: LicenseRecord(),
        description="License information",
    )

    # Raw content
    raw_content: str | None = Field(
        default=None,
        description="Raw file content, if captured",
    )

    # Migration
    migration: MigrationMetadata = Field(
        description="Migration/import metadata",
    )

    # Ecosystem metadata (preserved from v2)
    ecosystem_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Original ecosystem metadata from source",
    )

    model_config = {"extra": "forbid"}
