"""Phase 4: Capability taxonomy and normalization engine.

Builds a canonical taxonomy from the 1,050 unique capability strings,
groups them into categories, and normalizes variants to canonical forms.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class TaxonomyNode:
    """A node in the capability taxonomy."""

    canonical: str
    category: str
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    parent: str | None = None


# Master taxonomy: canonical_name -> TaxonomyNode
CAPABILITY_TAXONOMY: dict[str, TaxonomyNode] = {}

# Category definitions with canonical capabilities
_CATEGORIES = {
    "security": {
        "reverse_engineering": ["reverse-engineering", "reverse_engineering", "reverseengineering"],
        "penetration_testing": ["penetration-testing", "penetration_testing", "pentest", "pentesting"],
        "malware_analysis": ["malware-analysis", "malware_analysis", "malwareanalysis"],
        "ctf": ["ctf", "capture-the-flag", "capture_the_flag"],
        "api_security": ["api-security", "api_security", "apisecurity"],
        "code_audit": ["code-audit", "code_audit", "codeaudit"],
        "mobile_security": ["mobile-security", "mobile_security", "mobilesecurity"],
        "hardware_security": ["hardware-security", "hardware_security", "hardwaresecurity"],
        "ai_security": ["ai-security", "ai_security", "aisecurity"],
        "security_scanning": ["security", "security-scanning", "vulnerability-scanning"],
        "threat_hunting": ["threat-hunting", "threat_hunting", "threathunting"],
        "forensics": ["forensics", "digital-forensics", "incident-response"],
        "exploitation": ["exploitation", "exploit", "exploit-development"],
    },
    "cloud": {
        "azure": ["azure", "microsoft-azure"],
        "gcp": ["google", "gcp", "google-cloud"],
        "gke": ["gke", "google-kubernetes-engine"],
        "firebase": ["firebase"],
        "aws": ["aws", "amazon-web-services"],
        "cloud_deployment": ["cloud", "deploy", "deployment"],
        "storage": ["storage", "object-storage", "blob-storage"],
        "serverless": ["serverless", "lambda", "functions"],
        "cosmos_db": ["cosmos", "cosmosdb", "cosmos-db"],
        "keyvault": ["keyvault", "key-vault"],
        "terraform": ["terraform", "iac", "infrastructure-as-code"],
    },
    "ai_ml": {
        "training": ["train", "training", "model-training"],
        "inference": ["inference", "model-inference", "prediction"],
        "nlp": ["nlp", "natural-language-processing", "text-processing"],
        "computer_vision": ["computer-vision", "cv", "image-processing"],
        "agent_development": ["agent", "agents", "agent-development"],
        "huggingface": ["huggingface", "hugging-face"],
        "neMo": ["nemo"],
        "finetune": ["finetune", "fine-tune", "fine_tune"],
        "chat": ["chat", "chatbot", "conversational"],
        "transcription": ["transcription", "speech-to-text", "stt"],
        "cuopt": ["cuopt"],
        "earth2studio": ["earth2studio", "earth-2"],
    },
    "code_quality": {
        "code_review": ["review", "code-review", "code_review"],
        "implementation": ["implementation", "implement", "coding"],
        "refactoring": ["refactoring", "refactor"],
        "testing": ["testing", "test", "qa", "quality-assurance"],
        "linting": ["linting", "lint", "formatting"],
        "optimization": ["optimization", "optimize", "perf", "performance"],
    },
    "languages": {
        "dotnet": ["dotnet", "csharp", "c#", ".net"],
        "java": ["java"],
        "rust": ["rust"],
        "python": ["python"],
        "javascript": ["javascript", "js"],
        "typescript": ["typescript", "ts"],
        "go": ["go", "golang"],
        "ruby": ["ruby"],
        "swift": ["swift"],
        "kotlin": ["kotlin"],
    },
    "data": {
        "data_processing": ["data", "data-processing", "etl"],
        "analytics": ["analytics", "analysis", "data-analytics"],
        "financial_analysis": ["financial-analysis", "financial_analysis", "finance"],
        "search": ["search", "search-engine", "information-retrieval"],
        "database": ["database", "db", "sql", "nosql"],
    },
    "ui_ux": {
        "design_guidance": ["design-guidance", "design", "ui-design"],
        "typography": ["typography", "fonts", "type-design"],
        "animation": ["animation", "motion", "motion-design"],
        "frontend": ["frontend", "front-end", "ui-development"],
        "accessibility": ["accessibility", "a11y", "wcag"],
        "color_theory": ["color-theory", "color_theory", "color-scheme"],
        "figma": ["figma"],
        "layout": ["layout", "responsive", "grid"],
    },
    "devops": {
        "ci_cd": ["ci-cd", "ci_cd", "cicd", "continuous-integration"],
        "workflow": ["workflow", "workflows", "automation"],
        "setup": ["setup", "configuration", "install"],
        "monitoring": ["monitoring", "observability", "logging"],
        "containerization": ["docker", "container", "kubernetes"],
    },
    "nvidia": {
        "doca": ["doca"],
        "tao": ["tao"],
        "jetson": ["jetson"],
        "vss": ["vss"],
        "mbridge": ["mbridge"],
        "i4h": ["i4h"],
        "nvclip": ["nvclip"],
        "nvtron": ["nvtron"],
        "nvflare": ["nvflare"],
    },
    "tools": {
        "ida_pro": ["ida-pro", "ida_pro", "idapro"],
        "ghidra": ["ghidra"],
        "radare2": ["radare2", "r2"],
        "debugging": ["debugging", "debug"],
    },
    "media": {
        "video": ["video", "video-editing", "video-processing"],
        "frame_extraction": ["frame-extraction", "frame_extraction", "frameextraction"],
        "image": ["image", "image-processing", "graphics"],
        "audio": ["audio", "sound", "music"],
    },
    "documentation": {
        "writing": ["writing", "documentation", "docs"],
        "wiki": ["wiki", "knowledge-base"],
        "presentation": ["presentation", "slides", "pptx"],
    },
    "integration": {
        "api": ["api", "rest", "graphql", "webhook"],
        "routing": ["routing", "router", "middleware"],
        "relay": ["relay", "proxy", "gateway"],
    },
    "business": {
        "ads": ["ads", "advertising", "marketing"],
        "communication": ["communication", "messaging", "notification"],
        "navigation": ["navigation", "routing", "maps"],
        "resource": ["resource", "resource-management"],
        "generate": ["generate", "generation", "create", "creation"],
        "basics": ["basics", "fundamentals", "introduction"],
        "app": ["app", "application"],
        "solution": ["solution", "solutions"],
        "skill": ["skill", "skills"],
        "mgmt": ["mgmt", "management"],
    },
    "platform": {
        "platform": ["platform", "platform-engineering"],
        "manager": ["manager"],
        "customize": ["customize", "customization", "config"],
        "general": ["general", "general-purpose", "utility"],
        "run": ["run", "runtime", "execution"],
    },
}


def _build_taxonomy() -> None:
    """Build the taxonomy from category definitions."""
    for category, capabilities in _CATEGORIES.items():
        for canonical, aliases in capabilities.items():
            node = TaxonomyNode(
                canonical=canonical,
                category=category,
                aliases=aliases,
                description=f"{canonical.replace('_', ' ').title()} capability",
            )
            CAPABILITY_TAXONOMY[canonical] = node

            # Map all aliases to the canonical form
            for alias in aliases:
                normalized = _normalize_name(alias)
                if normalized not in _ALIAS_MAP:
                    _ALIAS_MAP[normalized] = canonical


# Alias lookup: normalized_name -> canonical_name
_ALIAS_MAP: dict[str, str] = {}


def _normalize_name(name: str) -> str:
    """Normalize a capability name for lookup."""
    return re.sub(r"[-_\s]+", "", name.lower().strip())


def classify_capability(raw_name: str) -> tuple[str, str, str]:
    """Classify a raw capability name into (canonical, category, taxonomy_path).

    Returns:
        (canonical_name, category, taxonomy_path)
        If no match, returns (normalized_raw, "uncategorized", "uncategorized/{normalized}")
    """
    normalized = _normalize_name(raw_name)

    # Direct alias match
    if normalized in _ALIAS_MAP:
        canonical = _ALIAS_MAP[normalized]
        node = CAPABILITY_TAXONOMY[canonical]
        return canonical, node.category, f"{node.category}/{canonical}"

    # Fuzzy match: check if any alias is a substring
    for alias_norm, canonical in _ALIAS_MAP.items():
        if len(alias_norm) >= 4 and (alias_norm in normalized or normalized in alias_norm):
            node = CAPABILITY_TAXONOMY[canonical]
            return canonical, node.category, f"{node.category}/{canonical}"

    # No match: return normalized form as uncategorized
    clean = re.sub(r"[^a-z0-9_]", "_", normalized).strip("_")
    if not clean:
        clean = "unknown"
    return clean, "uncategorized", f"uncategorized/{clean}"


def normalize_capabilities(capabilities: list[dict]) -> list[dict]:
    """Normalize a list of capability dicts, adding canonical/category/taxonomy_path.

    Input: list of {"name": "...", ...}
    Output: list of {"name": "...", "canonical": "...", "category": "...", "taxonomy_path": "..."}
    """
    result = []
    seen_canonical = set()

    for cap in capabilities:
        name = cap.get("name", "") if isinstance(cap, dict) else str(cap)
        if not name:
            continue

        canonical, category, taxonomy_path = classify_capability(name)

        # Deduplicate by canonical name
        if canonical in seen_canonical:
            continue
        seen_canonical.add(canonical)

        entry = dict(cap) if isinstance(cap, dict) else {"name": name}
        entry["canonical"] = canonical
        entry["category"] = category
        entry["taxonomy_path"] = taxonomy_path
        result.append(entry)

    return result


def get_taxonomy_stats() -> dict:
    """Return taxonomy statistics."""
    total_nodes = len(CAPABILITY_TAXONOMY)
    total_aliases = len(_ALIAS_MAP)
    categories = {n.category for n in CAPABILITY_TAXONOMY.values()}
    return {
        "total_taxonomy_nodes": total_nodes,
        "total_alias_mappings": total_aliases,
        "categories": sorted(categories),
        "category_counts": {
            cat: sum(1 for n in CAPABILITY_TAXONOMY.values() if n.category == cat) for cat in sorted(categories)
        },
    }


# Build on import
_build_taxonomy()
