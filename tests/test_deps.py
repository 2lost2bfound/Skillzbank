"""Tests for Phase 6: Dependency Intelligence."""

from __future__ import annotations

import pytest

from skillsbank.deps.extractor import (
    DepType,
    ExtractedDependency,
    _extract_api_keys,
    _extract_env_vars,
    _extract_packages,
    _extract_runtimes,
    _extract_tools,
    extract_dependencies_from_text,
    extract_from_version,
)
from skillsbank.deps.graph import DependencyGraph


class TestPackageExtraction:
    """Test install command parsing."""

    def test_pip_install_single(self):
        text = "Install with pip install requests"
        deps = _extract_packages(text)
        assert any(d.name == "requests" and d.ecosystem == "pip" for d in deps)

    def test_pip_install_multiple(self):
        text = "pip install flask sqlalchemy psycopg2-binary"
        deps = _extract_packages(text)
        names = {d.name for d in deps}
        assert "flask" in names
        assert "sqlalchemy" in names
        assert "psycopg2-binary" in names

    def test_pip3_install(self):
        text = "pip3 install numpy pandas"
        deps = _extract_packages(text)
        names = {d.name for d in deps}
        assert "numpy" in names
        assert "pandas" in names

    def test_npm_install(self):
        text = "npm install express react"
        deps = _extract_packages(text)
        names = {d.name for d in deps}
        assert "express" in names
        assert "react" in names

    def test_npm_add(self):
        text = "yarn add typescript @types/node"
        deps = _extract_packages(text)
        names = {d.name for d in deps}
        assert "typescript" in names

    def test_apt_install(self):
        text = "apt install ffmpeg imagemagick"
        deps = _extract_packages(text)
        names = {d.name for d in deps}
        assert "ffmpeg" in names
        assert "imagemagick" in names

    def test_brew_install(self):
        text = "brew install ffmpeg yt-dlp"
        deps = _extract_packages(text)
        names = {d.name for d in deps}
        assert "ffmpeg" in names
        assert "yt-dlp" in names

    def test_cargo_install(self):
        text = "cargo install ripgrep"
        deps = _extract_packages(text)
        assert any(d.name == "ripgrep" and d.ecosystem == "cargo" for d in deps)

    def test_go_install(self):
        text = "go install github.com/user/tool@latest"
        deps = _extract_packages(text)
        assert len(deps) >= 1

    def test_no_packages_in_plain_text(self):
        text = "This is just a description of a skill"
        deps = _extract_packages(text)
        assert len(deps) == 0


class TestAPIKeyExtraction:
    """Test API key pattern detection."""

    def test_openai_key(self):
        text = "Requires OPENAI_API_KEY to be set"
        deps = _extract_api_keys(text)
        assert any("OpenAI" in d.name for d in deps)

    def test_anthropic_key(self):
        text = "Set ANTHROPIC_API_KEY in your environment"
        deps = _extract_api_keys(text)
        assert any("Anthropic" in d.name for d in deps)

    def test_multiple_keys(self):
        text = "Needs OPENAI_API_KEY and GITHUB_TOKEN"
        deps = _extract_api_keys(text)
        names = {d.name for d in deps}
        assert any("OpenAI" in n for n in names)
        assert any("GitHub" in n for n in names)

    def test_aws_keys(self):
        text = "Configure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY"
        deps = _extract_api_keys(text)
        assert any("AWS" in d.name for d in deps)

    def test_stripe_key(self):
        text = "Set STRIPE_SECRET_KEY for payments"
        deps = _extract_api_keys(text)
        assert any("Stripe" in d.name for d in deps)

    def test_no_keys_in_plain_text(self):
        text = "A simple skill for code formatting"
        deps = _extract_api_keys(text)
        assert len(deps) == 0


class TestToolExtraction:
    """Test CLI tool detection."""

    def test_docker(self):
        text = "Requires docker to run containers"
        deps = _extract_tools(text)
        assert any(d.name == "docker" for d in deps)

    def test_kubectl(self):
        text = "Uses kubectl to manage kubernetes clusters"
        deps = _extract_tools(text)
        assert any(d.name == "kubectl" for d in deps)

    def test_ffmpeg(self):
        text = "Process video with ffmpeg"
        deps = _extract_tools(text)
        assert any(d.name == "ffmpeg" for d in deps)

    def test_git(self):
        text = "Version control with git"
        deps = _extract_tools(text)
        assert any(d.name == "git" for d in deps)

    def test_multiple_tools(self):
        text = "Uses docker and kubectl for deployment"
        deps = _extract_tools(text)
        names = {d.name for d in deps}
        assert "docker" in names
        assert "kubectl" in names


class TestRuntimeExtraction:
    """Test runtime requirement detection."""

    def test_python(self):
        text = "Requires python 3.10 or higher"
        deps = _extract_runtimes(text)
        assert any(d.name == "python" for d in deps)

    def test_node(self):
        text = "Needs node.js v18"
        deps = _extract_runtimes(text)
        assert any(d.name == "node" for d in deps)

    def test_rust(self):
        text = "Built with rust"
        deps = _extract_runtimes(text)
        assert any(d.name == "rust" for d in deps)


class TestEnvVarExtraction:
    """Test environment variable detection."""

    def test_custom_env_var(self):
        text = "Set MY_SERVICE_URL and API_TOKEN_SECRET"
        deps = _extract_env_vars(text)
        names = {d.name for d in deps}
        assert "MY_SERVICE_URL" in names or "API_TOKEN_SECRET" in names

    def test_no_env_vars_in_plain(self):
        text = "Just a simple skill"
        deps = _extract_env_vars(text)
        assert len(deps) == 0


class TestExtractFromText:
    """Test the main extraction function."""

    def test_combined_extraction(self):
        text = """
        This skill requires python 3.10+ and pip install requests flask.
        Set OPENAI_API_KEY. Uses docker for containerization.
        """
        deps = extract_dependencies_from_text(text)
        types = {d.dep_type for d in deps}
        assert DepType.PACKAGE in types
        assert DepType.TOOL in types
        assert DepType.API in types

    def test_min_confidence_filter(self):
        text = "Uses git for version control"
        deps = extract_dependencies_from_text(text, min_confidence=0.90)
        # git has confidence 0.70, should be filtered
        assert len(deps) == 0

    def test_empty_text(self):
        assert extract_dependencies_from_text("") == []
        assert extract_dependencies_from_text("   ") == []
        assert extract_dependencies_from_text("short") == []

    def test_include_env_vars(self):
        text = "Requires DATABASE_URL and OPENAI_API_KEY"
        deps = extract_dependencies_from_text(text, include_env_vars=True)
        types = {d.dep_type for d in deps}
        assert DepType.ENV_VAR in types or DepType.API in types


class TestExtractFromVersion:
    """Test extraction from v3 version dicts."""

    def test_from_summary(self):
        version = {
            "skill_id": "test-123",
            "name": "test-skill",
            "summary": "Requires python 3.10 and pip install requests",
        }
        deps = extract_from_version(version)
        assert len(deps) > 0

    def test_from_declared(self):
        version = {
            "skill_id": "test-123",
            "name": "test-skill",
            "summary": "A skill",
            "declared_dependencies": {
                "tools": ["docker", "kubectl"],
                "apis": [{"name": "OpenAI API", "version": "v1"}],
            },
        }
        deps = extract_from_version(version)
        declared = [d for d in deps if d.source == "declared"]
        assert len(declared) >= 2

    def test_empty_version(self):
        version = {"skill_id": "test", "name": "test"}
        deps = extract_from_version(version)
        assert isinstance(deps, list)


class TestDependencyGraph:
    """Test graph construction and queries."""

    def _make_graph(self) -> DependencyGraph:
        graph = DependencyGraph()
        graph.add_skill(
            "a",
            "skill-a",
            [
                ExtractedDependency(name="docker", dep_type=DepType.TOOL, confidence=0.9),
                ExtractedDependency(name="python", dep_type=DepType.RUNTIME, confidence=0.9),
            ],
        )
        graph.add_skill(
            "b",
            "skill-b",
            [
                ExtractedDependency(name="node", dep_type=DepType.RUNTIME, confidence=0.9),
            ],
        )
        graph.add_skill(
            "c",
            "skill-c",
            [
                ExtractedDependency(name="docker", dep_type=DepType.TOOL, confidence=0.9),
                ExtractedDependency(name="skill-a", dep_type=DepType.PACKAGE, confidence=0.8),
            ],
        )
        graph.resolve_edges()
        return graph

    def test_add_skill(self):
        graph = self._make_graph()
        assert "a" in graph._nodes
        assert "b" in graph._nodes
        assert "c" in graph._nodes

    def test_direct_dependencies(self):
        graph = self._make_graph()
        deps = graph.get_direct_dependencies("c")
        assert "a" in deps  # c depends on a

    def test_dependents(self):
        graph = self._make_graph()
        dependents = graph.get_dependents("a")
        assert "c" in dependents  # c depends on a

    def test_transitive_dependencies(self):
        graph = DependencyGraph()
        graph.add_skill("a", "a", [])
        graph.add_skill(
            "b",
            "b",
            [
                ExtractedDependency(name="a", dep_type=DepType.PACKAGE, confidence=0.9),
            ],
        )
        graph.add_skill(
            "c",
            "c",
            [
                ExtractedDependency(name="b", dep_type=DepType.PACKAGE, confidence=0.9),
            ],
        )
        graph.resolve_edges()
        transitive = graph.get_transitive_dependencies("c")
        assert "a" in transitive
        assert "b" in transitive

    def test_no_cycles_in_dag(self):
        graph = self._make_graph()
        cycles = graph.detect_cycles()
        assert len(cycles) == 0

    def test_detect_cycle(self):
        graph = DependencyGraph()
        graph.add_skill(
            "a",
            "a",
            [
                ExtractedDependency(name="b", dep_type=DepType.PACKAGE, confidence=0.9),
            ],
        )
        graph.add_skill(
            "b",
            "b",
            [
                ExtractedDependency(name="a", dep_type=DepType.PACKAGE, confidence=0.9),
            ],
        )
        graph.resolve_edges()
        cycles = graph.detect_cycles()
        assert len(cycles) == 1
        assert set(cycles[0]) == {"a", "b"}

    def test_external_dependencies(self):
        graph = self._make_graph()
        ext = graph.get_external_dependencies("a")
        names = {d.name for d in ext}
        assert "docker" in names
        assert "python" in names

    def test_conflict_detection(self):
        graph = DependencyGraph()
        graph.add_skill(
            "a",
            "a",
            [
                ExtractedDependency(
                    name="requests", dep_type=DepType.PACKAGE, version_constraint=">=2.0", confidence=0.9
                ),
            ],
        )
        graph.add_skill(
            "b",
            "b",
            [
                ExtractedDependency(
                    name="requests", dep_type=DepType.PACKAGE, version_constraint="<2.0", confidence=0.9
                ),
            ],
        )
        graph.resolve_edges()
        conflicts = graph.detect_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == "version"

    def test_stats(self):
        graph = self._make_graph()
        stats = graph.get_stats()
        assert stats["total_skills"] == 3
        assert stats["total_skill_edges"] == 1  # c -> a
        assert stats["total_external_deps"] > 0

    def test_from_versions(self):
        versions = [
            {
                "skill_id": "v1",
                "name": "skill-1",
                "summary": "Requires python and pip install flask",
            },
            {
                "skill_id": "v2",
                "name": "skill-2",
                "summary": "Uses docker and kubectl",
            },
        ]
        graph = DependencyGraph.from_versions(versions)
        assert graph._nodes["v1"].skill_name == "skill-1"
        assert graph._nodes["v2"].skill_name == "skill-2"
        ext1 = graph.get_external_dependencies("v1")
        ext2 = graph.get_external_dependencies("v2")
        assert len(ext1) > 0
        assert len(ext2) > 0


class TestDependencyDBSync:
    """Test DB sync operations."""

    def test_deps_to_db_format(self):
        from skillsbank.db.dep_sync import _deps_to_db_format

        deps = [
            ExtractedDependency(name="docker", dep_type=DepType.TOOL, confidence=0.9),
            ExtractedDependency(name="requests", dep_type=DepType.PACKAGE, ecosystem="pip", confidence=0.85),
            ExtractedDependency(name="OpenAI API", dep_type=DepType.API, confidence=0.95),
        ]
        result = _deps_to_db_format(deps)
        assert len(result["tools"]) == 1
        assert len(result["packages"]) == 1
        assert len(result["apis"]) == 1
        assert result["tools"][0]["name"] == "docker"
        assert result["packages"][0]["ecosystem"] == "pip"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
