# SkillsBank

A universal, ecosystem-agnostic registry of 1,000+ AI agent skills with full-text search, recommendations, duplicate detection, and quality scoring.

## What is SkillsBank?

SkillsBank indexes agent skills from 36+ GitHub repositories (Anthropic, Google, Microsoft, NVIDIA, OpenAI, and community projects) into a single SQLite database with rich metadata, normalized capabilities, and compatibility profiles for 7 agent runtimes.

**Key numbers:**

| Metric | Count |
|--------|-------|
| Skills | 1,065 |
| Repositories | 36 |
| Capabilities | 3,351 |
| Tags | 4,405 |
| Agent profiles | 7 |

## Quick Start

```bash
# Install
pip install -e .

# Import the registry (takes ~2 seconds)
skillsbank import registry.v3.json

# Search
skillsbank search "security audit"
skillsbank search "react frontend" --domain frontend --limit 5

# Get recommendations for a task
skillsbank recommend "build a secure REST API with authentication"

# Browse skills
skillsbank skills list --domain security --limit 10
skillsbank skills get <skill-id>

# Export
skillsbank export json output.json
skillsbank export csv output.csv --domain ml

# Health check
skillsbank doctor
skillsbank stats
```

## Commands

| Command | Description |
|---------|-------------|
| `search <query>` | Full-text search with BM25 ranking, facets, and filters |
| `autocomplete <prefix>` | Prefix-based skill name autocomplete |
| `recommend <task>` | AI task-based skill recommendations |
| `recommend-for <id>` | Find similar/complementary skills |
| `skills list` | Browse skills with domain/repo filters |
| `skills get <id>` | Detailed skill info with capabilities and tags |
| `repos` | List indexed repositories |
| `compose <ids...>` | Compose skills into a pipeline |
| `export <fmt> <path>` | Export to JSON, Markdown, or CSV |
| `import <path>` | Import/sync from v3 JSON |
| `dedup` | Run duplicate detection |
| `deps` | Show dependency information |
| `doctor` | Health checks (9 diagnostics) |
| `analytics` | Full registry analytics report |
| `stats` | Quick registry statistics |
| `rebuild-fts` | Rebuild full-text search index |
| `normalize` | Normalize capability taxonomy |

## Global Options

```bash
skillsbank --db custom.db search "query"   # Custom database path
skillsbank --json skills list               # JSON output
skillsbank --compact search "query"         # Compact JSON
```

## REST API

Start the API server:

```bash
uvicorn skillsbank.api:app --host 0.0.0.0 --port 8000
```

Endpoints:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/search?q=...` | Full-text search |
| GET | `/autocomplete?prefix=...` | Name autocomplete |
| GET | `/skills/{id}` | Get skill details |
| GET | `/skills` | List skills |
| GET | `/recommend?task=...` | Task recommendations |
| GET | `/recommend/{id}` | Similar skills |
| GET | `/repos` | List repositories |
| GET | `/export/json` | Export as JSON |
| GET | `/export/csv` | Export as CSV |
| GET | `/export/stats` | Export statistics |
| GET | `/search/stats` | Search index stats |
| POST | `/admin/rebuild-fts` | Rebuild search index |

## Architecture

```
skillsbank/
  models/       Pydantic v3 domain models (13 modules)
  db/           SQLAlchemy persistence, Alembic migrations, import/export
  parsers/      SKILL.md, AGENTS.md, README parsers
  taxonomy/     17 categories, 100+ canonical capabilities
  dedup/        5-dimension duplicate detection engine
  deps/         Dependency extraction + graph analysis
  scoring/      License detection, quality scoring, security assessment
  compat/       Agent compatibility profiles (Claude, Codex, OpenCode, etc.)
  sync/         Incremental sync with change tracking
  search/       FTS5 full-text search with facets
  recommender/  Task-based + similarity recommendations
  composition/  Multi-skill pipeline composition
  exports/      JSON, Markdown, CSV export
  api/          FastAPI REST API
  analytics/    Health checks + registry analytics
  perf/         LRU cache, eager loading, benchmarks
  security/     Input validation, secret detection, rate limiting
  cli.py        Click CLI (16 commands)
```

## Data Model

SkillsBank uses a 3-layer model:

1. **Skill** — stable identity (UUID5), canonical name, lifecycle status
2. **Version** — a specific imported snapshot with full metadata
3. **Repository** — source repo with sync status and snapshots

Each version carries:
- Domain classification (primary + secondary)
- Normalized capabilities with taxonomy paths
- I/O shape declarations
- Dependency graph (extracted + declared)
- Quality score (6 dimensions)
- Security assessment (7 risk flags)
- License detection with permission inference
- Agent compatibility profiles (7 agents)
- Raw content for re-parsing

## Registry Data

The `registry.v3.json` file contains the full v3 schema with all skills, versions, repositories, relationships, and similarities. Import it into SQLite for querying:

```bash
skillsbank import registry.v3.json
```

The original `registry.json` (v2 format) is preserved as an immutable reference.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -x -q --tb=short --ignore=tests/test_sqlite_roundtrip.py

# Run all tests including slow integration
pytest tests/ -x -q --tb=short

# Lint and format
ruff check skillsbank/ tests/
ruff format skillsbank/ tests/

# Build package
python -m build
```

## License

MIT License — see [LICENSE](LICENSE) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Acknowledgments

Skills indexes skills from these repositories (among others):
- [anthropics/skills](https://github.com/anthropics/skills) — Anthropic's official skills
- [mattpocock/skills](https://github.com/mattpocock/skills) — Engineering workflow skills
- [google/skills](https://github.com/google/skills) — Google's agent skills
- [microsoft/skills](https://github.com/microsoft/skills) — Microsoft's agent skills
- [nvidia/skills](https://github.com/nvidia/skills) — NVIDIA's agent skills
- [openai/skills](https://github.com/openai/skills) — OpenAI's agent skills
- [softaworks/agent-toolkit](https://github.com/softaworks/agent-toolkit) — Agent toolkit skills
- [VoltAgent/awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills) — Curated catalog
