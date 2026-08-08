"""Dependency and runtime requirement models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from skillsbank.models.enums import MetadataQuality


class Dependency(BaseModel):
    """A dependency required by a skill."""

    name: str = Field(description="Dependency name")
    version_constraint: str | None = Field(
        default=None,
        description="Version constraint, e.g. >=1.0, ^2.0",
    )
    required: bool = Field(
        default=True,
        description="Whether this dependency is required or optional",
    )
    source: str = Field(
        default="unknown",
        description="declared, inferred, unknown",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence if inferred",
    )

    model_config = {"extra": "forbid"}


class ToolRequirement(BaseModel):
    """A CLI tool or binary required by a skill."""

    name: str = Field(description="Tool name, e.g. ghidra, ffmpeg, docker")
    required: bool = Field(default=True)
    source: str = Field(default="unknown", description="declared, inferred, unknown")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    model_config = {"extra": "forbid"}


class APIRequirement(BaseModel):
    """An external API or service required by a skill."""

    name: str = Field(description="API/service name, e.g. OpenAI, Groq, GitHub")
    required: bool = Field(default=True)
    credentials_needed: bool = Field(default=False)
    source: str = Field(default="unknown", description="declared, inferred, unknown")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    model_config = {"extra": "forbid"}


class PackageRequirement(BaseModel):
    """A package/library required by a skill."""

    name: str = Field(description="Package name, e.g. pypdf, playwright")
    ecosystem: str | None = Field(
        default=None,
        description="Package ecosystem: pip, npm, cargo, etc.",
    )
    required: bool = Field(default=True)
    source: str = Field(default="unknown", description="declared, inferred, unknown")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    model_config = {"extra": "forbid"}


class EnvVarRequirement(BaseModel):
    """An environment variable required by a skill."""

    name: str = Field(description="Environment variable name, e.g. OPENAI_API_KEY")
    required: bool = Field(default=True)
    description: str | None = Field(default=None)
    source: str = Field(default="unknown", description="declared, inferred, unknown")

    model_config = {"extra": "forbid"}


class RuntimeRequirement(BaseModel):
    """Aggregate runtime requirements for a skill."""

    tools: list[ToolRequirement] = Field(default_factory=list)
    apis: list[APIRequirement] = Field(default_factory=list)
    packages: list[PackageRequirement] = Field(default_factory=list)
    env_vars: list[EnvVarRequirement] = Field(default_factory=list)
    runtimes: list[str] = Field(
        default_factory=list,
        description="Required runtimes: python3, node, docker, etc.",
    )
    shell_required: bool = Field(
        default=False,
        description="Whether shell execution is needed",
    )
    filesystem_write: bool = Field(
        default=False,
        description="Whether filesystem writes are needed",
    )
    network_required: bool = Field(
        default=False,
        description="Whether network access is needed",
    )
    quality: MetadataQuality = Field(
        default=MetadataQuality.UNKNOWN,
        description="Quality of dependency extraction",
    )

    model_config = {"extra": "forbid"}
