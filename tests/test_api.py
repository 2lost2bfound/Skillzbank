"""Tests for Phase 14: REST API."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from skillsbank.api import app
from skillsbank.db.base import Base
from skillsbank.db.importer import import_v3_to_sqlite
from skillsbank.search import rebuild_fts_index

TEST_V3 = os.path.join(os.path.dirname(__file__), "..", "registry.v3.json")


@pytest.fixture(scope="module")
def client():
    """Test client with populated in-memory DB."""
    import skillsbank.api as api_module

    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine)
    session = TestSession()
    import_v3_to_sqlite(session, TEST_V3)
    rebuild_fts_index(session)
    session.commit()
    session.close()

    # Override module-level engine/SessionLocal/DB_PATH
    api_module.engine = test_engine
    api_module.SessionLocal = TestSession
    api_module.DB_PATH = ":memory:"

    with TestClient(app) as c:
        yield c

    api_module.engine = None
    api_module.SessionLocal = None


class TestHealth:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["total_skills"] > 0
        assert data["total_repos"] > 0


class TestSearch:
    def test_basic_search(self, client):
        r = client.get("/search", params={"q": "security"})
        assert r.status_code == 200
        data = r.json()
        assert data["query"] == "security"
        assert data["total"] >= 0
        assert isinstance(data["results"], list)

    def test_search_with_domain_filter(self, client):
        r = client.get("/search", params={"q": "code", "domain": "security"})
        assert r.status_code == 200

    def test_search_with_limit(self, client):
        r = client.get("/search", params={"q": "test", "limit": 3})
        assert r.status_code == 200
        data = r.json()
        assert len(data["results"]) <= 3

    def test_search_with_facets(self, client):
        r = client.get("/search", params={"q": "api", "facets": True})
        assert r.status_code == 200
        data = r.json()
        assert "facets" in data

    def test_search_no_results(self, client):
        r = client.get("/search", params={"q": "xyznonexistent"})
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0


class TestAutocomplete:
    def test_autocomplete(self, client):
        r = client.get("/autocomplete", params={"prefix": "code", "limit": 5})
        assert r.status_code == 200
        data = r.json()
        assert data["prefix"] == "code"
        assert isinstance(data["results"], list)

    def test_autocomplete_empty(self, client):
        r = client.get("/autocomplete", params={"prefix": "xyznonexistent"})
        assert r.status_code == 200


class TestSkills:
    def test_list_skills(self, client):
        r = client.get("/skills")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] > 0
        assert len(data["skills"]) > 0

    def test_list_skills_with_domain(self, client):
        r = client.get("/skills", params={"domain": "security"})
        assert r.status_code == 200

    def test_list_skills_with_limit(self, client):
        r = client.get("/skills", params={"limit": 3})
        assert r.status_code == 200
        data = r.json()
        assert len(data["skills"]) <= 3

    def test_get_skill(self, client):
        # First get a skill ID
        r = client.get("/skills", params={"limit": 1})
        skill_id = r.json()["skills"][0]["id"]

        r = client.get(f"/skills/{skill_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == skill_id
        assert "capabilities" in data
        assert "tags" in data

    def test_get_skill_not_found(self, client):
        r = client.get("/skills/nonexistent-id-12345")
        assert r.status_code == 404


class TestRecommend:
    def test_recommend(self, client):
        r = client.get("/recommend", params={"task": "security audit", "limit": 5})
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data["recommendations"], list)

    def test_recommend_with_installed(self, client):
        # Get some skill IDs
        r = client.get("/skills", params={"limit": 2})
        ids = ",".join(s["id"] for s in r.json()["skills"])

        r = client.get("/recommend", params={"installed": ids, "limit": 5})
        assert r.status_code == 200

    def test_recommend_for_skill(self, client):
        r = client.get("/skills", params={"limit": 1})
        skill_id = r.json()["skills"][0]["id"]

        r = client.get(f"/recommend/{skill_id}", params={"limit": 5})
        assert r.status_code == 200
        data = r.json()
        assert data["skill_id"] == skill_id


class TestRepos:
    def test_list_repos(self, client):
        r = client.get("/repos")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] > 0
        assert len(data["repos"]) > 0


class TestExport:
    def test_export_json(self, client):
        r = client.get("/export/json")
        assert r.status_code == 200
        data = r.json()
        assert data["schema_version"] == "3.0"
        assert data["total_skills"] > 0

    def test_export_json_filtered(self, client):
        r = client.get("/export/json", params={"limit": 3})
        assert r.status_code == 200
        data = r.json()
        assert data["total_skills"] <= 3

    def test_export_csv(self, client):
        r = client.get("/export/csv")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]

    def test_export_stats(self, client):
        r = client.get("/export/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["total_skills"] > 0


class TestSearchStats:
    def test_search_stats(self, client):
        r = client.get("/search/stats")
        assert r.status_code == 200
        data = r.json()
        assert "fts_skills" in data or "skills" in data


class TestAdmin:
    def test_rebuild_fts(self, client):
        r = client.post("/admin/rebuild-fts")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
