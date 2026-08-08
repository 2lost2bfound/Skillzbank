"""Extract dependency information from skill content.

Works with summary, long_description, and raw_content when available.
Infers tool/API/package/env requirements from text patterns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class DepType(str, Enum):
    PACKAGE = "package"
    TOOL = "tool"
    API = "api"
    ENV_VAR = "env_var"
    RUNTIME = "runtime"


@dataclass
class ExtractedDependency:
    name: str
    dep_type: DepType
    source: str = "inferred"
    version_constraint: str | None = None
    ecosystem: str | None = None
    confidence: float = 0.8
    context: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "dep_type": self.dep_type.value,
            "source": self.source,
            "confidence": self.confidence,
        }
        if self.version_constraint:
            d["version_constraint"] = self.version_constraint
        if self.ecosystem:
            d["ecosystem"] = self.ecosystem
        if self.context:
            d["context"] = self.context
        return d


# --- Patterns for install commands ---

_PIP_INSTALL_RE = re.compile(
    r"pip(?:3)?\s+install\s+(?:-[a-zA-Z]+\s+)*([a-zA-Z0-9_\-\.]+(?:\s+[a-zA-Z0-9_\-\.]+)*)",
    re.IGNORECASE,
)
_NPM_INSTALL_RE = re.compile(
    r"(?:npm|yarn|pnpm)\s+(?:install|add)\s+(?:--[a-zA-Z-]+\s+)*([a-zA-Z0-9_@/\-\.]+(?:\s+[a-zA-Z0-9_@/\-\.]+)*)",
    re.IGNORECASE,
)
_APT_INSTALL_RE = re.compile(
    r"apt(?:-get)?\s+install\s+(?:-[a-zA-Z]+\s+)*([a-zA-Z0-9_\-\.]+(?:\s+[a-zA-Z0-9_\-\.]+)*)",
    re.IGNORECASE,
)
_BREW_INSTALL_RE = re.compile(
    r"brew\s+install\s+(?:--[a-zA-Z-]+\s+)*([a-zA-Z0-9_\-\.]+(?:\s+[a-zA-Z0-9_\-\.]+)*)",
    re.IGNORECASE,
)
_CARGO_INSTALL_RE = re.compile(
    r"cargo\s+install\s+(?:--[a-zA-Z-]+\s+)*([a-zA-Z0-9_\-\.]+)",
    re.IGNORECASE,
)
_GO_INSTALL_RE = re.compile(
    r"go\s+install\s+([a-zA-Z0-9_\-\.\/@:]+)",
    re.IGNORECASE,
)
_GEM_INSTALL_RE = re.compile(
    r"gem\s+install\s+(?:--[a-zA-Z]+\s+)*([a-zA-Z0-9_\-\.]+)",
    re.IGNORECASE,
)

# --- Patterns for API keys ---

_API_KEY_PATTERNS: list[tuple[str, str, float]] = [
    (r"OPENAI_API_KEY", "OpenAI API", 0.95),
    (r"ANTHROPIC_API_KEY", "Anthropic API", 0.95),
    (r"GROQ_API_KEY", "Groq API", 0.95),
    (r"GOOGLE_API_KEY|GEMINI_API_KEY", "Google AI API", 0.95),
    (r"HUGGINGFACE[_\-]?TOKEN|HF_TOKEN", "Hugging Face API", 0.95),
    (r"GITHUB_TOKEN|GH_TOKEN", "GitHub API", 0.90),
    (r"SLACK_(?:BOT_)?TOKEN", "Slack API", 0.90),
    (r"DISCORD_(?:BOT_)?TOKEN", "Discord API", 0.90),
    (r"STRIPE_(?:SECRET_)?KEY", "Stripe API", 0.90),
    (r"AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY", "AWS API", 0.90),
    (r"AZURE_(?:CLIENT_)?SECRET", "Azure API", 0.90),
    (r"GCP_|GOOGLE_APPLICATION_CREDENTIALS", "Google Cloud API", 0.90),
    (r"DATABASE_URL|DB_URL|POSTGRES_URL|MYSQL_URL|REDIS_URL", "Database", 0.85),
    (r"COHERE_API_KEY", "Cohere API", 0.90),
    (r"MISTRAL_API_KEY", "Mistral API", 0.90),
    (r"DEEPSEEK_API_KEY", "DeepSeek API", 0.90),
    (r"TOGETHER_API_KEY", "Together AI API", 0.90),
    (r"REPLICATE_API_TOKEN", "Replicate API", 0.90),
    (r"FIRECRAWL_API_KEY", "Firecrawl API", 0.90),
    (r"SERPER_API_KEY", "Serper API", 0.90),
    (r"TAVILY_API_KEY", "Tavily API", 0.90),
    (r"BRAVE_API_KEY", "Brave API", 0.90),
    (r"NEON_API_KEY", "Neon API", 0.90),
    (r"SENTRY_DSN|SENTRY_AUTH_TOKEN", "Sentry", 0.85),
    (r"DATADOG_API_KEY|DD_API_KEY", "Datadog API", 0.90),
    (r"NOTION_API_KEY|NOTION_TOKEN", "Notion API", 0.90),
    (r"FIREBASE_", "Firebase", 0.85),
    (r"SUPABASE_URL|SUPABASE_KEY|SUPABASE_SERVICE", "Supabase", 0.90),
    (r"VERCEL_TOKEN", "Vercel API", 0.90),
    (r"CLOUDFLARE_API_TOKEN", "Cloudflare API", 0.90),
    (r"NETLIFY_AUTH_TOKEN", "Netlify API", 0.90),
    (r"FIGMA_TOKEN|FIGMA_ACCESS_TOKEN", "Figma API", 0.90),
]

# --- Patterns for CLI tools ---

_TOOL_PATTERNS: list[tuple[str, str, float]] = [
    (r"\bdocker\b", "docker", 0.90),
    (r"\bkubectl\b", "kubectl", 0.90),
    (r"\bterraform\b", "terraform", 0.90),
    (r"\baws\s+(?:cli)?", "aws-cli", 0.85),
    (r"\bgcloud\b", "gcloud", 0.90),
    (r"\baz\b", "azure-cli", 0.85),
    (r"\bgh\b|\bgithub-cli\b", "gh", 0.85),
    (r"\bjq\b", "jq", 0.80),
    (r"\bcurl\b", "curl", 0.70),
    (r"\bwget\b", "wget", 0.70),
    (r"\bgit\b", "git", 0.70),
    (r"\bffmpeg\b", "ffmpeg", 0.90),
    (r"\byt-dlp\b", "yt-dlp", 0.95),
    (r"\bplaywright\b", "playwright", 0.90),
    (r"\bpuppeteer\b", "puppeteer", 0.90),
    (r"\bselenium\b", "selenium", 0.90),
    (r"\bchromium\b|\bchrome\b", "chromium", 0.80),
    (r"\bnode\b|\bnodejs\b", "node", 0.80),
    (r"\bpython3?\b", "python", 0.75),
    (r"\brustc?\b|\bcargo\b", "rust", 0.85),
    (r"\bgo\b(?:\s+install|\s+build)", "go", 0.80),
    (r"\bjavac?\b|\bmaven\b|\bgradle\b", "java", 0.80),
    (r"\bnpm\b", "npm", 0.80),
    (r"\byarn\b", "yarn", 0.80),
    (r"\bpnpm\b", "pnpm", 0.80),
    (r"\bpip3?\b", "pip", 0.75),
    (r"\buv\b", "uv", 0.85),
    (r"\bpoetry\b", "poetry", 0.85),
    (r"\bpdm\b", "pdm", 0.85),
    (r"\bconda\b", "conda", 0.85),
    (r"\brew\b", "brew", 0.80),
    (r"\bapt(?:-get)?\b", "apt", 0.75),
    (r"\byum\b", "yum", 0.75),
    (r"\bdnf\b", "dnf", 0.75),
    (r"\bpacman\b", "pacman", 0.75),
]

# --- Patterns for runtimes ---

_RUNTIME_PATTERNS: list[tuple[str, str, float]] = [
    (r"\bpython\s*(?:3\.\d+|>=?\s*3(?:\.\d+)?)?\b", "python", 0.85),
    (r"\bnode\.?js\s*(?:v?\d+|>=?\s*\d+)?\b", "node", 0.85),
    (r"\brust\s*(?:v?\d+\.\d+)?\b", "rust", 0.85),
    (r"\bgo\s*(?:v?1\.\d+)?\b", "go", 0.80),
    (r"\bjav(?:a|ascript)\s*(?:v?\d+)?\b", "java", 0.75),
    (r"\bdeno\b", "deno", 0.90),
    (r"\bbun\b", "bun", 0.90),
]


def _extract_packages(text: str) -> list[ExtractedDependency]:
    """Extract package dependencies from install commands."""
    deps: list[ExtractedDependency] = []
    seen: set[str] = set()

    patterns: list[tuple[re.Pattern[str], str]] = [
        (_PIP_INSTALL_RE, "pip"),
        (_NPM_INSTALL_RE, "npm"),
        (_APT_INSTALL_RE, "apt"),
        (_BREW_INSTALL_RE, "brew"),
        (_CARGO_INSTALL_RE, "cargo"),
        (_GO_INSTALL_RE, "go"),
        (_GEM_INSTALL_RE, "gem"),
    ]

    for pattern, eco in patterns:
        for m in pattern.finditer(text):
            pkgs = m.group(1).strip().split()
            for pkg in pkgs:
                pkg = pkg.strip().strip("'\"")
                if not pkg or pkg.startswith("-") or len(pkg) < 2:
                    continue
                key = f"{eco}:{pkg.lower()}"
                if key not in seen:
                    seen.add(key)
                    deps.append(
                        ExtractedDependency(
                            name=pkg,
                            dep_type=DepType.PACKAGE,
                            source="inferred",
                            ecosystem=eco,
                            confidence=0.85,
                            context=m.group(0)[:100],
                        )
                    )

    return deps


def _extract_api_keys(text: str) -> list[ExtractedDependency]:
    """Extract API key requirements from text."""
    deps: list[ExtractedDependency] = []
    seen: set[str] = set()

    for pattern, name, conf in _API_KEY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE) and name not in seen:
            seen.add(name)
            deps.append(
                ExtractedDependency(
                    name=name,
                    dep_type=DepType.API,
                    source="inferred",
                    confidence=conf,
                )
            )

    return deps


def _extract_tools(text: str) -> list[ExtractedDependency]:
    """Extract tool requirements from text."""
    deps: list[ExtractedDependency] = []
    seen: set[str] = set()

    for pattern, name, conf in _TOOL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE) and name not in seen:
            seen.add(name)
            deps.append(
                ExtractedDependency(
                    name=name,
                    dep_type=DepType.TOOL,
                    source="inferred",
                    confidence=conf,
                )
            )

    return deps


def _extract_runtimes(text: str) -> list[ExtractedDependency]:
    """Extract runtime requirements from text."""
    deps: list[ExtractedDependency] = []
    seen: set[str] = set()

    for pattern, name, conf in _RUNTIME_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m and name not in seen:
            seen.add(name)
            version = None
            ver_match = re.search(r"[v>=<\s](\d+(?:\.\d+)*)", m.group(0))
            if ver_match:
                version = ver_match.group(1)
            deps.append(
                ExtractedDependency(
                    name=name,
                    dep_type=DepType.RUNTIME,
                    source="inferred",
                    version_constraint=version,
                    confidence=conf,
                )
            )

    return deps


def _extract_env_vars(text: str) -> list[ExtractedDependency]:
    """Extract environment variable requirements from text."""
    deps: list[ExtractedDependency] = []
    seen: set[str] = set()

    env_pattern = re.compile(r"\b([A-Z][A-Z0-9_]{2,}(?:_KEY|_TOKEN|_SECRET|_URL|_DSN|_ID))\b")
    for m in env_pattern.finditer(text):
        name = m.group(1)
        if name not in seen and not name.startswith("THE_"):
            seen.add(name)
            deps.append(
                ExtractedDependency(
                    name=name,
                    dep_type=DepType.ENV_VAR,
                    source="inferred",
                    confidence=0.70,
                )
            )

    return deps


def extract_dependencies_from_text(
    text: str,
    *,
    include_env_vars: bool = False,
    min_confidence: float = 0.70,
) -> list[ExtractedDependency]:
    """Extract all dependency types from text content.

    Args:
        text: Source text (summary, description, raw content)
        include_env_vars: Whether to extract env var requirements
        min_confidence: Minimum confidence threshold

    Returns:
        Deduplicated list of ExtractedDependency
    """
    if not text or len(text.strip()) < 10:
        return []

    all_deps: list[ExtractedDependency] = []
    all_deps.extend(_extract_packages(text))
    all_deps.extend(_extract_api_keys(text))
    all_deps.extend(_extract_tools(text))
    all_deps.extend(_extract_runtimes(text))
    if include_env_vars:
        all_deps.extend(_extract_env_vars(text))

    # Filter by confidence
    return [d for d in all_deps if d.confidence >= min_confidence]


def extract_from_version(
    version: dict[str, Any],
    *,
    include_env_vars: bool = False,
) -> list[ExtractedDependency]:
    """Extract dependencies from a v3 version dict.

    Combines summary + long_description + raw_content.
    Also merges any declared dependencies.
    """
    texts: list[str] = []

    summary = version.get("summary")
    if summary and isinstance(summary, str):
        texts.append(summary)

    ld = version.get("long_description")
    if ld and isinstance(ld, str):
        texts.append(ld)

    rc = version.get("raw_content")
    if rc and isinstance(rc, str):
        texts.append(rc)

    combined = "\n".join(texts)
    deps = extract_dependencies_from_text(
        combined,
        include_env_vars=include_env_vars,
    )

    # Merge declared dependencies (from ecosystem_metadata or declared_dependencies)
    declared = version.get("declared_dependencies", {})
    if isinstance(declared, dict):
        for dep_type_key in ["tools", "apis", "packages", "env_vars", "runtimes"]:
            items = declared.get(dep_type_key, [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, str):
                        deps.append(
                            ExtractedDependency(
                                name=item,
                                dep_type=DepType(dep_type_key.rstrip("s")),
                                source="declared",
                                confidence=1.0,
                            )
                        )
                    elif isinstance(item, dict):
                        name = item.get("name", "")
                        if name:
                            deps.append(
                                ExtractedDependency(
                                    name=name,
                                    dep_type=DepType(dep_type_key.rstrip("s")),
                                    source="declared",
                                    version_constraint=item.get("version"),
                                    confidence=1.0,
                                )
                            )

    return deps
