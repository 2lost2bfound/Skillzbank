# Contributing to SkillsBank

Thank you for your interest in contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/2lost2bfound/Skillzbank.git
cd Skillzbank
pip install -e ".[dev]"
```

## Running Tests

```bash
# Fast tests (~2 minutes)
pytest tests/ -x -q --tb=short --ignore=tests/test_sqlite_roundtrip.py

# All tests including slow integration (~5 minutes)
pytest tests/ -x -q --tb=short
```

## Code Quality

```bash
# Lint
ruff check skillsbank/ tests/

# Format
ruff format skillsbank/ tests/

# All checks
ruff check skillsbank/ tests/ && ruff format --check skillsbank/ tests/
```

## Submitting Changes

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-change`)
3. Make your changes
4. Run tests and lint
5. Commit with a clear message
6. Push and open a Pull Request

## Adding a New Parser

To support a new skill file format:

1. Create a parser class in `skillsbank/parsers/__init__.py`
2. Implement `can_parse(content, filename)` and `parse(content, filename, source_info)`
3. Register it in `ParserRegistry`
4. Add tests in `tests/test_parsers.py`

## Adding a New Agent Profile

To add compatibility detection for a new agent:

1. Add an `AgentProfile` in `skillsbank/compat/__init__.py`
2. Add detection patterns
3. Add tests in `tests/test_compat.py`

## Code Style

- Python 3.11+ with type hints
- Pydantic v2 for data models
- SQLAlchemy 2.x for persistence
- Click for CLI
- FastAPI for API
- pytest for tests

## Reporting Issues

Use the [GitHub issue tracker](https://github.com/2lost2bfound/Skillzbank/issues) to report bugs or request features.
