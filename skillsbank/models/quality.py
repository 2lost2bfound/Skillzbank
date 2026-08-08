"""Quality assessment, security assessment, and license record models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from skillsbank.models.enums import (
    LicenseStatus,
    MetadataQuality,
    RiskLevel,
)


class QualityDimension(BaseModel):
    """A single quality dimension score."""

    name: str = Field(description="Dimension name")
    score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Score 0.0-1.0, null if not assessed",
    )
    notes: str | None = Field(default=None)

    model_config = {"extra": "forbid"}


class QualityAssessment(BaseModel):
    """Quality assessment of a skill record."""

    overall_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Overall quality score, derived from dimensions",
    )
    dimensions: list[QualityDimension] = Field(
        default_factory=list,
        description="Individual quality dimension scores",
    )
    metadata_completeness: MetadataQuality = Field(
        default=MetadataQuality.UNKNOWN,
    )
    documentation_quality: MetadataQuality = Field(
        default=MetadataQuality.UNKNOWN,
    )
    specificity: MetadataQuality = Field(
        default=MetadataQuality.UNKNOWN,
    )
    portability: MetadataQuality = Field(
        default=MetadataQuality.UNKNOWN,
    )
    dependency_clarity: MetadataQuality = Field(
        default=MetadataQuality.UNKNOWN,
    )
    maintainability: MetadataQuality = Field(
        default=MetadataQuality.UNKNOWN,
    )
    testability: MetadataQuality = Field(
        default=MetadataQuality.UNKNOWN,
    )
    extraction_confidence: MetadataQuality = Field(
        default=MetadataQuality.UNKNOWN,
    )

    model_config = {"extra": "forbid"}


class SecurityAssessment(BaseModel):
    """Security/risk metadata for a skill."""

    risk_level: RiskLevel = Field(
        default=RiskLevel.UNKNOWN,
        description="Overall risk classification",
    )
    risk_factors: list[str] = Field(
        default_factory=list,
        description="Specific risk factors identified",
    )
    shell_execution: bool = Field(
        default=False,
        description="Whether the skill executes shell commands",
    )
    filesystem_access: bool = Field(
        default=False,
        description="Whether the skill reads/writes filesystem",
    )
    network_access: bool = Field(
        default=False,
        description="Whether the skill makes network requests",
    )
    browser_automation: bool = Field(
        default=False,
        description="Whether the skill automates browser actions",
    )
    credential_requirements: list[str] = Field(
        default_factory=list,
        description="Credentials/API keys needed",
    )
    package_installation: bool = Field(
        default=False,
        description="Whether the skill installs packages",
    )
    destructive_potential: bool = Field(
        default=False,
        description="Whether the skill can perform destructive operations",
    )
    security_tooling: bool = Field(
        default=False,
        description="Whether the skill is security/pentesting tooling",
    )
    review_status: str = Field(
        default="not_reviewed",
        description="not_reviewed, reviewed, approved, flagged",
    )

    model_config = {"extra": "forbid"}


class LicenseRecord(BaseModel):
    """License information for a skill or repository."""

    license_type: str | None = Field(
        default=None,
        description="License identifier: MIT, Apache-2.0, proprietary, etc.",
    )
    detected_source: str | None = Field(
        default=None,
        description="Where license was detected: repo_license, file_header, declared, unknown",
    )
    status: LicenseStatus = Field(
        default=LicenseStatus.UNKNOWN,
    )
    redistributable: bool | None = Field(
        default=None,
        description="Whether redistribution is allowed",
    )
    modifiable: bool | None = Field(
        default=None,
        description="Whether modification is allowed",
    )
    commercial_restrictions: bool | None = Field(
        default=None,
        description="Whether there are commercial use restrictions",
    )
    attribution_required: bool | None = Field(
        default=None,
        description="Whether attribution is required",
    )
    verified: bool = Field(
        default=False,
        description="Whether license has been verified by a human",
    )
    notes: str | None = Field(default=None)

    model_config = {"extra": "forbid"}
