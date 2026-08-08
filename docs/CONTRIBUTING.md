# Contributing

## Development Setup

```bash
# Clone
git clone <repo-url>
cd "skill indexer"

# Install in dev mode
pip install -e ".[dev]"

# Run tests
pytest tests/ -x -q
```

## Project Structure

```
skillsbank/
├── models/          # Pydantic v2 domain models
├── db/              # SQLAlchemy persistence
├── parsers/         # SKILL.md/AGENTS.md/README parsers
├── taxonomy/        # Capability classification
├── dedup/           # Duplicate detection
├── deps/            # Dependency extraction
├── scoring/         # Quality/security/license scoring
├── compat/          # Agent compatibility
├── sync/            # Incremental sync
├── search/          # FTS5 search
├── recommender/     # Recommendations
├── composition/     # Skill composition
├── exports/         # JSON/Markdown/CSV export
├── api/             # FastAPI REST API
├── analytics/       # Health checks + analytics
├── perf/            # Performance optimization
├── security/        # Input validation + sanitization
└── cli.py           # Click CLI
tests/               # 462 standard + 16 slow/integration (478 collected)
docs/                # Documentation
```

## Adding a New Parser

1. Create parser class in `skillsbank/parsers/__init__.py`
2. Implement `can_parse(content, filename)` and `parse(content, filename)` methods
3. Register in `ParserRegistry._parsers` list
4. Add tests in `tests/test_parsers.py`

## Adding a New Feature Module

1. Create `skillsbank/newmodule/__init__.py`
2. Implement pure functions (no global state)
3. Add DB sync function if needed (in `skillsbank/db/`)
4. Add CLI command in `skillsbank/cli.py`
5. Add API endpoint in `skillsbank/api/__init__.py`
6. Write tests in `tests/test_newmodule.py`
7. Update this doc

## Testing

- All tests use in-memory SQLite for isolation
- Each test file is self-contained with its own fixtures
- Run `pytest tests/ -x -q` for all tests
- Run `pytest tests/test_specific.py -v` for specific module

## Code Style

- Python 3.10+ (uses `match` statements, `type | None` syntax)
- Pydantic v2 for domain models
- SQLAlchemy 2.x for persistence
- Type hints on all public functions
- Docstrings on module-level functions
