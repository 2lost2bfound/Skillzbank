# SkillsBank v1.0.0 — Agent Skill Intelligence Layer

**Release date:** 2026-08-08  
**Tag:** `v1.0.0`  
**License:** MIT

## What it is

SkillsBank is a **local-first, ecosystem-neutral intelligence layer** for AI agent skills. It normalizes skills from many GitHub sources into a SQLite registry you can search, compare, score, recommend, compose, and export — through a Click CLI and a FastAPI REST API.

It is not a place to *write* skills. It is the **index** for skills that already exist.

## v1.0.0 registry snapshot

Verified from the shipped `registry.v3.json` / imported database:

| Metric | Count |
|-------:|------:|
| Skills | 1,065 |
| Versions | 1,065 |
| Repositories | 36 |
| Capabilities | 3,351 |
| Tags | 4,405 |
| Agent compatibility profiles | 7 |

Re-run `skillsbank stats` after importing additional sources — snapshot numbers will change.

## Major capabilities

- **Search** — SQLite FTS5 + BM25, facets, filters, autocomplete
- **Recommend** — multi-signal ranking for natural-language tasks
- **Compose** — multi-skill workflows with conflict detection
- **Taxonomy** — 17 categories, 100+ canonical capabilities
- **Dedup** — exact / near / functional overlap / related
- **Dependencies** — packages, APIs, CLI tools, runtimes, env vars
- **Compatibility** — Claude, Codex, OpenCode, Gemini, Cursor, MCP client, generic CLI
- **Scoring** — quality dimensions, license patterns, security risk flags
- **Sync** — content hashes, changelog, version preservation
- **Export** — JSON (registry schema v3), Markdown, CSV
- **Doctor / analytics** — health checks and coverage reports

### SEARCH · RECOMMEND · COMPOSE

| Operation | Question |
|-----------|----------|
| Search | I roughly know the capability — find skills |
| Recommend | I know the task — rank fitting skills |
| Compose | I have skill IDs — build an ordered workflow |

See the README demo asset: `docs/assets/skillsbank-demo.svg`.

## Local-first architecture

Core operations do not require a hosted DB, vector DB, LLM API, embeddings API, or SaaS search provider. Stack:

- Python 3.11+
- **Pydantic v2** domain models
- **Registry schema v3** JSON format (`registry.v3.json`)
- SQLAlchemy 2.x + SQLite + Alembic
- FTS5 / BM25
- Click + FastAPI / Uvicorn

## Interfaces

- **CLI:** 16 top-level commands (`search`, `recommend`, `compose`, `import`, `doctor`, …)
- **API:** 13 application routes under a local Uvicorn process
- **Package:** `pip install .` from this repository (not on PyPI yet)

## Testing and release audit

| Suite | Count |
|-------|------:|
| Standard tests | 462 |
| Slow SQLite round-trip | 16 |
| Collected total | 478 |

A 25-part release audit fixed fresh-DB init, idempotent import, build backend, version metadata, and packaging of Alembic migrations. Details: [`RELEASE_AUDIT_V1.0.0.md`](RELEASE_AUDIT_V1.0.0.md).

## Install

```bash
git clone https://github.com/2lost2bfound/Skillzbank.git
cd Skillzbank
python3 -m venv .venv && source .venv/bin/activate
pip install .
skillsbank import registry.v3.json
skillsbank doctor
skillsbank search "security audit"
```

Or install the release wheel from GitHub Releases, then import `registry.v3.json` from the source tree (registry data ships in the repository).

## Known limitations

- Not published to PyPI in v1.0.0
- Recommendation quality depends on taxonomy coverage and keyword signals (no embeddings required, and none used by default)
- Compatibility scores are advisory, not runtime proof
- Many upstream skills lack structured dependency/license metadata; inference is best-effort
- Security scoring flags patterns; it is not a substitute for human review or formal audit
- Incremental upstream GitHub sync is implemented as change-tracking primitives — bulk re-crawl of the open web is out of scope for this release

## Contributing

See [`../CONTRIBUTING.md`](../CONTRIBUTING.md). Good first work: new source repos, parser fixes, taxonomy corrections, dependency patterns, docs.

## Links

- Repository: https://github.com/2lost2bfound/Skillzbank
- README: https://github.com/2lost2bfound/Skillzbank#readme
- Security policy: [`../SECURITY.md`](../SECURITY.md)
