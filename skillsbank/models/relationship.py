"""Relationship and similarity record models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from skillsbank.models.enums import RelationshipType


class Relationship(BaseModel):
    """A directional relationship between two skills."""

    source_id: str = Field(description="ID of the source skill")
    target_id: str = Field(description="ID of the target skill")
    relationship_type: RelationshipType = Field(
        description="Type of relationship",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence in this relationship",
    )
    notes: str | None = Field(default=None)
    source: str = Field(
        default="unknown",
        description="detected, declared, manual, unknown",
    )

    model_config = {"extra": "forbid"}


class SimilarityDimension(BaseModel):
    """A single dimension of similarity scoring."""

    name: str = Field(description="Dimension name: content_hash, name, capabilities, summary, etc.")
    score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Similarity score on this dimension",
    )

    model_config = {"extra": "forbid"}


class SimilarityRecord(BaseModel):
    """A similarity assessment between two skills."""

    skill_a_id: str = Field(description="First skill ID")
    skill_b_id: str = Field(description="Second skill ID")
    overall_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Overall similarity score",
    )
    dimensions: list[SimilarityDimension] = Field(
        default_factory=list,
        description="Per-dimension similarity scores",
    )
    classification: str | None = Field(
        default=None,
        description="Similarity classification: EXACT_DUPLICATE, NEAR_DUPLICATE, FUNCTIONAL_OVERLAP, etc.",
    )
    computed_at: str | None = Field(
        default=None,
        description="When this similarity was computed (ISO datetime)",
    )

    model_config = {"extra": "forbid"}
