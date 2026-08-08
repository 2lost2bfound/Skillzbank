"""Tests for the compatibility engine."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from skillsbank.compat import (
    AGENT_PROFILES,
    AgentProfile,
    FullCompatibilityProfile,
    _assess_agent,
    _detect_invocation_type,
    _detect_os,
    _detect_runtimes,
    _detect_skill_md_format,
    assess_compatibility,
    get_compatibility_summary,
    sync_compatibility_to_db,
)
from skillsbank.db.engine import get_session
from skillsbank.db.persistence_models import Base, SkillRow, VersionRow
from skillsbank.models.enums import CompatibilityLevel


@pytest.fixture
def db_session():
    """Create a fresh in-memory DB for each test."""
    engine = sa.create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    with get_session(engine) as session:
        yield session


def _make_version(
    session,
    skill_id="sk-1",
    summary="",
    long_description=None,
    raw_content=None,
    source_path="skills/foo/SKILL.md",
    install_methods=None,
    declared_deps=None,
    inferred_deps=None,
    input_format="unknown",
    output_format="unknown",
) -> VersionRow:
    """Helper: create a minimal skill + version in DB."""
    skill = SkillRow(id=skill_id, name="test-skill", display_name="Test Skill")
    session.add(skill)
    session.flush()

    version = VersionRow(
        skill_id=skill_id,
        version_id="v1",
        name="test-skill",
        summary=summary,
        long_description=long_description,
        raw_content=raw_content,
        source_path=source_path,
        input_format=input_format,
        output_format=output_format,
        install_methods=install_methods or [],
        declared_dependencies=declared_deps or [],
        inferred_dependencies=inferred_deps or [],
    )
    session.add(version)
    session.flush()
    return version


# ── Signal detection tests ───────────────────────────────────────────────────


class TestDetectSkillMd:
    def test_skill_md_path(self):
        assert _detect_skill_md_format({"source_path": "skills/foo/SKILL.md"}) is True

    def test_agents_md_path(self):
        assert _detect_skill_md_format({"source_path": "AGENTS.md"}) is False

    def test_readme_path(self):
        assert _detect_skill_md_format({"source_path": "README.md"}) is False


class TestDetectInvocationType:
    def test_skill_md_is_prompt_only(self):
        signals = {"source_path": "skills/foo/SKILL.md", "combined_text": "some text"}
        assert _detect_invocation_type(signals) == "prompt_only"

    def test_mcp_content(self):
        signals = {"source_path": "foo.py", "combined_text": "This is an MCP server tool"}
        assert _detect_invocation_type(signals) == "mcp_tool"

    def test_npm_install(self):
        signals = {
            "source_path": "index.js",
            "combined_text": "A Node.js tool",
            "install_methods": [{"method": "npm", "command": "npm install foo"}],
        }
        assert _detect_invocation_type(signals) == "tool_call"

    def test_shell_fallback(self):
        signals = {"source_path": "script.sh", "combined_text": "Run bash commands in terminal"}
        assert _detect_invocation_type(signals) == "cli_command"

    def test_default_prompt_only(self):
        signals = {"source_path": "doc.md", "combined_text": "Some documentation text"}
        assert _detect_invocation_type(signals) == "prompt_only"


class TestDetectRuntimes:
    def test_python(self):
        assert "python" in _detect_runtimes({"combined_text": "pip install numpy"})

    def test_node(self):
        assert "node" in _detect_runtimes({"combined_text": "npm install express"})

    def test_rust(self):
        assert "rust" in _detect_runtimes({"combined_text": "cargo build --release"})

    def test_go(self):
        assert "go" in _detect_runtimes({"combined_text": "go mod tidy"})

    def test_java(self):
        assert "java" in _detect_runtimes({"combined_text": "gradle build"})

    def test_none_detected(self):
        assert _detect_runtimes({"combined_text": "just text"}) == []


class TestDetectOs:
    def test_linux(self):
        assert "linux" in _detect_os({"combined_text": "Works on Ubuntu 22.04"})

    def test_macos(self):
        assert "macos" in _detect_os({"combined_text": "Install via brew on macOS"})

    def test_windows(self):
        assert "windows" in _detect_os({"combined_text": "Run powershell script"})

    def test_none(self):
        assert _detect_os({"combined_text": "generic text"}) == []


# ── Agent assessment tests ───────────────────────────────────────────────────


class TestAssessAgent:
    def test_skill_md_with_claude(self):
        """SKILL.md with Claude → SUPPORTED."""
        signals = {
            "combined_text": "This is a helpful skill",
            "source_path": "skills/foo/SKILL.md",
            "install_methods": [],
        }
        result = _assess_agent(signals, AGENT_PROFILES["claude"], skill_md=True, mcp_compat=False)
        assert result.level == CompatibilityLevel.SUPPORTED
        assert result.confidence > 0.7
        assert any("SKILL.md" in e for e in result.enablers)

    def test_mcp_with_mcp_client(self):
        """MCP skill with MCP client → SUPPORTED."""
        signals = {
            "combined_text": "An MCP server for database access",
            "source_path": "server.py",
            "install_methods": [],
        }
        result = _assess_agent(signals, AGENT_PROFILES["mcp_client"], skill_md=False, mcp_compat=True)
        assert result.level == CompatibilityLevel.SUPPORTED
        assert any("MCP" in e for e in result.enablers)

    def test_browser_with_codex(self):
        """Browser-dependent skill with Codex (no browser) → blocked."""
        signals = {
            "combined_text": "Uses playwright to scrape websites",
            "source_path": "scraper.py",
            "install_methods": [],
        }
        result = _assess_agent(signals, AGENT_PROFILES["codex"], skill_md=False, mcp_compat=False)
        assert result.level in (CompatibilityLevel.REQUIRES_ADAPTER, CompatibilityLevel.NOT_SUPPORTED)
        assert any("browser" in b.lower() for b in result.blockers)

    def test_shell_with_gemini(self):
        """Shell-dependent skill with Gemini → supported (has shell)."""
        signals = {
            "combined_text": "Run bash commands to automate tasks",
            "source_path": "tool.py",
            "install_methods": [],
        }
        result = _assess_agent(signals, AGENT_PROFILES["gemini"], skill_md=False, mcp_compat=False)
        assert result.confidence >= 0.4

    def test_docker_with_generic_cli(self):
        """Docker-dependent skill with generic CLI (no shell) → blocked."""
        no_shell = AgentProfile(name="no_shell", supports_shell=False)
        signals = {
            "combined_text": "Run docker compose up",
            "source_path": "docker.py",
            "install_methods": [],
        }
        result = _assess_agent(signals, no_shell, skill_md=False, mcp_compat=False)
        assert any("docker" in b.lower() for b in result.blockers)


# ── Full assessment tests ───────────────────────────────────────────────────


class TestAssessCompatibility:
    def test_skill_md_assessment(self, db_session):
        """SKILL.md skill gets assessed for all agents."""
        version = _make_version(
            db_session,
            summary="A helpful skill for code review",
            source_path="skills/code-review/SKILL.md",
        )
        profile = assess_compatibility(version)

        assert isinstance(profile, FullCompatibilityProfile)
        assert profile.skill_md_format is True
        assert profile.invocation_type == "prompt_only"
        assert len(profile.agent_results) == len(AGENT_PROFILES)

        # Claude should be SUPPORTED
        claude_result = next(r for r in profile.agent_results if r.agent == "claude")
        assert claude_result.level == CompatibilityLevel.SUPPORTED

    def test_mcp_skill_assessment(self, db_session):
        """MCP-based skill detected correctly."""
        version = _make_version(
            db_session,
            summary="An MCP server providing database tools for PostgreSQL",
            source_path="mcp-db/server.py",
        )
        profile = assess_compatibility(version)

        assert profile.mcp_compatible is True
        mcp_client_result = next(r for r in profile.agent_results if r.agent == "mcp_client")
        assert mcp_client_result.level == CompatibilityLevel.SUPPORTED

    def test_python_runtime_detected(self, db_session):
        """Python runtime detected from content."""
        version = _make_version(
            db_session,
            summary="Requires python3 and pip install requests",
            source_path="tool/main.py",
        )
        profile = assess_compatibility(version)
        assert "python" in profile.detected_runtimes

    def test_node_runtime_detected(self, db_session):
        """Node runtime detected from install methods."""
        version = _make_version(
            db_session,
            summary="A Node.js CLI tool",
            source_path="cli/index.js",
            install_methods=[{"method": "npm", "command": "npm install -g my-tool"}],
        )
        profile = assess_compatibility(version)
        assert "node" in profile.detected_runtimes

    def test_agent_mention_boost(self, db_session):
        """Explicit agent mention boosts that agent's compatibility."""
        version = _make_version(
            db_session,
            summary="A skill designed for Claude Code by Anthropic",
            source_path="skills/claude-skill/SKILL.md",
        )
        profile = assess_compatibility(version)
        claude_result = next(r for r in profile.agent_results if r.agent == "claude")
        assert claude_result.confidence > 0.8


# ── Batch sync tests ────────────────────────────────────────────────────────


class TestSyncCompatibility:
    def test_sync_all_versions(self, db_session):
        """Sync computes compatibility for all versions."""
        _make_version(db_session, skill_id="s1", summary="A SKILL.md skill")
        _make_version(
            db_session,
            skill_id="s2",
            summary="An MCP server",
            source_path="mcp/server.py",
        )

        stats = sync_compatibility_to_db(db_session)
        assert stats.versions_assessed == 2
        assert stats.skill_md_count == 1
        assert stats.mcp_compatible_count == 1

    def test_sync_idempotent(self, db_session):
        """Re-running sync skips already-assessed versions."""
        _make_version(db_session, skill_id="s1", summary="A skill")

        stats1 = sync_compatibility_to_db(db_session)
        assert stats1.versions_assessed == 1

        stats2 = sync_compatibility_to_db(db_session)
        assert stats2.versions_assessed == 0  # already done

    def test_get_summary(self, db_session):
        """Summary returns correct structure."""
        _make_version(db_session, skill_id="s1", summary="A SKILL.md skill")
        sync_compatibility_to_db(db_session)

        summary = get_compatibility_summary(db_session)
        assert summary["total_versions_with_compat"] == 1
        assert "claude" in summary["agent_compatibility"]
        assert summary["skill_md_format_count"] == 1


# ── Agent profile tests ─────────────────────────────────────────────────────


class TestAgentProfiles:
    def test_all_agents_present(self):
        expected = {"claude", "codex", "opencode", "gemini", "cursor", "mcp_client", "generic_cli"}
        assert set(AGENT_PROFILES.keys()) == expected

    def test_claude_has_all_capabilities(self):
        claude = AGENT_PROFILES["claude"]
        assert claude.supports_skill_md is True
        assert claude.supports_mcp is True
        assert claude.supports_shell is True
        assert claude.supports_browser is True

    def test_codex_no_mcp(self):
        assert AGENT_PROFILES["codex"].supports_mcp is False

    def test_mcp_client_shell_only(self):
        mcp = AGENT_PROFILES["mcp_client"]
        assert mcp.supports_mcp is True
        assert mcp.supports_shell is False
        assert mcp.supports_browser is False
