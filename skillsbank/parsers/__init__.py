"""Parser plugin system for extracting structured data from skill files.

Parsers detect file format (SKILL.md, AGENTS.md, README) and extract
structured metadata into a normalized SkillParseResult.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SkillParseResult:
    """Normalized output from any parser."""

    name: str = ""
    summary: str = ""
    description: str = ""
    domain: str = ""
    capabilities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    input_format: str = "unknown"
    output_format: str = "unknown"
    dependencies: list[str] = field(default_factory=list)
    install_methods: list[dict[str, str]] = field(default_factory=list)
    compatibility: list[str] = field(default_factory=list)
    raw_content: str = ""
    format_detected: str = "unknown"
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseParser(ABC):
    """Base class for all skill file parsers."""

    @abstractmethod
    def can_parse(self, content: str, filename: str) -> bool:
        """Return True if this parser can handle the given content."""
        ...

    @abstractmethod
    def parse(self, content: str, filename: str, repo: str = "") -> SkillParseResult:
        """Parse the content and return structured data."""
        ...

    @property
    @abstractmethod
    def format_name(self) -> str:
        """Human-readable format name."""
        ...


class SKILLMdParser(BaseParser):
    """Parser for SKILL.md files (Anthropic/matt-pocock format).

    Typical structure:
    - YAML frontmatter (optional)
    - # Title
    - Description paragraphs
    - ## sections (Triggers, When to use, etc.)
    """

    def can_parse(self, content: str, filename: str) -> bool:
        if filename.lower().endswith("skill.md"):
            return True
        # Check for SKILL.md-specific signals (not just any markdown with H2)
        skill_signals = [
            r"(?i)^##\s+(?:when to use|triggers|differentiator|voice triggers)",
            r"(?i)^##\s+(?:what|description|usage)",
            r"(?i)\btrigger\s+phrases?\b",
        ]
        return any(re.search(s, content, re.MULTILINE) for s in skill_signals)

    def parse(self, content: str, filename: str, repo: str = "") -> SkillParseResult:
        result = SkillParseResult(raw_content=content, format_detected="SKILL.md")

        # Strip YAML frontmatter
        content_clean = content
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if fm_match:
            content_clean = content[fm_match.end() :]

        # Extract title from first H1
        title_match = re.search(r"^#\s+(.+)", content_clean, re.MULTILINE)
        if title_match:
            result.name = title_match.group(1).strip()

        # Extract summary (first paragraph after title)
        after_title = content_clean[title_match.end() :] if title_match else content_clean
        para_match = re.search(r"\n\n([^#\n][^\n]+)", after_title)
        if para_match:
            result.summary = para_match.group(1).strip()

        # Extract sections
        sections = self._extract_sections(content_clean)

        # Domain inference from content
        result.domain = self._infer_domain(content_clean, sections)

        # Capabilities from triggers/sections
        result.capabilities = self._extract_capabilities(sections)

        # Tags from content patterns
        result.tags = self._extract_tags(content_clean, sections)

        # Dependencies
        result.dependencies = self._extract_dependencies(content_clean)

        # Compatibility
        result.compatibility = self._extract_compatibility(sections)

        # Confidence based on extraction quality
        result.confidence = self._score_confidence(result)

        return result

    def _extract_sections(self, content: str) -> dict[str, str]:
        """Extract H2 sections into a dict (handles indented headers)."""
        sections = {}
        # Split on H2 headers, capture heading + body until next H2
        pattern = re.compile(r"^\s*##\s+([^\n]+)\n(.*?)(?=^\s*##\s|\Z)", re.MULTILINE | re.DOTALL)
        for match in pattern.finditer(content):
            heading = match.group(1).strip().lower()
            body = match.group(2).strip()
            sections[heading] = body
        return sections

    def _infer_domain(self, content: str, sections: dict) -> str:
        """Infer primary domain from content."""
        content_lower = content.lower()

        domain_signals = {
            "security": ["security", "pentest", "vulnerability", "exploit", "malware", "threat"],
            "frontend": ["ui", "css", "react", "vue", "angular", "frontend", "design", "component"],
            "backend": ["api", "server", "database", "backend", "microservice", "endpoint"],
            "devops": ["deploy", "ci/cd", "docker", "kubernetes", "terraform", "infrastructure"],
            "data": ["data", "analytics", "pipeline", "etl", "sql", "pandas", "spark"],
            "testing": ["test", "qa", "automation", "playwright", "cypress", "selenium"],
            "ai_ml": ["machine learning", "ml", "ai", "model", "training", "neural", "llm"],
            "documentation": ["doc", "readme", "guide", "tutorial", "documentation"],
            "code_quality": ["lint", "format", "refactor", "review", "code quality"],
            "research": ["research", "analysis", "investigate", "study"],
        }

        scores = {}
        for domain, signals in domain_signals.items():
            score = sum(1 for s in signals if s in content_lower)
            if score > 0:
                scores[domain] = score

        if scores:
            return max(scores, key=scores.get)
        return "general"

    def _extract_capabilities(self, sections: dict) -> list[str]:
        """Extract capabilities from sections."""
        caps = []

        # Look for trigger/capability sections
        for key in ["triggers", "when to use", "capabilities", "features", "what it does"]:
            if key in sections:
                # Extract bullet points
                bullets = re.findall(r"[-*]\s+(.+)", sections[key])
                caps.extend(b.strip() for b in bullets)

        # If no explicit capabilities, extract from first section content
        if not caps:
            for key, body in sections.items():
                bullets = re.findall(r"[-*]\s+(.+)", body)
                if bullets:
                    caps.extend(b.strip() for b in bullets[:5])
                    break

        return caps[:20]  # Limit

    def _extract_tags(self, content: str, sections: dict) -> list[str]:
        """Extract tags from content patterns."""
        tags = set()
        content_lower = content.lower()

        # Common tech tags
        tech_patterns = [
            r"\b(python|javascript|typescript|rust|go|java|ruby|swift|kotlin)\b",
            r"\b(react|vue|angular|svelte|nextjs|nuxt)\b",
            r"\b(docker|kubernetes|terraform|ansible)\b",
            r"\b(postgres|mysql|redis|mongodb|sqlite)\b",
            r"\b(aws|gcp|azure|vercel|netlify|fly\.io)\b",
            r"\b(playwright|cypress|selenium|jest|vitest|pytest)\b",
        ]

        for pattern in tech_patterns:
            matches = re.findall(pattern, content_lower)
            tags.update(matches)

        return sorted(tags)[:15]

    def _extract_dependencies(self, content: str) -> list[str]:
        """Extract dependencies from content."""
        deps = []
        # Look for code blocks with install commands
        install_blocks = re.findall(r"```(?:bash|sh)?\n((?:npm|pip|cargo|brew|apt)\s+install[^\n]+)", content)
        for block in install_blocks:
            deps.extend(block.strip().split("\n"))

        # Look for "requires" or "dependencies" mentions
        req_match = re.findall(r"(?:requires?|dependencies?):\s*([^\n]+)", content, re.IGNORECASE)
        for match in req_match:
            deps.extend(d.strip() for d in match.split(","))

        return deps[:10]

    def _extract_compatibility(self, sections: dict) -> list[str]:
        """Extract compatibility info."""
        compat = []
        for key in ["compatibility", "supported", "platforms", "ecosystems"]:
            if key in sections:
                bullets = re.findall(r"[-*]\s+(.+)", sections[key])
                compat.extend(b.strip() for b in bullets)
        return compat

    def _score_confidence(self, result: SkillParseResult) -> float:
        """Score parsing confidence 0.0-1.0."""
        score = 0.0
        if result.name:
            score += 0.25
        if result.summary:
            score += 0.2
        if result.capabilities:
            score += 0.25
        if result.domain != "general":
            score += 0.1
        if result.tags:
            score += 0.1
        if result.dependencies:
            score += 0.1
        return min(score, 1.0)

    @property
    def format_name(self) -> str:
        return "SKILL.md"


class AGENTSmdParser(BaseParser):
    """Parser for AGENTS.md files (agent instruction format).

    Typical structure:
    - # Agent Name
    - Description/instructions
    - ## Sections (Rules, Tools, Workflow, etc.)
    """

    def can_parse(self, content: str, filename: str) -> bool:
        if filename.lower().endswith("agents.md"):
            return True
        # Check for agent-style patterns
        agent_signals = [
            r"you are\b",
            r"agent\b",
            r"workflow\b",
            r"when (?:the )?user",
            r"## (?:rules|guidelines|tools|workflow)",
        ]
        content_lower = content.lower()
        return any(re.search(s, content_lower) for s in agent_signals)

    def parse(self, content: str, filename: str, repo: str = "") -> SkillParseResult:
        result = SkillParseResult(raw_content=content, format_detected="AGENTS.md")

        # Extract title
        title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        if title_match:
            result.name = title_match.group(1).strip()
        elif repo:
            result.name = repo.split("/")[-1] if "/" in repo else repo

        # Summary from first paragraph
        para_match = re.search(r"\n\n([^#\n][^\n]+)", content)
        if para_match:
            result.summary = para_match.group(1).strip()[:200]

        # Extract sections
        sections = {}
        pattern = re.compile(r"^\s*##\s+([^\n]+)\n(.*?)(?=^\s*##\s|\Z)", re.MULTILINE | re.DOTALL)
        for match in pattern.finditer(content):
            sections[match.group(1).strip().lower()] = match.group(2).strip()

        # Capabilities from workflow/rules
        caps = []
        for key in ["workflow", "capabilities", "what you can do", "features"]:
            if key in sections:
                bullets = re.findall(r"[-*]\s+(.+)", sections[key])
                caps.extend(b.strip() for b in bullets[:10])
        result.capabilities = caps

        # Tags from content
        content_lower = content.lower()
        tech_patterns = [
            r"\b(python|javascript|typescript|rust|go|java)\b",
            r"\b(react|vue|angular|svelte)\b",
            r"\b(docker|kubernetes|terraform)\b",
        ]
        tags = set()
        for pattern in tech_patterns:
            tags.update(re.findall(pattern, content_lower))
        result.tags = sorted(tags)

        result.confidence = self._score_confidence(result)
        return result

    def _score_confidence(self, result: SkillParseResult) -> float:
        score = 0.0
        if result.name:
            score += 0.3
        if result.summary:
            score += 0.2
        if result.capabilities:
            score += 0.3
        if result.tags:
            score += 0.2
        return min(score, 1.0)

    @property
    def format_name(self) -> str:
        return "AGENTS.md"


class ReadmeParser(BaseParser):
    """Parser for README.md files (general repo docs).

    Fallback parser — extracts whatever structure it can find.
    """

    def can_parse(self, content: str, filename: str) -> bool:
        return filename.lower().startswith("readme") and filename.lower().endswith(".md")

    def parse(self, content: str, filename: str, repo: str = "") -> SkillParseResult:
        result = SkillParseResult(raw_content=content, format_detected="README.md")

        # Extract title
        title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        if title_match:
            result.name = title_match.group(1).strip()
        elif repo:
            result.name = repo.split("/")[-1] if "/" in repo else repo

        # Summary from first paragraph or blockquote
        para_match = re.search(r"\n\n(?:>\s*)?([^#\n][^\n]+)", content)
        if para_match:
            result.summary = para_match.group(1).strip()[:200]

        # Extract badges/shields for tags
        badges = re.findall(r"!\[.*?\]\(https?://img\.shields\.io/badge/([^-]+)", content)
        result.tags = [b.lower().strip() for b in badges[:5]]

        # Look for install sections
        install_match = re.search(
            r"##\s+(?:install|setup|getting\s+started)\s*\n(.*?)(?=##|\Z)", content, re.IGNORECASE | re.DOTALL
        )
        if install_match:
            install_content = install_match.group(1)
            commands = re.findall(r"```(?:bash|sh)?\n((?:npm|pip|cargo|brew|apt|yarn|pnpm)\s+[^\n]+)", install_content)
            result.dependencies = commands[:5]

        # Capabilities from features section
        feat_match = re.search(
            r"##\s+(?:features|what|capabilities)\s*\n(.*?)(?=##|\Z)", content, re.IGNORECASE | re.DOTALL
        )
        if feat_match:
            bullets = re.findall(r"[-*]\s+(.+)", feat_match.group(1))
            result.capabilities = [b.strip() for b in bullets[:10]]

        result.confidence = self._score_confidence(result)
        return result

    def _score_confidence(self, result: SkillParseResult) -> float:
        score = 0.0
        if result.name:
            score += 0.3
        if result.summary:
            score += 0.2
        if result.capabilities:
            score += 0.3
        if result.tags:
            score += 0.1
        if result.dependencies:
            score += 0.1
        return min(score, 1.0)

    @property
    def format_name(self) -> str:
        return "README.md"


class ParserRegistry:
    """Auto-detecting parser registry."""

    def __init__(self) -> None:
        self._parsers: list[BaseParser] = [
            SKILLMdParser(),
            AGENTSmdParser(),
            ReadmeParser(),
        ]

    def register(self, parser: BaseParser) -> None:
        """Register a new parser."""
        self._parsers.insert(0, parser)  # Higher priority

    def detect_format(self, content: str, filename: str) -> str:
        """Detect the format of a skill file."""
        for parser in self._parsers:
            if parser.can_parse(content, filename):
                return parser.format_name
        return "unknown"

    def parse(self, content: str, filename: str, repo: str = "") -> SkillParseResult:
        """Auto-detect format and parse."""
        for parser in self._parsers:
            if parser.can_parse(content, filename):
                return parser.parse(content, filename, repo)

        # Fallback: treat as README
        return ReadmeParser().parse(content, filename, repo)

    def parse_with_format(self, content: str, filename: str, format_hint: str, repo: str = "") -> SkillParseResult:
        """Parse with an explicit format hint."""
        for parser in self._parsers:
            if parser.format_name == format_hint:
                return parser.parse(content, filename, repo)

        # Fallback to auto-detect
        return self.parse(content, filename, repo)
