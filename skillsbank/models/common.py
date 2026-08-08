"""Shared types for field-level provenance and migration metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProvenancedValue(BaseModel):
    """A value with provenance tracking.

    Wraps any field to record how the value was determined,
    its confidence level, and when it was set.
    """

    value: str | None = None
    source: str = Field(
        default="unknown",
        description="How this value was determined: imported, inferred, reviewed, corrected, unknown",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score 0.0-1.0, null if unknown",
    )
    set_at: datetime | None = Field(
        default=None,
        description="When this value was last set or updated",
    )

    model_config = {"extra": "forbid"}


class MigrationMetadata(BaseModel):
    """Metadata about the migration/import of a record."""

    imported_from: str = Field(
        description="Source format: registry_v2, parser_v1, manual, etc.",
    )
    imported_at: datetime = Field(
        description="When this record was imported",
    )
    original_values: dict[str, Any] = Field(
        default_factory=dict,
        description="Original v2 values before normalization, keyed by field path",
    )
    normalization_notes: list[str] = Field(
        default_factory=list,
        description="Notes about what was normalized during import",
    )
    parser_version: str | None = Field(
        default=None,
        description="Version of the parser that produced this record",
    )
    extractor_version: str | None = Field(
        default=None,
        description="Version of the content extractor",
    )

    model_config = {"extra": "forbid"}
