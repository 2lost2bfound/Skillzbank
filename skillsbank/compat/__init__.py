"""Compatibility engine: assess skill compatibility with agents and environments."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from skillsbank.db.persistence_models import RepoRow, VersionRow
from skillsbank.models.enums import CompatibilityLevel

# ── Agent/environment profiles ──────────────────────────────────────────────


@dataclass
class AgentProfile:
    """What a specific agent can do."""

    name: str
    supports_skill_md: bool = False
    supports_agents_md: bool = False
    supports_mcp: bool = False
    supports_shell: bool = False
    supports_browser: bool = False
    supports_python: bool = False
    supports_node: bool = False
    supports_generic_cli: bool = False
    max_context_tokens: int = 200_000


AGENT_PROFILES: dict[str, AgentProfile] = {
    "claude": AgentProfile(
        name="claude",
        supports_skill_md=True,
        supports_agents_md=True,
        supports_mcp=True,
        supports_shell=True,
        supports_browser=True,
        supports_python=True,
        supports_node=True,
        supports_generic_cli=True,
    ),
    "codex": AgentProfile(
        name="codex",
        supports_skill_md=True,
        supports_agents_md=True,
        supports_mcp=False,
        supports_shell=True,
        supports_browser=False,
        supports_python=True,
        supports_node=True,
        supports_generic_cli=True,
    ),
    "opencode": AgentProfile(
        name="opencode",
        supports_skill_md=True,
        supports_agents_md=True,
        supports_mcp=True,
        supports_shell=True,
        supports_browser=True,
        supports_python=True,
        supports_node=True,
        supports_generic_cli=True,
    ),
    "gemini": AgentProfile(
        name="gemini",
        supports_skill_md=False,
        supports_agents_md=False,
        supports_mcp=True,
        supports_shell=True,
        supports_browser=False,
        supports_python=True,
        supports_node=True,
        supports_generic_cli=True,
    ),
    "cursor": AgentProfile(
        name="cursor",
        supports_skill_md=True,
        supports_agents_md=True,
        supports_mcp=True,
        supports_shell=True,
        supports_browser=False,
        supports_python=True,
        supports_node=True,
        supports_generic_cli=True,
    ),
    "mcp_client": AgentProfile(
        name="mcp_client",
        supports_skill_md=False,
        supports_agents_md=False,
        supports_mcp=True,
        supports_shell=False,
        supports_browser=False,
        supports_python=False,
        supports_node=False,
        supports_generic_cli=False,
    ),
    "generic_cli": AgentProfile(
        name="generic_cli",
        supports_skill_md=False,
        supports_agents_md=False,
        supports_mcp=False,
        supports_shell=True,
        supports_browser=False,
        supports_python=True,
        supports_node=True,
        supports_generic_cli=True,
    ),
}


# ── Pattern detectors ────────────────────────────────────────────────────────

# Agent-specific mentions in content
AGENT_MENTION_PATTERNS: dict[str, re.Pattern] = {
    "claude": re.compile(r"\b(claude|anthropic|claude[-_]?code|claude[-_]?desktop)\b", re.IGNORECASE),
    "codex": re.compile(r"\b(codex|openai[-_]?codex|codex[-_]?cli)\b", re.IGNORECASE),
    "opencode": re.compile(r"\b(opencode)\b", re.IGNORECASE),
    "gemini": re.compile(r"\b(gemini|google[-_]?ai|bard)\b", re.IGNORECASE),
    "cursor": re.compile(r"\b(cursor|cursor[-_]?ai)\b", re.IGNORECASE),
    "mcp_client": re.compile(r"\b(mcp|model[-_]?context[-_]?protocol)\b", re.IGNORECASE),
}

# Runtime requirement patterns
RUNTIME_PATTERNS: dict[str, re.Pattern] = {
    "python": re.compile(r"\b(python3?|pip|pip3|venv|conda|poetry)\b", re.IGNORECASE),
    "node": re.compile(r"\b(node|npm|npx|yarn|pnpm|bun)\b", re.IGNORECASE),
    "rust": re.compile(r"\b(rust|cargo|rustc)\b", re.IGNORECASE),
    "go": re.compile(r"\b(go\b|golang)\b", re.IGNORECASE),
    "java": re.compile(r"\b(java|jvm|gradle|maven|mvn)\b", re.IGNORECASE),
    "deno": re.compile(r"\b(deno)\b", re.IGNORECASE),
}

# OS/platform patterns
OS_PATTERNS: dict[str, re.Pattern] = {
    "linux": re.compile(r"\b(linux|ubuntu|debian|centos|fedora|arch)\b", re.IGNORECASE),
    "macos": re.compile(r"\b(macos|darwin|mac\b|osx|brew|homebrew)\b", re.IGNORECASE),
    "windows": re.compile(r"\b(windows|powershell|cmd\.exe|wsl)\b", re.IGNORECASE),
}

# Capability signals
SHELL_PATTERN = re.compile(r"\b(bash|shell|zsh|command[-_]?line|terminal|sh\b)\b", re.IGNORECASE)
BROWSER_PATTERN = re.compile(r"\b(playwright|puppeteer|selenium|browser|chrome|firefox|chromium|cdp)\b", re.IGNORECASE)
MCP_PATTERN = re.compile(r"\b(mcp|model[-_]?context[-_]?protocol|mcp[-_]?server|mcp[-_]?tool)\b", re.IGNORECASE)
DOCKER_PATTERN = re.compile(r"\b(docker|container|dockerfile|docker[-_]?compose)\b", re.IGNORECASE)
API_PATTERN = re.compile(r"\b(api[-_]?key|api[-_]?token|bearer|oauth|authentication)\b", re.IGNORECASE)


@dataclass
class CompatibilityResult:
    """Compatibility assessment for a single version against a single agent."""

    agent: str
    level: CompatibilityLevel
    confidence: float
    notes: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    enablers: list[str] = field(default_factory=list)


@dataclass
class FullCompatibilityProfile:
    """Full compatibility profile across all agents for a version."""

    version_id: str
    skill_id: str
    agent_results: list[CompatibilityResult] = field(default_factory=list)
    detected_runtimes: list[str] = field(default_factory=list)
    detected_os: list[str] = field(default_factory=list)
    invocation_type: str = "unknown"
    skill_md_format: bool = False
    mcp_compatible: bool = False


def _collect_signals(version: VersionRow) -> dict:
    """Collect all text signals from a version for compatibility analysis."""
    texts = []
    if version.summary:
        texts.append(version.summary)
    if version.long_description:
        texts.append(version.long_description)
    if version.raw_content:
        texts.append(version.raw_content)

    # Include install method commands
    if version.install_methods:
        for im in version.install_methods:
            if isinstance(im, dict) and im.get("command"):
                texts.append(im["command"])

    # Include dependency info
    if version.declared_dependencies:
        for dep in version.declared_dependencies:
            if isinstance(dep, dict):
                texts.append(dep.get("name", ""))

    if version.inferred_dependencies:
        for dep in version.inferred_dependencies:
            if isinstance(dep, dict):
                texts.append(dep.get("name", ""))

    combined = " ".join(texts)

    return {
        "combined_text": combined,
        "source_path": version.source_path or "",
        "has_summary": bool(version.summary),
        "has_long_description": bool(version.long_description),
        "has_raw_content": bool(version.raw_content),
        "input_format": version.input_format or "unknown",
        "output_format": version.output_format or "unknown",
        "install_methods": version.install_methods or [],
        "declared_deps": version.declared_dependencies or [],
        "inferred_deps": version.inferred_dependencies or [],
        "runtime_requirements": version.runtime_requirements or {},
    }


def _detect_skill_md_format(signals: dict) -> bool:
    """Check if the skill uses SKILL.md format."""
    path = signals["source_path"].lower()
    return "skill.md" in path


def _detect_invocation_type(signals: dict) -> str:
    """Determine how the skill is invoked."""
    text = signals["combined_text"]
    path = signals["source_path"].lower()

    if "skill.md" in path:
        return "prompt_only"
    if MCP_PATTERN.search(text):
        return "mcp_tool"
    if any(
        isinstance(im, dict) and im.get("method") in ("npm", "pip", "npx") for im in signals.get("install_methods", [])
    ):
        return "tool_call"
    if SHELL_PATTERN.search(text):
        return "cli_command"
    return "prompt_only"


def _detect_runtimes(signals: dict) -> list[str]:
    """Detect required runtimes from signals."""
    text = signals["combined_text"]
    runtimes = []
    for name, pattern in RUNTIME_PATTERNS.items():
        if pattern.search(text):
            runtimes.append(name)
    return runtimes


def _detect_os(signals: dict) -> list[str]:
    """Detect mentioned operating systems."""
    text = signals["combined_text"]
    os_list = []
    for name, pattern in OS_PATTERNS.items():
        if pattern.search(text):
            os_list.append(name)
    return os_list


def _assess_agent(
    signals: dict,
    agent: AgentProfile,
    skill_md: bool,
    mcp_compat: bool,
) -> CompatibilityResult:
    """Assess compatibility of a skill with a specific agent."""
    text = signals["combined_text"]
    notes = []
    blockers = []
    enablers = []
    score = 0.5  # baseline

    # SKILL.md format is the strongest signal of agent compatibility
    if skill_md:
        if agent.supports_skill_md:
            enablers.append("uses SKILL.md format (agent-native)")
            score += 0.35
        else:
            notes.append("uses SKILL.md format (agent may not support it natively)")
            score -= 0.1

    # AGENTS.md format
    if "agents.md" in signals["source_path"].lower():
        if agent.supports_agents_md:
            enablers.append("uses AGENTS.md format")
            score += 0.15
        else:
            notes.append("uses AGENTS.md format")

    # MCP compatibility
    if mcp_compat:
        if agent.supports_mcp:
            enablers.append("MCP compatible (agent-native)")
            score += 0.30
        else:
            blockers.append("requires MCP support")
            score -= 0.3

    # Runtime requirements
    runtimes = _detect_runtimes(signals)
    for rt in runtimes:
        if rt == "python" and agent.supports_python or rt == "node" and agent.supports_node:
            enablers.append(f"requires {rt} (supported)")
        elif rt in ("rust", "go", "java", "deno"):
            if agent.supports_shell:
                notes.append(f"requires {rt} (needs shell to install)")
            else:
                blockers.append(f"requires {rt} (no shell access)")
                score -= 0.2

    # Browser requirements
    if BROWSER_PATTERN.search(text):
        if agent.supports_browser:
            enablers.append("uses browser automation (supported)")
        else:
            blockers.append("requires browser automation")
            score -= 0.2

    # Shell requirements (explicit)
    if SHELL_PATTERN.search(text) and not skill_md:
        if agent.supports_shell:
            enablers.append("uses shell commands (supported)")
        else:
            blockers.append("requires shell access")
            score -= 0.3

    # Agent-specific mentions
    for agent_name, pattern in AGENT_MENTION_PATTERNS.items():
        if pattern.search(text):
            if agent_name == agent.name:
                enablers.append(f"explicitly mentions {agent.name}")
                score += 0.15
            elif agent_name != agent.name:
                notes.append(f"mentions {agent_name} (may need adaptation)")

    # Docker
    if DOCKER_PATTERN.search(text):
        if agent.supports_shell:
            notes.append("uses Docker (needs Docker installed)")
        else:
            blockers.append("requires Docker")
            score -= 0.2

    # API key requirements
    if API_PATTERN.search(text):
        notes.append("requires API keys/tokens")

    # Clamp score
    score = max(0.0, min(1.0, score))

    # Map score to level
    if score >= 0.80:
        level = CompatibilityLevel.SUPPORTED
    elif score >= 0.60:
        level = CompatibilityLevel.LIKELY_SUPPORTED
    elif score >= 0.35:
        level = CompatibilityLevel.REQUIRES_ADAPTER
    elif blockers:
        level = CompatibilityLevel.NOT_SUPPORTED
    else:
        level = CompatibilityLevel.UNKNOWN

    return CompatibilityResult(
        agent=agent.name,
        level=level,
        confidence=round(score, 3),
        notes=notes,
        blockers=blockers,
        enablers=enablers,
    )


def assess_compatibility(
    version: VersionRow,
    agents: dict[str, AgentProfile] | None = None,
) -> FullCompatibilityProfile:
    """Assess compatibility of a single version across all known agents."""
    if agents is None:
        agents = AGENT_PROFILES

    signals = _collect_signals(version)
    skill_md = _detect_skill_md_format(signals)
    mcp_compat = bool(MCP_PATTERN.search(signals["combined_text"]))
    invocation = _detect_invocation_type(signals)
    runtimes = _detect_runtimes(signals)
    os_list = _detect_os(signals)

    results = []
    for agent_name, agent in sorted(agents.items()):
        result = _assess_agent(signals, agent, skill_md, mcp_compat)
        results.append(result)

    return FullCompatibilityProfile(
        version_id=version.version_id or "",
        skill_id=version.skill_id,
        agent_results=results,
        detected_runtimes=runtimes,
        detected_os=os_list,
        invocation_type=invocation,
        skill_md_format=skill_md,
        mcp_compatible=mcp_compat,
    )


# ── Batch processing ────────────────────────────────────────────────────────


@dataclass
class CompatStats:
    """Statistics from a batch compatibility run."""

    versions_assessed: int = 0
    agent_distribution: dict[str, dict[str, int]] = field(default_factory=dict)
    invocation_distribution: dict[str, int] = field(default_factory=dict)
    runtime_distribution: dict[str, int] = field(default_factory=dict)
    mcp_compatible_count: int = 0
    skill_md_count: int = 0


def sync_compatibility_to_db(
    session: Session,
    agents: dict[str, AgentProfile] | None = None,
) -> CompatStats:
    """Compute compatibility for all versions and store in DB.

    Stores results as JSON in VersionRow.compatibility.
    Only processes versions that don't already have compatibility data.
    """
    if agents is None:
        agents = AGENT_PROFILES

    # Select versions without real compatibility data (NULL or JSON "null")
    stmt = select(VersionRow).where(
        sa.or_(
            VersionRow.compatibility.is_(None),
            VersionRow.compatibility == "null",
        )
    )
    versions = session.scalars(stmt).all()

    stats = CompatStats()

    for version in versions:
        profile = assess_compatibility(version, agents)
        stats.versions_assessed += 1

        # Build compatibility dict for storage
        compat_data = {
            "invocation_type": profile.invocation_type,
            "skill_md_format": profile.skill_md_format,
            "mcp_compatible": profile.mcp_compatible,
            "detected_runtimes": profile.detected_runtimes,
            "detected_os": profile.detected_os,
            "agents": {},
        }

        for result in profile.agent_results:
            compat_data["agents"][result.agent] = {
                "level": result.level.value,
                "confidence": result.confidence,
                "notes": result.notes,
                "blockers": result.blockers,
                "enablers": result.enablers,
            }

            # Track distribution
            if result.agent not in stats.agent_distribution:
                stats.agent_distribution[result.agent] = {}
            level_name = result.level.value
            stats.agent_distribution[result.agent][level_name] = (
                stats.agent_distribution[result.agent].get(level_name, 0) + 1
            )

        version.compatibility = compat_data

        # Track stats
        inv = profile.invocation_type
        stats.invocation_distribution[inv] = stats.invocation_distribution.get(inv, 0) + 1
        for rt in profile.detected_runtimes:
            stats.runtime_distribution[rt] = stats.runtime_distribution.get(rt, 0) + 1
        if profile.mcp_compatible:
            stats.mcp_compatible_count += 1
        if profile.skill_md_format:
            stats.skill_md_count += 1

    session.commit()
    return stats


def get_compatibility_summary(session: Session) -> dict:
    """Get summary of compatibility data in the DB."""
    stmt = select(VersionRow).where(
        sa.and_(
            VersionRow.compatibility.is_not(None),
            VersionRow.compatibility != "null",
        )
    )
    versions = session.scalars(stmt).all()

    agent_levels: dict[str, dict[str, int]] = {}
    invocation_types: dict[str, int] = {}
    runtimes: dict[str, int] = {}
    mcp_count = 0
    skill_md_count = 0

    for v in versions:
        compat = v.compatibility or {}
        inv = compat.get("invocation_type", "unknown")
        invocation_types[inv] = invocation_types.get(inv, 0) + 1

        if compat.get("mcp_compatible"):
            mcp_count += 1
        if compat.get("skill_md_format"):
            skill_md_count += 1

        for rt in compat.get("detected_runtimes", []):
            runtimes[rt] = runtimes.get(rt, 0) + 1

        for agent_name, agent_data in compat.get("agents", {}).items():
            if agent_name not in agent_levels:
                agent_levels[agent_name] = {}
            level = agent_data.get("level", "UNKNOWN")
            agent_levels[agent_name][level] = agent_levels[agent_name].get(level, 0) + 1

    return {
        "total_versions_with_compat": len(versions),
        "agent_compatibility": agent_levels,
        "invocation_types": invocation_types,
        "runtimes": runtimes,
        "mcp_compatible_count": mcp_count,
        "skill_md_format_count": skill_md_count,
    }
