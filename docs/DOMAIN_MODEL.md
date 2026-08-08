# SkillsBank Domain Model

**Schema version:** 3.0.0

## Overview

SkillsBank models agent skills as first-class entities with full provenance, versioning, classification, dependency tracking, and quality assessment.

## Entity Hierarchy

```
Registry
├── Skill[]          — canonical identity (stable across versions)
│   └── SkillVersion[]  — specific imported snapshot
│       └── SkillSource     — where this version came from
├── Repository[]     — source repositories
│   └── RepositorySnapshot[]  — point-in-time repo metadata
├── Relationship[]   — skill-to-skill relationships
└── SimilarityRecord[]  — computed similarity scores
```

## Core Entities

### Skill

The canonical identity of an agent skill. Independent of any specific version, name, repo, or ecosystem.

**Identity:** UUID5 derived from `https://github.com/{repo}/{skill_path}`. This ID is stable across schema migrations, name changes, and content updates.

**Fields:**
- `id` — stable UUID5 (immutable)
- `canonical_key` — human-readable key, e.g. `mattpocock/skills/code-review`
- `name` — current canonical name
- `display_name` — human-friendly display name
- `aliases` — known alternative names
- `lifecycle` — current/stale/superseded/deprecated/archived/unknown
- `is_current` — whether the skill is active
- `primary_source` — provenanced source repo
- `primary_path` — provenanced skill path
- `metadata_quality` — COMPLETE/PARTIAL/LOW_CONFIDENCE/BROKEN_EXTRACTION/UNKNOWN
- `version_count` — number of imported versions
- `current_version_id` — ID of the latest version

### SkillVersion

A specific imported snapshot of a skill. Captures the exact state at a point in time.

**Fields include all classification, I/O, dependency, compatibility, quality, security, and license data** — see `skillsbank/models/skill_version.py` for the full schema.

### SkillSource

Where a skill lives upstream.

- `repo` — repository identifier (e.g. `mattpocock/skills`)
- `owner` — repository owner
- `repo_url` — full URL
- `skill_path` — path within the repository
- `commit_sha` — git commit at import time (null if unknown)
- `content_hash` — SHA256 of file content (null if unknown)
- `branch` — git branch/tag (null if unknown)
- `source_type` — github_repo/git_repo/url/local/unknown

### Repository

A source repository containing skills.

- `id` — repository identifier
- `url` — full URL
- `owner`, `name` — parsed components
- `source_type` — type of source
- `license` — repository-level license record
- `skill_count` — number of skills found
- `snapshots` — historical metadata snapshots

## Classification

### Domain

Each skill has a domain classification with provenance:
- `primary` — ProvenancedValue with source/confidence
- `secondary` — additional domains
- `source` — declared/inferred/reviewed/corrected/unknown
- `quality` — extraction quality status

### Capability

Capabilities preserve both original and canonical forms:
- `name` — original string from source
- `canonical` — taxonomy-normalized name (null until taxonomy phase)
- `taxonomy_path` — hierarchical path (null until taxonomy phase)

### Tag

Simple categorization labels with source tracking.

## Dependencies

Split into declared vs inferred:
- `declared_dependencies` — from skill source
- `inferred_dependencies` — from content analysis
- `runtime_requirements` — aggregate: tools, APIs, packages, env vars, runtimes

## Quality & Security

### QualityAssessment

Dimension-based quality scoring:
- `metadata_completeness`, `documentation_quality`, `specificity`, `portability`, `dependency_clarity`, `maintainability`, `testability`, `extraction_confidence`
- `overall_score` — derived from dimensions

### SecurityAssessment

Descriptive risk metadata (not authorization):
- `risk_level` — LOW/MODERATE/HIGH/SPECIALIZED/UNKNOWN
- `risk_factors` — specific factors identified
- Boolean flags: shell_execution, filesystem_access, network_access, etc.

### LicenseRecord

License information with verification status:
- `license_type` — identifier (MIT, Apache-2.0, etc.)
- `status` — verified/detected/declared/unknown
- `redistributable`, `modifiable`, `commercial_restrictions`, `attribution_required`

## Provenance

### ProvenancedValue

Wraps any value with:
- `value` — the actual value
- `source` — how determined: imported, inferred, reviewed, corrected, unknown
- `confidence` — 0.0-1.0 score (null if unknown)
- `set_at` — when last set

### MigrationMetadata

Records how a record was imported:
- `imported_from` — source format
- `imported_at` — timestamp
- `original_values` — pre-normalization values
- `normalization_notes` — what changed during import
- `parser_version`, `extractor_version`

## Metadata Quality Status

| Status | Meaning |
|--------|---------|
| COMPLETE | All expected fields present and valid |
| PARTIAL | Some fields present, others missing |
| LOW_CONFIDENCE | Fields present but extraction confidence is low |
| BROKEN_EXTRACTION | Parser failed; original values preserved in migration metadata |
| UNKNOWN | Quality not assessed |

## Relationships (Future)

The `Relationship` and `SimilarityRecord` models are defined but not populated in Phase 1. They will be used in Phase 6 (duplicate detection) for:
- duplicate_of, near_duplicate_of, fork_of, inspired_by
- supersedes, superseded_by, alternative_to, complements
- depends_on, routes_to, child_of, parent_of
