# Architecture

## Overview

SkillsBank is a layered system with clear separation between domain models, persistence, and application logic.

```
┌─────────────────────────────────────────────────────┐
│                   CLI / API / Exports                 │
├─────────────────────────────────────────────────────┤
│  Search  │  Recommend  │  Dedup  │  Sync  │ Compose  │
├─────────────────────────────────────────────────────┤
│  Scoring │  Compat    │  Deps   │ Taxonomy│ Parsers  │
├─────────────────────────────────────────────────────┤
│              Domain Models (Pydantic v2)              │
├─────────────────────────────────────────────────────┤
│           SQLAlchemy 2.x + SQLite + FTS5             │
└─────────────────────────────────────────────────────┘
```

## Layers

### 1. Domain Models (`skillsbank/models/`)

Pure Pydantic v2 models with no persistence logic. 13 files:

| Model | Purpose |
|-------|---------|
| `enums.py` | 9 enumerations (MetadataQuality, DomainSource, RiskLevel, etc.) |
| `common.py` | ProvenancedValue (value + source + confidence), MigrationMetadata |
| `classification.py` | Domain, Capability, Tag |
| `dependency.py` | Dependency, RuntimeRequirement (tools, APIs, packages, env vars) |
| `io_shapes.py` | InputShape, OutputShape |
| `compatibility.py` | CompatibilityEntry, CompatibilityProfile, InstallMethod |
| `quality.py` | QualityAssessment (6 dimensions), SecurityAssessment, LicenseRecord |
| `relationship.py` | Relationship, SimilarityRecord |
| `skill_source.py` | SkillSource (repo, path, commit, content hash) |
| `skill_version.py` | SkillVersion (full imported version) |
| `skill.py` | Skill (canonical identity) |
| `repository.py` | Repository, RepositorySnapshot |
| `registry.py` | Registry (top-level container) |

### 2. Persistence (`skillsbank/db/`)

SQLAlchemy 2.x ORM with 9 tables:

```
skills ──1:N── versions ──1:N── capabilities
   │              │
   │              └──1:N── tags
   │
   ├──N:N── repositories (via versions.source_repo)
   │
   └──N:N── relationships/similarities (self-referential)
```

Key design decisions:
- Domain models separate from persistence models
- Relational for core searchable data, JSON for optional metadata
- UUID5 skill IDs (stable across re-imports)
- `render_as_batch=True` for SQLite ALTER TABLE support
- FTS5 virtual tables for full-text search (not contentless)
- Composite indexes for common query patterns

### 3. Parsers (`skillsbank/parsers/`)

Plugin system with auto-detection:

| Parser | Format | Signals |
|--------|--------|---------|
| `SKILLMdParser` | SKILL.md | Title, sections, domain keywords, trigger patterns |
| `AGENTSmdParser` | AGENTS.md | Workflow steps, rules, agent signals |
| `ReadmeParser` | README.md | Features sections, install blocks, badges |

`ParserRegistry.parse()` tries each parser's `can_parse()` method and returns structured results.

### 4. Feature Modules

Each module is self-contained with its own tests:

#### Taxonomy (`skillsbank/taxonomy/`)
- 17 categories, 100+ canonical capabilities, 200+ aliases
- `classify_capability()` with fuzzy substring matching
- `normalize_capabilities()` for deduplication

#### Dedup (`skillsbank/deps/`)
- 5 signal scorers: name (0.30), summary (0.20), capabilities (0.35), content (0.10), source (0.05)
- Content-hash exact match override (≥0.99)
- Classifications: EXACT_DUPLICATE, NEAR_DUPLICATE, FUNCTIONAL_OVERLAP, RELATED

#### Dependencies (`skillsbank/deps/`)
- Regex extraction: pip, npm, apt, brew, cargo, go, gem
- 30+ API key patterns, 40+ CLI tool patterns
- Tarjan's cycle detection, conflict detection

#### Scoring (`skillsbank/scoring/`)
- License detection: 20+ patterns with permission inference
- Quality: 6 dimensions (documentation, metadata, freshness, adoption, deps, security)
- Security: 7 risk flags with severity levels

#### Compatibility (`skillsbank/compat/`)
- 7 agent profiles: claude, codex, opencode, gemini, cursor, mcp_client, generic_cli
- Pattern-based assessment with weighted signals
- SUPPORTED / LIKELY_SUPPORTED / REQUIRES_ADAPTER classification

#### Sync (`skillsbank/sync/`)
- Content-hash based change detection
- Soft-delete (archive) for removed skills
- Full changelog with sync_id grouping

#### Search (`skillsbank/search/`)
- 3 FTS5 tables: skills, capabilities, tags
- BM25 ranking with faceted filtering
- Query builder handles bare words, quoted phrases, boolean operators

#### Recommender (`skillsbank/recommender/`)
- 6 signal sources: task-match, similar, category, ecosystem, popular, high-quality
- 20 task categories with keyword extraction
- Weighted scoring with deduplication

#### Composition (`skillsbank/composition/`)
- 4 strategies: sequential, parallel, pipeline, conditional
- Conflict detection: capability overlap, dependency conflicts
- Topological sort for dependency ordering

### 5. Application Layer

#### CLI (`skillsbank/cli.py`)
18 Click commands with `--db`, `--json`, `--compact` global options.

#### API (`skillsbank/api/`)
FastAPI with 13 endpoints. Uses module-level engine/session pattern with `_init_engine()`.

#### Exports (`skillsbank/exports/`)
JSON (v3-compatible), Markdown (grouped by domain), CSV with filtering.

### 6. Cross-Cutting

#### Performance (`skillsbank/perf/`)
- LRU cache with TTL
- Eager-loading queries
- SQLite pragmas (WAL, cache_size, mmap)
- Benchmark suite

#### Security (`skillsbank/security/`)
- Input validation (identifiers, queries, paths)
- SQL injection prevention
- Secret detection
- Rate limiting
- Safe error responses

#### Analytics (`skillsbank/analytics/`)
- 9 health checks
- 12 analytics functions
- Coverage reports, gap analysis, quality distribution

## Data Flow

### Import Pipeline
```
registry.v3.json → import_v3_to_sqlite() → SQLite tables
                                            ↓
                              FTS5 index rebuild
                              Taxonomy normalization
                              Dependency extraction
                              Quality/security scoring
                              Compatibility assessment
                              Duplicate detection
```

### Query Pipeline
```
User query → CLI/API → Search/Recommend/Dedup module
                         ↓
                    SQLite + FTS5
                         ↓
                    Filter + Rank + Format
                         ↓
                    JSON/Markdown/CSV output
```

### Sync Pipeline
```
New v3.json → detect_changes() → ChangeRecords
                                    ↓
                            apply_sync() → INSERT (new)
                                         → UPDATE (modified)
                                         → ARCHIVE (removed)
                                         → changelog table
```

## Database Schema

9 tables with FK constraints and cascade deletes:

```sql
skills (id PK, canonical_key, name, lifecycle, ...)
  └── versions (id PK, skill_id FK, version_id, ...)
        ├── capabilities (id PK, version_id_fk FK, name, canonical, ...)
        └── tags (id PK, version_id_fk FK, name, source, ...)

repositories (id PK, url, owner, name, ...)
  └── repo_snapshots (id PK, repo_id FK, commit_sha, ...)

relationships (id PK, source_id FK, target_id FK, rel_type, ...)
similarities (id PK, skill_a_id FK, skill_b_id FK, overall_score, ...)
```

Composite indexes:
- `ix_versions_domain_repo` on (domain_primary, source_repo)
- `ix_versions_skill_version` on (skill_id, version_id)
- `ix_capabilities_version_name` on (version_id_fk, name)
- `ix_tags_version_name` on (version_id_fk, name)

FTS5 tables:
- `fts_skills` — name, summary, domain, repo
- `fts_capabilities` — capability_name, canonical_name, taxonomy_path
- `fts_tags` — tag_name

## Testing Strategy

Each module has its own test file:

| Test File | Tests | Coverage |
|-----------|-------|----------|
| test_v2_import.py | 19 | v2→v3 migration |
| test_sqlite_roundtrip.py | 16 | DB import/export lossless round-trip |
| test_parsers.py | 26 | All 3 parsers + registry |
| test_taxonomy.py | 20 | Classification + normalization |
| test_dedup.py | 25 | Fingerprinting + comparison |
| test_deps.py | 44 | Extraction + graph + cycle detection |
| test_scoring.py | 27 | License + quality + security |
| test_compat.py | 35 | Agent compatibility assessment |
| test_sync.py | 26 | Change detection + apply |
| test_search.py | 41 | FTS5 search + facets + autocomplete |
| test_recommender.py | 28 | Task-based recommendations |
| test_composition.py | 28 | Skill composition + conflicts |
| test_exports.py | 13 | JSON/Markdown/CSV export |
| test_api.py | 23 | FastAPI endpoints |
| test_cli.py | 21 | CLI commands |
| test_analytics.py | 26 | Health checks + analytics |
| test_perf.py | 24 | Cache + benchmarks |
| test_security.py | 36 | Validation + sanitization + rate limiting |
| **Total** | **~478** | |

All tests use in-memory SQLite for isolation and speed.
