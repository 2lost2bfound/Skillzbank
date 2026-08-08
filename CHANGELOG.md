# Changelog

## [1.0.0] - 2025-08-08

### Added

- SQLite persistence with SQLAlchemy 2.x and Alembic migrations
- Pydantic v2 domain models (13 modules: enums, common, classification, dependency, io_shapes, compatibility, quality, relationship, skill_source, skill_version, skill, repository, registry)
- v2 backward importer with provenance tracking and idempotent re-import
- SKILL.md, AGENTS.md, README parser plugins
- Capability taxonomy: 17 categories, 100+ canonical capabilities, fuzzy matching
- Duplicate detection engine: 5-dimension scoring (name, summary, capabilities, content, source)
- Dependency extraction: packages, APIs, CLI tools, runtimes, env vars
- License detection with permission inference (20+ license patterns)
- Quality scoring: 6 dimensions (documentation, metadata, freshness, adoption, dependency clarity, security posture)
- Security assessment: 7 risk flags (shell, filesystem, network, browser, credentials, packages, destructive)
- Agent compatibility profiles: Claude, Codex, OpenCode, Gemini, Cursor, MCP client, generic CLI
- Incremental sync with change tracking and changelog
- FTS5 full-text search with BM25 ranking, facets, and autocomplete
- Task-based recommendation engine (20 task categories)
- Skill composition: sequential, parallel, pipeline strategies with conflict detection
- Export formats: JSON (v3-compatible), Markdown, CSV
- FastAPI REST API with 13 application routes
- Click CLI with 16 top-level commands
- Health diagnostics (9 checks) and analytics (12 functions)
- LRU cache, eager loading, composite indexes, SQLite pragmas
- Input validation, secret detection, rate limiting, safe error handling
- GitHub Actions CI (lint, test, integration, build)
- 462 standard tests + 16 slow SQLite round-trip tests (478 collected)

### Registry Data

- 1,065 skills from 36 repositories
- 3,351 normalized capabilities across 17 categories
- 4,405 tags
- 7 agent compatibility profiles
- Sources: Anthropic, Google, Microsoft, NVIDIA, OpenAI, mattpocock, softaworks, and 28 community repos
