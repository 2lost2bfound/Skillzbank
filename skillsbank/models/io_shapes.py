"""Input/Output shape models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from skillsbank.models.enums import MetadataQuality


class InputShape(BaseModel):
    """Describes the expected input format for a skill."""

    format: str = Field(
        default="unknown",
        description="Input format: natural_language, cli_command, file_path, json, unknown",
    )
    required: list[str] = Field(
        default_factory=list,
        description="Required input fields/parameters",
    )
    optional: list[str] = Field(
        default_factory=list,
        description="Optional input fields/parameters",
    )
    json_schema: dict[str, Any] | None = Field(
        default=None,
        description="JSON Schema for structured inputs",
    )
    quality: MetadataQuality = Field(
        default=MetadataQuality.UNKNOWN,
        description="Quality of input shape extraction",
    )

    model_config = {"extra": "forbid"}


class OutputShape(BaseModel):
    """Describes the output format produced by a skill."""

    format: str = Field(
        default="unknown",
        description="Output format: markdown, html, json, file, unknown",
    )
    json_schema: dict[str, Any] | None = Field(
        default=None,
        description="JSON Schema for structured outputs",
    )
    quality: MetadataQuality = Field(
        default=MetadataQuality.UNKNOWN,
        description="Quality of output shape extraction",
    )

    model_config = {"extra": "forbid"}
