"""Tests for SkillsBank CLI (skillsbank/cli.py)."""

from __future__ import annotations

import json
import os

import pytest
from click.testing import CliRunner
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from skillsbank.db.base import Base
from skillsbank.db.persistence_models import (
    CapabilityRow,
    RepoRow,
    SkillRow,
    TagRow,
    VersionRow,
)

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary SQLite DB with test data."""
    path = str(tmp_path / "test.db")
    engine = create_engine(f"sqlite:///{path}")

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()

    # Insert test repo
    session.add(
        RepoRow(
            id="test-org/test-repo",
            url="https://github.com/test-org/test-repo",
            owner="test-org",
            name="test-repo",
            skill_count=2,
        )
    )

    # Insert test skills
    for i, (name, domain) in enumerate(
        [
            ("security-audit", "security"),
            ("frontend-design", "frontend"),
        ]
    ):
        skill = SkillRow(
            id=f"skill-{i:04d}",
            canonical_key=name,
            name=name,
            display_name=name.replace("-", " ").title(),
            lifecycle="active",
            is_current=True,
            primary_source="test-org/test-repo",
            version_count=1,
        )
        session.add(skill)
        session.flush()

        version = VersionRow(
            skill_id=skill.id,
            version_id=f"v-{i:04d}",
            source_repo="test-org/test-repo",
            source_path=f"skills/{name}/SKILL.md",
            name=name,
            summary=f"Test skill for {domain}",
            domain_primary=domain,
            quality={"overall_score": 0.75},
            security={"risk_level": "LOW"},
        )
        session.add(version)
        session.flush()

        session.add(CapabilityRow(version_id_fk=version.id, name=f"{domain}_cap", canonical=f"{domain}_cap"))
        session.add(TagRow(version_id_fk=version.id, name=domain, source="parser"))

    session.commit()
    session.close()
    engine.dispose()
    return path


@pytest.fixture
def runner():
    """Click CliRunner."""
    return CliRunner()


@pytest.fixture
def cli_app():
    """Import CLI app fresh."""
    from skillsbank.cli import cli

    return cli


# ── Tests ─────────────────────────────────────────────────────────────


class TestCLI:
    def test_help(self, runner, cli_app):
        result = runner.invoke(cli_app, ["--help"])
        assert result.exit_code == 0
        assert "SkillsBank" in result.output

    def test_stats(self, runner, cli_app, db_path):
        result = runner.invoke(cli_app, ["--db", db_path, "stats"])
        assert result.exit_code == 0
        assert "Skills" in result.output
        assert "2" in result.output

    def test_stats_json(self, runner, cli_app, db_path):
        result = runner.invoke(cli_app, ["--db", db_path, "--json", "stats"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["skills"] == 2
        assert data["repos"] == 1

    def test_skills_list(self, runner, cli_app, db_path):
        result = runner.invoke(cli_app, ["--db", db_path, "skills", "list"])
        assert result.exit_code == 0
        assert "security-audit" in result.output

    def test_skills_list_json(self, runner, cli_app, db_path):
        result = runner.invoke(cli_app, ["--db", db_path, "--json", "skills", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total"] == 2

    def test_skills_get(self, runner, cli_app, db_path):
        result = runner.invoke(cli_app, ["--db", db_path, "skills", "get", "skill-0000"])
        assert result.exit_code == 0
        assert "security-audit" in result.output

    def test_skills_get_not_found(self, runner, cli_app, db_path):
        result = runner.invoke(cli_app, ["--db", db_path, "skills", "get", "nonexistent"])
        assert result.exit_code == 1

    def test_repos(self, runner, cli_app, db_path):
        result = runner.invoke(cli_app, ["--db", db_path, "repos"])
        assert result.exit_code == 0
        assert "test-org" in result.output

    def test_repos_json(self, runner, cli_app, db_path):
        result = runner.invoke(cli_app, ["--db", db_path, "--json", "repos"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["owner"] == "test-org"

    def test_doctor(self, runner, cli_app, db_path):
        result = runner.invoke(cli_app, ["--db", db_path, "doctor"])
        assert result.exit_code == 0
        assert "Health Check" in result.output

    def test_doctor_json(self, runner, cli_app, db_path):
        result = runner.invoke(cli_app, ["--db", db_path, "--json", "doctor"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "healthy" in data
        assert "checks" in data

    def test_search(self, runner, cli_app, db_path):
        # Build FTS index first
        from skillsbank.db.engine import create_engine_from_url
        from skillsbank.search import rebuild_fts_index

        engine = create_engine_from_url(f"sqlite:///{db_path}")
        from sqlalchemy.orm import sessionmaker

        session = sessionmaker(bind=engine)()
        rebuild_fts_index(session)
        session.close()

        result = runner.invoke(cli_app, ["--db", db_path, "search", "security"])
        assert result.exit_code == 0
        assert "Found" in result.output

    def test_search_json(self, runner, cli_app, db_path):
        from sqlalchemy.orm import sessionmaker as sm

        from skillsbank.db.engine import create_engine_from_url
        from skillsbank.search import rebuild_fts_index

        engine = create_engine_from_url(f"sqlite:///{db_path}")
        session = sm(bind=engine)()
        rebuild_fts_index(session)
        session.close()

        result = runner.invoke(cli_app, ["--db", db_path, "--json", "search", "security"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "total" in data
        assert "results" in data

    def test_rebuild_fts(self, runner, cli_app, db_path):
        result = runner.invoke(cli_app, ["--db", db_path, "rebuild-fts"])
        assert result.exit_code == 0
        assert "rebuilt" in result.output.lower()

    def test_normalize(self, runner, cli_app, db_path):
        result = runner.invoke(cli_app, ["--db", db_path, "normalize"])
        assert result.exit_code == 0

    def test_deps(self, runner, cli_app, db_path):
        result = runner.invoke(cli_app, ["--db", db_path, "deps"])
        assert result.exit_code == 0

    def test_deps_skill(self, runner, cli_app, db_path):
        result = runner.invoke(cli_app, ["--db", db_path, "deps", "--skill-id", "skill-0000"])
        assert result.exit_code == 0

    def test_deps_skill_not_found(self, runner, cli_app, db_path):
        result = runner.invoke(cli_app, ["--db", db_path, "deps", "--skill-id", "nonexistent"])
        assert result.exit_code == 1

    def test_export_json(self, runner, cli_app, db_path, tmp_path):
        out = str(tmp_path / "out.json")
        result = runner.invoke(cli_app, ["--db", db_path, "export", "json", out])
        assert result.exit_code == 0
        assert os.path.exists(out)
        with open(out) as f:
            data = json.load(f)
        assert "skills" in data
        assert data["total_skills"] >= 1

    def test_export_csv(self, runner, cli_app, db_path, tmp_path):
        out = str(tmp_path / "out.csv")
        result = runner.invoke(cli_app, ["--db", db_path, "export", "csv", out])
        assert result.exit_code == 0
        assert os.path.exists(out)

    def test_export_markdown(self, runner, cli_app, db_path, tmp_path):
        out = str(tmp_path / "out.md")
        result = runner.invoke(cli_app, ["--db", db_path, "export", "markdown", out])
        assert result.exit_code == 0
        assert os.path.exists(out)
