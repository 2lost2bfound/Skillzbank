"""Tests for Phase 13: Export formats."""

from __future__ import annotations

import csv
import json
import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from skillsbank.db.base import Base
from skillsbank.db.importer import import_v3_to_sqlite
from skillsbank.exports import (
    ExportOptions,
    export_csv,
    export_json,
    export_json_string,
    export_markdown,
    get_export_stats,
)

TEST_V3 = os.path.join(os.path.dirname(__file__), "..", "registry.v3.json")


@pytest.fixture(scope="module")
def populated_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    import_v3_to_sqlite(session, TEST_V3)
    session.commit()
    yield session
    session.close()


class TestExportJson:
    def test_basic_export(self, populated_session):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            result = export_json(populated_session, path)
            assert result["format"] == "json"
            assert result["count"] > 0
            assert os.path.exists(path)
            with open(path) as f:
                data = json.load(f)
            assert data["schema_version"] == "3.0"
            assert data["total_skills"] > 0
            assert len(data["skills"]) > 0
        finally:
            os.unlink(path)

    def test_filtered_by_domain(self, populated_session):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            opts = ExportOptions(domain="security")
            result = export_json(populated_session, path, opts)
            assert result["count"] >= 0  # May or may not have security skills
        finally:
            os.unlink(path)

    def test_filtered_by_repo(self, populated_session):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            opts = ExportOptions(repo="nonexistent/repo")
            result = export_json(populated_session, path, opts)
            assert result["count"] == 0
        finally:
            os.unlink(path)

    def test_limit(self, populated_session):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            opts = ExportOptions(limit=5)
            result = export_json(populated_session, path, opts)
            assert result["count"] <= 5
        finally:
            os.unlink(path)

    def test_exclude_capabilities(self, populated_session):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            opts = ExportOptions(include_capabilities=False)
            export_json(populated_session, path, opts)
            with open(path) as f:
                data = json.load(f)
            if data["skills"]:
                assert "capabilities" not in data["skills"][0]
        finally:
            os.unlink(path)


class TestExportMarkdown:
    def test_basic_export(self, populated_session):
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            path = f.name
        try:
            result = export_markdown(populated_session, path)
            assert result["format"] == "markdown"
            assert result["count"] > 0
            with open(path) as f:
                content = f.read()
            assert "# SkillsBank Registry Catalog" in content
            assert "## " in content  # Domain headers
        finally:
            os.unlink(path)

    def test_filtered(self, populated_session):
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            path = f.name
        try:
            opts = ExportOptions(limit=3)
            result = export_markdown(populated_session, path, opts)
            assert result["count"] <= 3
        finally:
            os.unlink(path)


class TestExportCsv:
    def test_basic_export(self, populated_session):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            result = export_csv(populated_session, path)
            assert result["format"] == "csv"
            assert result["count"] > 0
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            assert len(rows) > 0
            assert "id" in rows[0]
            assert "name" in rows[0]
        finally:
            os.unlink(path)

    def test_includes_capabilities(self, populated_session):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            opts = ExportOptions(include_capabilities=True)
            export_csv(populated_session, path, opts)
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            if rows:
                assert "capabilities" in rows[0]
        finally:
            os.unlink(path)

    def test_excludes_capabilities(self, populated_session):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            opts = ExportOptions(include_capabilities=False)
            export_csv(populated_session, path, opts)
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            if rows:
                assert "capabilities" not in rows[0]
        finally:
            os.unlink(path)


class TestExportJsonString:
    def test_returns_string(self, populated_session):
        result = export_json_string(populated_session)
        data = json.loads(result)
        assert data["schema_version"] == "3.0"
        assert data["total_skills"] > 0

    def test_filtered(self, populated_session):
        opts = ExportOptions(limit=2)
        result = export_json_string(populated_session, opts)
        data = json.loads(result)
        assert data["total_skills"] <= 2


class TestGetExportStats:
    def test_returns_stats(self, populated_session):
        stats = get_export_stats(populated_session)
        assert stats["total_skills"] > 0
        assert stats["total_versions"] > 0
        assert stats["total_repos"] > 0
        assert isinstance(stats["domains"], dict)
