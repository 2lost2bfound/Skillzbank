"""Compatibility profile and install method models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from skillsbank.models.enums import CompatibilityLevel, MetadataQuality


class CompatibilityEntry(BaseModel):
    """Compatibility status for a specific agent or ecosystem."""

    target: str = Field(
        description="Agent/ecosystem name: claude, codex, opencode, gemini, mcp, generic_llm, cli_agent, etc.",
    )
    level: CompatibilityLevel = Field(
        default=CompatibilityLevel.UNKNOWN,
        description="Compatibility level",
    )
    notes: str | None = Field(
        default=None,
        description="Specific compatibility notes or limitations",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence in this compatibility assessment",
    )
    source: str = Field(
        default="unknown",
        description="declared, inferred, tested, unknown",
    )

    model_config = {"extra": "forbid"}


class CompatibilityProfile(BaseModel):
    """Full compatibility profile across ecosystems."""

    entries: list[CompatibilityEntry] = Field(
        default_factory=list,
        description="Per-target compatibility entries",
    )
    invocation_type: str | None = Field(
        default=None,
        description="How the skill is invoked: prompt_only, tool_call, mcp_tool, cli_command, api_call, unknown",
    )
    skill_md_format: bool = Field(
        default=False,
        description="Whether the skill uses SKILL.md format",
    )
    mcp_compatible: bool = Field(
        default=False,
        description="Whether the skill works as or with MCP",
    )
    quality: MetadataQuality = Field(
        default=MetadataQuality.UNKNOWN,
        description="Quality of compatibility data",
    )

    model_config = {"extra": "forbid"}


class InstallMethod(BaseModel):
    """How a skill can be installed."""

    method: str = Field(
        description="Installation method: npm, pip, npx, curl, git_clone, manual, unknown",
    )
    command: str | None = Field(
        default=None,
        description="Exact install command",
    )
    target_path: str | None = Field(
        default=None,
        description="Where the skill gets installed",
    )
    notes: str | None = Field(default=None)

    model_config = {"extra": "forbid"}
