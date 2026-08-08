"""REST API for SkillsBank (FastAPI)."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from skillsbank.db.base import Base
from skillsbank.db.engine import create_engine_from_url, get_session
from skillsbank.db.persistence_models import RepoRow, SkillRow, VersionRow
from skillsbank.exports import ExportOptions, export_csv, export_json_string, export_markdown, get_export_stats
from skillsbank.recommender import RecommendationReason, recommend, recommend_for_skill
from skillsbank.search import SearchFilters, autocomplete, get_search_stats, rebuild_fts_index, search

# ── App setup ────────────────────────────────────────────────────────────

DB_PATH = os.environ.get("SKILLSBANK_DB", os.path.join(os.path.dirname(__file__), "..", "skillsbank.db"))
engine = None
SessionLocal = None


def _init_engine(db_path: str | None = None):
    global engine, SessionLocal
    path = db_path or DB_PATH
    engine = create_engine_from_url(f"sqlite:///{path}")
    SessionLocal = sessionmaker(bind=engine)


def _get_db():
    global engine, SessionLocal
    if engine is None:
        _init_engine()
    return SessionLocal()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables if needed (skip for in-memory)
    if engine is None:
        _init_engine()
    Base.metadata.create_all(bind=engine)
    yield
    # Shutdown
    if engine:
        engine.dispose()


app = FastAPI(
    title="SkillsBank API",
    description="Universal agent-skill registry API",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Response models ──────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str
    db_path: str
    total_skills: int
    total_repos: int


class SearchResult(BaseModel):
    skill_id: str
    name: str
    summary: str
    domain: str
    source_repo: str
    score: float


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResult]
    facets: dict[str, dict[str, int]]


class RecommendResponse(BaseModel):
    task: str
    total: int
    recommendations: list[dict]


class SkillDetail(BaseModel):
    id: str
    name: str
    display_name: str | None
    summary: str | None
    domain: str | None
    source_repo: str | None
    source_path: str | None
    capabilities: list[str]
    tags: list[str]
    quality: dict | None
    security: dict | None
    license: dict | None
    compatibility: dict | None


# ── Health ────────────────────────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse)
def health():
    session = _get_db()
    try:
        total_skills = session.query(SkillRow).count()
        total_repos = session.query(RepoRow).count()
        return HealthResponse(
            status="ok",
            db_path=DB_PATH,
            total_skills=total_skills,
            total_repos=total_repos,
        )
    finally:
        session.close()


# ── Search ────────────────────────────────────────────────────────────────


@app.get("/search", response_model=SearchResponse)
def api_search(
    q: str = Query(..., description="Search query"),
    domain: str | None = Query(None),
    category: str | None = Query(None),
    repo: str | None = Query(None),
    min_quality: float | None = Query(None, ge=0.0, le=1.0),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    facets: bool = Query(True),
):
    session = _get_db()
    try:
        filters = SearchFilters(
            domain=domain,
            category=category,
            repo=repo,
            min_quality=min_quality,
        )
        response = search(
            session,
            q,
            filters=filters,
            limit=limit,
            offset=offset,
            include_facets=facets,
        )
        return SearchResponse(
            query=q,
            total=response.total,
            results=[
                SearchResult(
                    skill_id=r.skill_id,
                    name=r.name,
                    summary=r.summary or "",
                    domain=r.domain or "",
                    source_repo=r.repo or "",
                    score=r.bm25_score,
                )
                for r in response.results
            ],
            facets={k: dict(v) for k, v in response.facets.items()},
        )
    finally:
        session.close()


@app.get("/autocomplete")
def api_autocomplete(
    prefix: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
):
    session = _get_db()
    try:
        results = autocomplete(session, prefix, limit=limit)
        return {"prefix": prefix, "results": results}
    finally:
        session.close()


# ── Skills ────────────────────────────────────────────────────────────────


@app.get("/skills/{skill_id}")
def get_skill(skill_id: str):
    session = _get_db()
    try:
        skill = session.query(SkillRow).filter(SkillRow.id == skill_id).first()
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        version = session.query(VersionRow).filter(VersionRow.skill_id == skill_id).first()
        if not version:
            raise HTTPException(status_code=404, detail="No version found for skill")

        from skillsbank.db.persistence_models import CapabilityRow, TagRow

        caps = (
            session.query(CapabilityRow.canonical, CapabilityRow.name)
            .filter(CapabilityRow.version_id_fk == version.id)
            .all()
        )
        tags = session.query(TagRow.name).filter(TagRow.version_id_fk == version.id).all()

        return SkillDetail(
            id=skill.id,
            name=skill.name,
            display_name=skill.display_name,
            summary=version.summary,
            domain=version.domain_primary,
            source_repo=version.source_repo,
            source_path=version.source_path,
            capabilities=[c.canonical or c.name for c in caps],
            tags=[t.name for t in tags],
            quality=version.quality if isinstance(version.quality, dict) else None,
            security=version.security if isinstance(version.security, dict) else None,
            license=version.license if isinstance(version.license, dict) else None,
            compatibility=version.compatibility if isinstance(version.compatibility, dict) else None,
        )
    finally:
        session.close()


@app.get("/skills")
def list_skills(
    domain: str | None = None,
    repo: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    session = _get_db()
    try:
        q = session.query(SkillRow).filter(SkillRow.lifecycle != "archived")
        if domain:
            q = q.join(VersionRow, VersionRow.skill_id == SkillRow.id).filter(VersionRow.domain_primary == domain)
        if repo:
            if domain is None:
                q = q.join(VersionRow, VersionRow.skill_id == SkillRow.id)
            q = q.filter(VersionRow.source_repo == repo)

        total = q.count()
        skills = q.offset(offset).limit(limit).all()

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "skills": [
                {
                    "id": s.id,
                    "name": s.name,
                    "display_name": s.display_name,
                    "lifecycle": s.lifecycle,
                    "version_count": s.version_count,
                }
                for s in skills
            ],
        }
    finally:
        session.close()


# ── Recommendations ──────────────────────────────────────────────────────


@app.get("/recommend", response_model=RecommendResponse)
def api_recommend(
    task: str = Query("", description="Task description"),
    installed: str = Query("", description="Comma-separated installed skill IDs"),
    limit: int = Query(10, ge=1, le=50),
):
    session = _get_db()
    try:
        installed_ids = [s.strip() for s in installed.split(",") if s.strip()] if installed else []
        result = recommend(session, task=task, installed_ids=installed_ids, limit=limit)
        return RecommendResponse(
            task=task,
            total=len(result.recommendations),
            recommendations=[
                {
                    "skill_id": r.skill_id,
                    "name": r.name,
                    "summary": r.summary,
                    "score": r.score,
                    "reason": r.reason.value,
                    "reason_detail": r.reason_detail,
                    "domain": r.domain,
                    "source_repo": r.source_repo,
                }
                for r in result.top(limit)
            ],
        )
    finally:
        session.close()


@app.get("/recommend/{skill_id}")
def api_recommend_for_skill(skill_id: str, limit: int = Query(10, ge=1, le=50)):
    session = _get_db()
    try:
        recs = recommend_for_skill(session, skill_id, limit=limit)
        return {
            "skill_id": skill_id,
            "total": len(recs),
            "recommendations": [
                {
                    "skill_id": r.skill_id,
                    "name": r.name,
                    "summary": r.summary,
                    "score": r.score,
                    "reason": r.reason.value,
                    "reason_detail": r.reason_detail,
                }
                for r in recs
            ],
        }
    finally:
        session.close()


# ── Repos ─────────────────────────────────────────────────────────────────


@app.get("/repos")
def list_repos():
    session = _get_db()
    try:
        repos = session.query(RepoRow).all()
        return {
            "total": len(repos),
            "repos": [
                {
                    "id": r.id,
                    "url": r.url,
                    "owner": r.owner,
                    "name": r.name,
                    "skill_count": r.skill_count,
                }
                for r in repos
            ],
        }
    finally:
        session.close()


# ── Export ────────────────────────────────────────────────────────────────


@app.get("/export/json")
def api_export_json(
    domain: str | None = None,
    repo: str | None = None,
    limit: int | None = None,
):
    session = _get_db()
    try:
        opts = ExportOptions(domain=domain, repo=repo, limit=limit)
        json_str = export_json_string(session, opts)
        return JSONResponse(content=json.loads(json_str))
    finally:
        session.close()


@app.get("/export/csv")
def api_export_csv(
    domain: str | None = None,
    repo: str | None = None,
):
    import tempfile

    session = _get_db()
    try:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            path = f.name
        opts = ExportOptions(domain=domain, repo=repo)
        export_csv(session, path, opts)
        with open(path) as f:
            content = f.read()
        os.unlink(path)
        return PlainTextResponse(content, media_type="text/csv")
    finally:
        session.close()


@app.get("/export/stats")
def api_export_stats():
    session = _get_db()
    try:
        return get_export_stats(session)
    finally:
        session.close()


# ── Search stats ──────────────────────────────────────────────────────────


@app.get("/search/stats")
def api_search_stats():
    session = _get_db()
    try:
        return get_search_stats(session)
    finally:
        session.close()


# ── Admin ─────────────────────────────────────────────────────────────────


@app.post("/admin/rebuild-fts")
def api_rebuild_fts():
    session = _get_db()
    try:
        stats = rebuild_fts_index(session)
        session.commit()
        return {"status": "ok", "stats": stats}
    finally:
        session.close()
