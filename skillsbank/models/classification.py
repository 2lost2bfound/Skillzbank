"""Domain, Capability, and Tag classification models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from skillsbank.models.common import ProvenancedValue
from skillsbank.models.enums import DomainSource, MetadataQuality


class Domain(BaseModel):
    """Domain classification for a skill."""

    primary: ProvenancedValue = Field(
        default_factory=lambda: ProvenancedValue(value=None, source="unknown"),
        description="Primary domain classification",
    )
    secondary: list[str] = Field(
        default_factory=list,
        description="Secondary domain classifications",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Overall domain classification confidence",
    )
    source: DomainSource = Field(
        default=DomainSource.UNKNOWN,
        description="How domain was determined",
    )
    quality: MetadataQuality = Field(
        default=MetadataQuality.UNKNOWN,
        description="Quality of domain extraction",
    )

    model_config = {"extra": "forbid"}


class Capability(BaseModel):
    """A capability that a skill provides."""

    name: str = Field(description="Original capability string from source")
    canonical: str | None = Field(
        default=None,
        description="Canonical/taxonomy-normalized capability name",
    )
    taxonomy_path: str | None = Field(
        default=None,
        description="Hierarchical taxonomy path, e.g. software_engineering.code_review",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence in canonical mapping",
    )

    model_config = {"extra": "forbid"}


class Tag(BaseModel):
    """A tag/label for categorization."""

    name: str = Field(description="Tag text")
    source: str = Field(
        default="imported",
        description="Where this tag came from: imported, inferred, manual",
    )

    model_config = {"extra": "forbid"}
