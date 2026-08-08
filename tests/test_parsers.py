"""Tests for Phase 3: Parser plugin system."""

from skillsbank.parsers import (
    AGENTSmdParser,
    ParserRegistry,
    ReadmeParser,
    SKILLMdParser,
    SkillParseResult,
)


class TestSKILLMdParser:
    """Test SKILL.md format parser."""

    def test_can_parse_skill_md(self):
        parser = SKILLMdParser()
        assert parser.can_parse("# My Skill\n\n## When to use\n- Use when X", "SKILL.md")

    def test_parse_title(self):
        parser = SKILLMdParser()
        result = parser.parse("# Code Review\n\nReview code quality.", "SKILL.md")
        assert result.name == "Code Review"

    def test_parse_summary(self):
        parser = SKILLMdParser()
        result = parser.parse("# My Skill\n\nThis skill does amazing things.", "SKILL.md")
        assert "amazing things" in result.summary

    def test_parse_capabilities_from_triggers(self):
        parser = SKILLMdParser()
        content = """# Test Skill

## Triggers
- Code review request
- PR review
- Quality check
"""
        result = parser.parse(content, "SKILL.md")
        assert len(result.capabilities) >= 2
        assert "Code review request" in result.capabilities

    def test_parse_tags(self):
        parser = SKILLMdParser()
        content = "# Python Tool\n\nA tool for python and react development."
        result = parser.parse(content, "SKILL.md")
        assert "python" in result.tags

    def test_domain_inference_security(self):
        parser = SKILLMdParser()
        content = "# Pentest Tool\n\nSecurity vulnerability scanning and exploit detection."
        result = parser.parse(content, "SKILL.md")
        assert result.domain == "security"

    def test_domain_inference_frontend(self):
        parser = SKILLMdParser()
        content = "# UI Builder\n\nReact component and CSS design tool."
        result = parser.parse(content, "SKILL.md")
        assert result.domain == "frontend"

    def test_confidence_high(self):
        parser = SKILLMdParser()
        content = """# Full Skill

A complete skill with everything.

## Triggers
- Trigger 1
- Trigger 2

## Dependencies
- npm install foo
"""
        result = parser.parse(content, "SKILL.md")
        assert result.confidence > 0.5

    def test_confidence_low(self):
        parser = SKILLMdParser()
        result = parser.parse("just some text", "unknown.md")
        assert result.confidence < 0.5

    def test_format_detected(self):
        parser = SKILLMdParser()
        result = parser.parse("# Test", "SKILL.md")
        assert result.format_detected == "SKILL.md"


class TestAGENTSmdParser:
    """Test AGENTS.md format parser."""

    def test_can_parse_agents_md(self):
        parser = AGENTSmdParser()
        assert parser.can_parse("# My Agent\n\nYou are a helpful agent.", "AGENTS.md")

    def test_parse_title(self):
        parser = AGENTSmdParser()
        result = parser.parse("# Build Agent\n\nYou are a build agent.", "AGENTS.md")
        assert result.name == "Build Agent"

    def test_parse_workflow_capabilities(self):
        parser = AGENTSmdParser()
        content = """# Agent

You are a build agent.

## Workflow
- Step 1: Run tests
- Step 2: Build
- Step 3: Deploy
"""
        result = parser.parse(content, "AGENTS.md")
        assert len(result.capabilities) >= 2

    def test_format_detected(self):
        parser = AGENTSmdParser()
        result = parser.parse("# Agent", "AGENTS.md")
        assert result.format_detected == "AGENTS.md"


class TestReadmeParser:
    """Test README.md format parser."""

    def test_can_parse_readme(self):
        parser = ReadmeParser()
        assert parser.can_parse("# My Project\n\nA cool project.", "README.md")

    def test_parse_title(self):
        parser = ReadmeParser()
        result = parser.parse("# Cool Tool\n\nA tool.", "README.md")
        assert result.name == "Cool Tool"

    def test_parse_features(self):
        parser = ReadmeParser()
        content = """# Tool

## Features
- Feature 1
- Feature 2
- Feature 3
"""
        result = parser.parse(content, "README.md")
        assert len(result.capabilities) >= 2

    def test_parse_install_deps(self):
        parser = ReadmeParser()
        content = """# Tool

## Install
```bash
npm install cool-tool
```
"""
        result = parser.parse(content, "README.md")
        assert len(result.dependencies) >= 1

    def test_format_detected(self):
        parser = ReadmeParser()
        result = parser.parse("# Tool", "README.md")
        assert result.format_detected == "README.md"


class TestParserRegistry:
    """Test the parser registry auto-detection."""

    def test_auto_detect_skill_md(self):
        registry = ParserRegistry()
        content = "# Skill\n\n## When to use\n- Use when X"
        result = registry.parse(content, "SKILL.md")
        assert result.format_detected == "SKILL.md"

    def test_auto_detect_agents_md(self):
        registry = ParserRegistry()
        content = "# Agent\n\nYou are a helpful agent.\n\n## Rules\n- Rule 1"
        result = registry.parse(content, "AGENTS.md")
        assert result.format_detected == "AGENTS.md"

    def test_auto_detect_readme(self):
        registry = ParserRegistry()
        content = "# Project\n\nA cool project.\n\n## Install\nnpm install foo"
        result = registry.parse(content, "README.md")
        assert result.format_detected == "README.md"

    def test_fallback_to_readme(self):
        registry = ParserRegistry()
        result = registry.parse("some random content", "notes.txt")
        assert result.format_detected == "README.md"

    def test_parse_with_format_hint(self):
        registry = ParserRegistry()
        content = "# My Thing\n\nDoes stuff."
        result = registry.parse_with_format(content, "file.md", "SKILL.md")
        assert result.format_detected == "SKILL.md"

    def test_register_custom_parser(self):
        registry = ParserRegistry()

        class CustomParser(SKILLMdParser):
            @property
            def format_name(self):
                return "CUSTOM"

            def can_parse(self, content, filename):
                return "CUSTOM_MARKER" in content

            def parse(self, content, filename, repo=""):
                result = super().parse(content, filename, repo)
                result.format_detected = "CUSTOM"
                return result

        registry.register(CustomParser())
        result = registry.parse("CUSTOM_MARKER my skill\n\n## Triggers\n- X", "file.md")
        assert result.format_detected == "CUSTOM"

    def test_result_is_parse_result(self):
        registry = ParserRegistry()
        result = registry.parse("# Test", "SKILL.md")
        assert isinstance(result, SkillParseResult)
