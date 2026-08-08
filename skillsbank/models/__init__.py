"""SkillsBank domain models (Pydantic v2)."""

from skillsbank.models.classification import (
    Capability,
    Domain,
    Tag,
)
from skillsbank.models.common import (
    MigrationMetadata,
    ProvenancedValue,
)
from skillsbank.models.compatibility import (
    CompatibilityEntry,
    CompatibilityProfile,
    InstallMethod,
)
from skillsbank.models.dependency import (
    APIRequirement,
    Dependency,
    EnvVarRequirement,
    PackageRequirement,
    RuntimeRequirement,
    ToolRequirement,
)
from skillsbank.models.enums import (
    ChangeEventType,
    CompatibilityLevel,
    DomainSource,
    LicenseStatus,
    LifecycleStatus,
    MetadataQuality,
    RelationshipType,
    RiskLevel,
    SourceType,
)
from skillsbank.models.io_shapes import (
    InputShape,
    OutputShape,
)
from skillsbank.models.quality import (
    LicenseRecord,
    QualityAssessment,
    SecurityAssessment,
)
from skillsbank.models.registry import Registry
from skillsbank.models.relationship import (
    Relationship,
    SimilarityRecord,
)
from skillsbank.models.repository import Repository, RepositorySnapshot
from skillsbank.models.skill import Skill
from skillsbank.models.skill_source import SkillSource
from skillsbank.models.skill_version import SkillVersion

__all__ = [
    "APIRequirement",
    "Capability",
    "ChangeEventType",
    # Compatibility
    "CompatibilityEntry",
    "CompatibilityLevel",
    "CompatibilityProfile",
    # Dependency
    "Dependency",
    # Classification
    "Domain",
    "DomainSource",
    "EnvVarRequirement",
    # I/O
    "InputShape",
    "InstallMethod",
    "LicenseRecord",
    "LicenseStatus",
    "LifecycleStatus",
    # Enums
    "MetadataQuality",
    "MigrationMetadata",
    "OutputShape",
    "PackageRequirement",
    # Common
    "ProvenancedValue",
    # Quality
    "QualityAssessment",
    "Registry",
    # Relationship
    "Relationship",
    "RelationshipType",
    "Repository",
    "RepositorySnapshot",
    "RiskLevel",
    "RuntimeRequirement",
    "SecurityAssessment",
    "SimilarityRecord",
    "Skill",
    # Core
    "SkillSource",
    "SkillVersion",
    "SourceType",
    "Tag",
    "ToolRequirement",
]
