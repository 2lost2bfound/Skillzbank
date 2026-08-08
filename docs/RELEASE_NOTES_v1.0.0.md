# SkillsBank v1.0.0 Release Notes

**Release Date:** August 8, 2025

## Overview

SkillsBank v1.0.0 is the first stable release of a universal, ecosystem-agnostic registry of 1,000+ AI agent skills. It provides full-text search, recommendations, duplicate detection, quality scoring, and compatibility analysis across 36 repositories and 7 agent runtimes.

## What's Included

### Registry Data
- **1,065 skills** from 36 GitHub repositories
- Sources: Anthropic, Google, Microsoft, NVIDIA, OpenAI, mattpocock, softaworks, and 28 community repos
- 3,351 normalized capabilities across 17 categories
- 4,405 tags
- 7 agent compatibility profiles (Claude, Codex, OpenCode, Gemini, Cursor, MCP client, generic CLI)

### Core Features

**Search & Discovery**
- FTS5 full-text search with BM25 ranking
- Faceted filtering by domain, category, repository, quality, risk level
- Prefix-based autocomplete
- Task-based skill recommendations

**Quality & Security**
- 6-dimension quality scoring (documentation, metadata, freshness, adoption, dependency clarity, security posture)
- 7-flag security assessment (shell, filesystem, network, browser, credentials, packages, destructive)
- License detection with permission inference (20+ patterns)

**Analysis**
- 5-dimension duplicate detection (name, summary, capabilities, content, source)
- Dependency extraction and graph analysis
- Agent compatibility profiling
- Capability taxonomy normalization

**Composition & Export**
- Multi-skill pipeline composition with conflict detection
- Export to JSON (v3-compatible), Markdown, or CSV
- Incremental sync with change tracking

**Interfaces**
- Click CLI with 16 commands
- FastAPI REST API with 13 endpoints
- SQLite database with Alembic migrations

### Technical Details

- **Python:** 3.11+
- **Dependencies:** SQLAlchemy 2.x, Pydantic v2, Click, FastAPI, uvicorn
- **Database:** SQLite with WAL mode, FTS5, composite indexes
- **Tests:** 462 tests across 18 test files
- **License:** MIT

## Installation

```bash
pip install skillsbank
```

Or from source:

```bash
git clone https://github.com/2lost2bfound/Skillzbank.git
cd Skillzbank
pip install -e .
skillsbank import registry.v3.json
```

## Quick Start

```bash
# Search for security skills
skillsbank search "security audit"

# Get recommendations for a task
skillsbank recommend "build a REST API with authentication"

# Browse by domain
skillsbank skills list --domain ml --limit 10

# Export
skillsbank export json skills.json

# Health check
skillsbank doctor
```

## Breaking Changes

None (first release).

## Known Limitations

- Registry data is a point-in-time snapshot; no automatic GitHub syncing yet
- Quality scores depend on content available in SKILL.md files
- Some community repos may have incomplete metadata

## What's Next

- Automatic registry syncing from GitHub
- Web UI for browsing and comparing skills
- Plugin system for custom parsers and scorers
- Skill versioning and update notifications
