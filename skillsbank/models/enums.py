"""Enumerations for SkillsBank domain models."""

from enum import Enum


class MetadataQuality(str, Enum):
    """Quality status for extracted metadata fields."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    BROKEN_EXTRACTION = "BROKEN_EXTRACTION"
    UNKNOWN = "UNKNOWN"


class DomainSource(str, Enum):
    """How a domain classification was determined."""

    DECLARED = "declared"
    INFERRED = "inferred"
    REVIEWED = "reviewed"
    CORRECTED = "corrected"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    """Security risk classification."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    SPECIALIZED = "SPECIALIZED"
    UNKNOWN = "UNKNOWN"


class CompatibilityLevel(str, Enum):
    """Compatibility status with an agent/ecosystem."""

    SUPPORTED = "SUPPORTED"
    LIKELY_SUPPORTED = "LIKELY_SUPPORTED"
    REQUIRES_ADAPTER = "REQUIRES_ADAPTER"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    UNKNOWN = "UNKNOWN"


class LifecycleStatus(str, Enum):
    """Skill lifecycle state."""

    CURRENT = "current"
    STALE = "stale"
    SUPERSEDED = "superseded"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"
    UNKNOWN = "unknown"


class RelationshipType(str, Enum):
    """Type of relationship between skills."""

    DUPLICATE_OF = "duplicate_of"
    NEAR_DUPLICATE_OF = "near_duplicate_of"
    FORK_OF = "fork_of"
    INSPIRED_BY = "inspired_by"
    SUPERSEDES = "supersedes"
    SUPERSEDED_BY = "superseded_by"
    ALTERNATIVE_TO = "alternative_to"
    COMPLEMENTS = "complements"
    DEPENDS_ON = "depends_on"
    ROUTES_TO = "routes_to"
    CHILD_OF = "child_of"
    PARENT_OF = "parent_of"


class SourceType(str, Enum):
    """Type of skill source."""

    GITHUB_REPO = "github_repo"
    GIT_REPO = "git_repo"
    URL = "url"
    LOCAL = "local"
    UNKNOWN = "unknown"


class ChangeEventType(str, Enum):
    """Type of change detected during sync."""

    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    REMOVED = "REMOVED"
    MOVED = "MOVED"
    RENAMED = "RENAMED"
    RESTORED = "RESTORED"


class LicenseStatus(str, Enum):
    """License determination status."""

    VERIFIED = "verified"
    DETECTED = "detected"
    DECLARED = "declared"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"
