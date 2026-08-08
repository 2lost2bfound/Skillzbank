"""License, quality, and security scoring for skills.

Computes quality scores from metadata completeness,
detects licenses from content patterns,
infers security risk from content analysis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# --- License Detection ---

_LICENSE_PATTERNS: list[tuple[str, str]] = [
    (r"\bMIT\b", "MIT"),
    (r"\bApache\s*(?:License)?\s*(?:2\.0|v2)", "Apache-2.0"),
    (r"\bApache-2\.0\b", "Apache-2.0"),
    (r"\bGPL\s*(?:v?3|v?2|3\.0|2\.0)", "GPL"),
    (r"\bGPL-3\.0\b", "GPL-3.0"),
    (r"\bGPL-2\.0\b", "GPL-2.0"),
    (r"\bLGPL\b", "LGPL"),
    (r"\bBSD\s*(?:2-Clause|3-Clause|Simplified)?", "BSD"),
    (r"\bBSD-3-Clause\b", "BSD-3-Clause"),
    (r"\bBSD-2-Clause\b", "BSD-2-Clause"),
    (r"\bISC\b", "ISC"),
    (r"\bMPL[- ]2\.0\b", "MPL-2.0"),
    (r"\bMozilla Public License\b", "MPL-2.0"),
    (r"\bUnlicense\b", "Unlicense"),
    (r"\bCC[- ](?:BY|0|SA|NC|ND)", "CC"),
    (r"\bCreative Commons\b", "CC"),
    (r"\bAGPL\b", "AGPL"),
    (r"\bAGPL-3\.0\b", "AGPL-3.0"),
    (r"\b(?:Open|Free) Software License\b", "OSL"),
]

_KNOWN_LICENSES = {
    "MIT",
    "Apache-2.0",
    "GPL",
    "GPL-2.0",
    "GPL-3.0",
    "LGPL",
    "BSD",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "MPL-2.0",
    "Unlicense",
    "CC",
    "AGPL",
    "AGPL-3.0",
    "OSL",
}


@dataclass
class LicenseResult:
    detected_type: str = "unknown"
    confidence: float = 0.0
    source: str = "none"
    redistributable: bool | None = None
    allows_modification: bool | None = None
    allows_commercial: bool | None = None
    requires_attribution: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.detected_type,
            "confidence": self.confidence,
            "source": self.source,
            "redistributable": self.redistributable,
            "allows_modification": self.allows_modification,
            "allows_commercial": self.allows_commercial,
            "requires_attribution": self.requires_attribution,
        }


_PERMISSIVE_LICENSES = {"MIT", "Apache-2.0", "BSD", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Unlicense"}
COPYLEFT_LICENSES = {"GPL", "GPL-2.0", "GPL-3.0", "LGPL", "AGPL", "AGPL-3.0", "MPL-2.0"}


def _infer_license_permissions(lic_type: str) -> dict[str, bool | None]:
    """Infer license permissions from type."""
    if lic_type in _PERMISSIVE_LICENSES:
        return {
            "redistributable": True,
            "allows_modification": True,
            "allows_commercial": True,
            "requires_attribution": lic_type not in {"Unlicense"},
        }
    if lic_type in COPYLEFT_LICENSES:
        return {
            "redistributable": True,
            "allows_modification": True,
            "allows_commercial": True,
            "requires_attribution": True,
        }
    return {
        "redistributable": None,
        "allows_modification": None,
        "allows_commercial": None,
        "requires_attribution": None,
    }


def detect_license(
    summary: str | None = None,
    ecosystem_metadata: dict[str, Any] | None = None,
    repo_license: str | None = None,
) -> LicenseResult:
    """Detect license from available sources.

    Priority: repo_license > ecosystem_metadata > content patterns.
    """
    # 1. Check repo license
    if repo_license and repo_license.lower() not in ("unknown", "none", ""):
        norm = repo_license.strip()
        if norm in _KNOWN_LICENSES:
            perms = _infer_license_permissions(norm)
            return LicenseResult(
                detected_type=norm,
                confidence=0.95,
                source="repo_metadata",
                **perms,
            )

    # 2. Check ecosystem_metadata
    em = ecosystem_metadata or {}
    em_lic = em.get("license")
    if isinstance(em_lic, str) and em_lic.lower() not in ("unknown", "none", ""):
        norm = em_lic.strip()
        if norm in _KNOWN_LICENSES:
            perms = _infer_license_permissions(norm)
            return LicenseResult(
                detected_type=norm,
                confidence=0.90,
                source="ecosystem_metadata",
                **perms,
            )
    elif isinstance(em_lic, dict):
        lic_type = em_lic.get("type", "")
        if lic_type and lic_type.lower() not in ("unknown", "none", ""):
            perms = _infer_license_permissions(lic_type)
            return LicenseResult(
                detected_type=lic_type,
                confidence=0.90,
                source="ecosystem_metadata",
                **perms,
            )

    # 3. Content pattern matching
    text = summary or ""
    for pattern, lic_type in _LICENSE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            perms = _infer_license_permissions(lic_type)
            return LicenseResult(
                detected_type=lic_type,
                confidence=0.70,
                source="content_pattern",
                **perms,
            )

    return LicenseResult()


# --- Quality Scoring ---


@dataclass
class QualityResult:
    overall_score: float = 0.0
    documentation_score: float = 0.0
    metadata_completeness: float = 0.0
    freshness_score: float = 0.0
    adoption_score: float = 0.0
    dependency_clarity: float = 0.0
    test_coverage: float = 0.0
    security_posture: float = 0.0
    dimensions: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": round(self.overall_score, 3),
            "documentation_score": round(self.documentation_score, 3),
            "metadata_completeness": round(self.metadata_completeness, 3),
            "freshness_score": round(self.freshness_score, 3),
            "adoption_score": round(self.adoption_score, 3),
            "dependency_clarity": round(self.dependency_clarity, 3),
            "test_coverage": round(self.test_coverage, 3),
            "security_posture": round(self.security_posture, 3),
            "dimensions": {k: round(v, 3) for k, v in self.dimensions.items()},
        }


def _score_documentation(version: dict[str, Any]) -> float:
    """Score documentation quality (0.0-1.0)."""
    score = 0.0
    summary = version.get("summary", "")
    long_desc = version.get("long_description", "")

    # Summary presence and length
    if summary:
        if len(summary) > 200:
            score += 0.3
        elif len(summary) > 100:
            score += 0.2
        elif len(summary) > 30:
            score += 0.1
        else:
            score += 0.05

    # Long description
    if long_desc and len(long_desc) > 100:
        score += 0.3

    # Has sections/capabilities
    caps = version.get("capabilities", [])
    if caps and isinstance(caps, list) and len(caps) > 0:
        score += 0.2

    # Has I/O shapes defined
    inp = version.get("input_format")
    out = version.get("output_format")
    if inp and inp not in ("unknown", "none", ""):
        score += 0.1
    if out and out not in ("unknown", "none", ""):
        score += 0.1

    return min(score, 1.0)


def _score_metadata_completeness(version: dict[str, Any]) -> float:
    """Score metadata completeness (0.0-1.0)."""
    fields_to_check = [
        ("name", 0.1),
        ("summary", 0.1),
        ("domain_primary", 0.1),
        ("input_format", 0.1),
        ("output_format", 0.1),
        ("capabilities", 0.15),
        ("tags", 0.1),
        ("install_methods", 0.1),
        ("declared_dependencies", 0.075),
        ("inferred_dependencies", 0.075),
    ]

    score = 0.0
    for field_name, weight in fields_to_check:
        val = version.get(field_name)
        if val is not None:
            if isinstance(val, (list, dict)):
                if len(val) > 0:
                    score += weight
            elif isinstance(val, str):
                if val and val not in ("unknown", "none", ""):
                    score += weight
            else:
                score += weight

    return min(score, 1.0)


def _score_freshness(version: dict[str, Any]) -> float:
    """Score freshness based on import timestamp (0.0-1.0)."""
    imported = version.get("imported_at") or version.get("source", {}).get("imported_at")
    if not imported:
        return 0.3  # Unknown gets neutral score
    # All our data was imported recently, so freshness is high
    return 0.8


def _score_adoption(version: dict[str, Any]) -> float:
    """Score community adoption (0.0-1.0)."""
    em = version.get("ecosystem_metadata", {})
    stars = em.get("stars", 0) if isinstance(em, dict) else 0
    if stars and stars > 1000:
        return 1.0
    if stars and stars > 100:
        return 0.7
    if stars and stars > 10:
        return 0.4
    return 0.2  # Unknown/minimal


def _score_dependency_clarity(version: dict[str, Any]) -> float:
    """Score how well dependencies are documented (0.0-1.0)."""
    declared = version.get("declared_dependencies", {})
    inferred = version.get("inferred_dependencies", {})

    has_declared = isinstance(declared, dict) and any(
        declared.get(k) for k in ["tools", "apis", "packages", "env_vars", "runtimes"]
    )
    has_inferred = isinstance(inferred, dict) and any(
        inferred.get(k) for k in ["tools", "apis", "packages", "env_vars", "runtimes"]
    )

    if has_declared and has_inferred:
        return 0.9
    if has_declared:
        return 0.7
    if has_inferred:
        return 0.5
    return 0.2


def _score_security_posture(version: dict[str, Any]) -> float:
    """Score security posture (0.0-1.0, higher = safer)."""
    sec = version.get("security", {})
    if not sec or not isinstance(sec, dict):
        return 0.5  # Unknown

    risk = sec.get("risk_level", "UNKNOWN")
    if risk == "LOW":
        return 0.9
    if risk == "MEDIUM":
        return 0.6
    if risk == "HIGH":
        return 0.3
    if risk == "CRITICAL":
        return 0.1

    # UNKNOWN - estimate from flags
    flags = [
        sec.get("shell_execution", False),
        sec.get("filesystem_access", False),
        sec.get("network_access", False),
        sec.get("browser_automation", False),
        sec.get("destructive_potential", False),
        sec.get("package_installation", False),
    ]
    risk_count = sum(1 for f in flags if f)
    return max(0.2, 1.0 - risk_count * 0.15)


def compute_quality(version: dict[str, Any]) -> QualityResult:
    """Compute quality scores for a version.

    Args:
        version: Version dict from registry.v3.json

    Returns:
        QualityResult with scores across all dimensions
    """
    doc = _score_documentation(version)
    meta = _score_metadata_completeness(version)
    fresh = _score_freshness(version)
    adopt = _score_adoption(version)
    dep = _score_dependency_clarity(version)
    sec = _score_security_posture(version)

    # Weighted overall
    overall = doc * 0.25 + meta * 0.20 + fresh * 0.10 + adopt * 0.10 + dep * 0.15 + sec * 0.20

    return QualityResult(
        overall_score=overall,
        documentation_score=doc,
        metadata_completeness=meta,
        freshness_score=fresh,
        adoption_score=adopt,
        dependency_clarity=dep,
        test_coverage=0.0,  # Not computable from current data
        security_posture=sec,
        dimensions={
            "documentation": doc,
            "metadata_completeness": meta,
            "freshness": fresh,
            "adoption": adopt,
            "dependency_clarity": dep,
            "security_posture": sec,
        },
    )


# --- Security Assessment ---

_SECURITY_KEYWORDS = {
    "shell_execution": [
        r"\bshell\b",
        r"\bbash\b",
        r"\bexec\b",
        r"\bsubprocess\b",
        r"\bcommand\s*(?:line|execution)\b",
        r"\brun\s+(?:a\s+)?command\b",
        r"\bterminal\b",
        r"\bcli\b",
    ],
    "filesystem_access": [
        r"\bfile\s*system\b",
        r"\bread\s+(?:a\s+)?file\b",
        r"\bwrite\s+(?:a\s+)?file\b",
        r"\bmodify\s+(?:a\s+)?file\b",
        r"\bdelete\s+(?:a\s+)?file\b",
        r"\bcreate\s+(?:a\s+)?(?:file|directory)\b",
        r"\bmkdir\b",
        r"\brm\b",
        r"\bfs\b",
        r"\bpath\b.*\bread\b",
    ],
    "network_access": [
        r"\bhttp\b",
        r"\bhttps\b",
        r"\bapi\s*(?:call|request)\b",
        r"\bfetch\b",
        r"\bcurl\b",
        r"\brequest\b",
        r"\bwebsocket\b",
        r"\bdownload\b",
        r"\bupload\b",
        r"\bnetwork\b",
    ],
    "browser_automation": [
        r"\bbrowser\b",
        r"\bplaywright\b",
        r"\bpuppeteer\b",
        r"\bselenium\b",
        r"\bscreenshot\b",
        r"\bnavigate\b.*\burl\b",
        r"\bchromium\b",
        r"\bheadless\b",
    ],
    "credential_requirements": [
        r"\bapi\s*key\b",
        r"\btoken\b",
        r"\bsecret\b",
        r"\bpassword\b",
        r"\bcredential\b",
        r"\bauth\b",
        r"\boauth\b",
        r"\bjwt\b",
    ],
    "package_installation": [
        r"\bpip\s+install\b",
        r"\bnpm\s+install\b",
        r"\bapt\s+install\b",
        r"\bbrew\s+install\b",
        r"\bcargo\s+install\b",
        r"\bgo\s+install\b",
        r"\bpackage\s+manager\b",
    ],
    "destructive_potential": [
        r"\bdelete\b",
        r"\bremove\b",
        r"\bdrop\b.*\btable\b",
        r"\btruncate\b",
        r"\bformat\b.*\bdisk\b",
        r"\bdestroy\b",
        r"\bkill\b.*\bprocess\b",
        r"\bshutdown\b",
    ],
}


@dataclass
class SecurityResult:
    risk_level: str = "UNKNOWN"
    risk_factors: list[str] = field(default_factory=list)
    shell_execution: bool = False
    filesystem_access: bool = False
    network_access: bool = False
    browser_automation: bool = False
    credential_requirements: list[str] = field(default_factory=list)
    package_installation: bool = False
    destructive_potential: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_level": self.risk_level,
            "risk_factors": self.risk_factors,
            "shell_execution": self.shell_execution,
            "filesystem_access": self.filesystem_access,
            "network_access": self.network_access,
            "browser_automation": self.browser_automation,
            "credential_requirements": self.credential_requirements,
            "package_installation": self.package_installation,
            "destructive_potential": self.destructive_potential,
        }


def assess_security(version: dict[str, Any]) -> SecurityResult:
    """Assess security risks from version content.

    Analyzes summary, long_description, and raw_content for risk indicators.
    """
    text = " ".join(
        filter(
            None,
            [
                version.get("summary", ""),
                version.get("long_description", ""),
                version.get("raw_content", ""),
            ],
        )
    )

    if not text or len(text.strip()) < 10:
        return SecurityResult()

    result = SecurityResult()
    risk_factors: list[str] = []

    for flag_name, patterns in _SECURITY_KEYWORDS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                if flag_name == "credential_requirements":
                    result.credential_requirements.append(flag_name)
                else:
                    setattr(result, flag_name, True)
                risk_factors.append(flag_name)
                break

    # Determine risk level
    risk_count = len(risk_factors)
    if result.destructive_potential or risk_count >= 4:
        result.risk_level = "HIGH"
    elif risk_count >= 2:
        result.risk_level = "MEDIUM"
    elif risk_count >= 1:
        result.risk_level = "LOW"
    else:
        result.risk_level = "LOW"

    result.risk_factors = risk_factors
    return result


# --- DB Sync ---


def sync_scoring_to_db(session: Any) -> dict[str, int]:
    """Compute and store quality, license, and security scores for all versions.

    Args:
        session: SQLAlchemy session

    Returns:
        Stats dict
    """
    from sqlalchemy import select

    from skillsbank.db.persistence_models import RepoRow, VersionRow

    stats = {
        "versions_scored": 0,
        "licenses_detected": 0,
        "quality_scores_computed": 0,
    }

    # Build repo license map
    repo_licenses: dict[str, str] = {}
    repos = session.execute(select(RepoRow)).scalars().all()
    for repo in repos:
        if repo.license:
            if isinstance(repo.license, dict):
                repo_licenses[repo.id] = repo.license.get("type", "unknown")
            elif isinstance(repo.license, str):
                repo_licenses[repo.id] = repo.license

    versions = session.execute(select(VersionRow)).scalars().all()

    for row in versions:
        version_dict = {
            "summary": row.summary,
            "long_description": row.long_description,
            "raw_content": row.raw_content,
            "name": row.name,
            "domain_primary": row.domain_primary,
            "input_format": row.input_format,
            "output_format": row.output_format,
            "capabilities": [],  # Will be populated from relationship
            "tags": [],
            "install_methods": row.install_methods or [],
            "declared_dependencies": row.declared_dependencies or {},
            "inferred_dependencies": row.inferred_dependencies or {},
            "ecosystem_metadata": row.ecosystem_metadata or {},
            "security": row.security or {},
            "quality": row.quality or {},
            "license": row.license or {},
        }

        # Get capabilities and tags from related tables
        caps = [c.name for c in row.capabilities] if hasattr(row, "capabilities") and row.capabilities else []
        tags = [t.name for t in row.tags] if hasattr(row, "tags") and row.tags else []
        version_dict["capabilities"] = caps
        version_dict["tags"] = tags

        # Compute quality
        qr = compute_quality(version_dict)
        row.quality = qr.to_dict()
        stats["quality_scores_computed"] += 1

        # Detect license
        repo_lic = repo_licenses.get(row.source_repo, "")
        lr = detect_license(
            summary=row.summary,
            ecosystem_metadata=row.ecosystem_metadata or {},
            repo_license=repo_lic,
        )
        row.license = lr.to_dict()
        if lr.detected_type != "unknown":
            stats["licenses_detected"] += 1

        # Assess security
        sr = assess_security(version_dict)
        row.security = sr.to_dict()

        stats["versions_scored"] += 1

    session.commit()
    return stats


def get_scoring_summary(session: Any) -> dict[str, Any]:
    """Get summary of scoring results."""
    from collections import Counter

    from sqlalchemy import select

    from skillsbank.db.persistence_models import VersionRow

    versions = session.execute(select(VersionRow)).scalars().all()

    quality_scores: list[float] = []
    license_types: Counter[str] = Counter()
    risk_levels: Counter[str] = Counter()

    for row in versions:
        q = row.quality or {}
        if q.get("overall_score") is not None:
            quality_scores.append(q["overall_score"])

        l = row.license or {}
        lic_type = l.get("type", "unknown")
        license_types[lic_type] += 1

        s = row.security or {}
        risk_levels[s.get("risk_level", "UNKNOWN")] += 1

    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0

    return {
        "total_versions": len(versions),
        "avg_quality_score": round(avg_quality, 3),
        "quality_distribution": {
            "excellent (0.8+)": sum(1 for s in quality_scores if s >= 0.8),
            "good (0.6-0.8)": sum(1 for s in quality_scores if 0.6 <= s < 0.8),
            "fair (0.4-0.6)": sum(1 for s in quality_scores if 0.4 <= s < 0.6),
            "poor (<0.4)": sum(1 for s in quality_scores if s < 0.4),
        },
        "license_distribution": dict(license_types.most_common()),
        "risk_distribution": dict(risk_levels.most_common()),
    }
