"""SkillsBank CLI — search, recommend, export, compose, sync, and manage the registry."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click
from sqlalchemy import func, text
from sqlalchemy.orm import Session, sessionmaker

from skillsbank.db.engine import create_engine_from_url
from skillsbank.db.persistence_models import (
    CapabilityRow,
    RepoRow,
    SkillRow,
    TagRow,
    VersionRow,
)

# ── Helpers ────────────────────────────────────────────────────────────

DEFAULT_DB = os.environ.get(
    "SKILLSBANK_DB",
    str(Path(__file__).resolve().parent.parent / "skillsbank.db"),
)

_engine_cache: dict[str, tuple] = {}


def _get_session(db_path: str) -> Session:
    """Get or create a session for the given DB path."""
    abs_path = str(Path(db_path).resolve())
    if abs_path not in _engine_cache:
        eng = create_engine_from_url(f"sqlite:///{abs_path}")
        from skillsbank.db.base import Base

        Base.metadata.create_all(bind=eng)
        factory = sessionmaker(bind=eng)
        _engine_cache[abs_path] = (eng, factory)
    _, factory = _engine_cache[abs_path]
    return factory()


def _json_out(data: object, compact: bool = False) -> None:
    """Print JSON to stdout."""
    if compact:
        click.echo(json.dumps(data, separators=(",", ":")))
    else:
        click.echo(json.dumps(data, indent=2))


def _format_table(rows: list[dict], columns: list[str], max_width: int = 80) -> str:
    """Format rows as a simple text table."""
    if not rows:
        return "(no results)"
    # Calculate column widths
    widths = {c: len(c) for c in columns}
    for row in rows:
        for c in columns:
            val = str(row.get(c, ""))
            widths[c] = min(max(widths[c], len(val)), max_width)
    # Header
    header = " | ".join(c.ljust(widths[c]) for c in columns)
    sep = "-+-".join("-" * widths[c] for c in columns)
    lines = [header, sep]
    for row in rows:
        line = " | ".join(str(row.get(c, "")).ljust(widths[c])[:max_width] for c in columns)
        lines.append(line)
    return "\n".join(lines)


# ── Main CLI ──────────────────────────────────────────────────────────


@click.group()
@click.option("--db", default=DEFAULT_DB, envvar="SKILLSBANK_DB", help="Path to SQLite database")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.option("--compact", is_flag=True, help="Compact JSON output")
@click.pass_context
def cli(ctx: click.Context, db: str, json_output: bool, compact: bool) -> None:
    """SkillsBank — universal agent-skill registry."""
    ctx.ensure_object(dict)
    ctx.obj["db"] = db
    ctx.obj["json"] = json_output
    ctx.obj["compact"] = compact


# ── Search ────────────────────────────────────────────────────────────


@cli.command()
@click.argument("query")
@click.option("--domain", default=None, help="Filter by domain")
@click.option("--category", default=None, help="Filter by taxonomy category")
@click.option("--repo", default=None, help="Filter by source repo")
@click.option("--min-quality", type=float, default=None, help="Minimum quality score")
@click.option("--limit", type=int, default=20, help="Max results")
@click.option("--offset", type=int, default=0, help="Skip N results")
@click.option("--facets", is_flag=True, help="Include facet counts")
@click.pass_context
def search(
    ctx: click.Context,
    query: str,
    domain: str | None,
    category: str | None,
    repo: str | None,
    min_quality: float | None,
    limit: int,
    offset: int,
    facets: bool,
) -> None:
    """Search skills by text query."""
    from skillsbank.search import SearchFilters
    from skillsbank.search import search as do_search

    session = _get_session(ctx.obj["db"])
    try:
        filters = SearchFilters(
            domain=domain,
            category=category,
            repo=repo,
            min_quality=min_quality,
        )
        resp = do_search(session, query, filters=filters, limit=limit, offset=offset, include_facets=facets)
        if ctx.obj["json"]:
            data = {
                "total": resp.total,
                "results": [
                    {
                        "skill_id": r.skill_id,
                        "name": r.name,
                        "summary": r.summary,
                        "domain": r.domain,
                        "repo": r.repo,
                        "quality_score": r.quality_score,
                        "bm25_score": r.bm25_score,
                    }
                    for r in resp.results
                ],
            }
            if facets and resp.facets:
                data["facets"] = {k: dict(v) for k, v in resp.facets.items()}
            _json_out(data, ctx.obj["compact"])
        else:
            click.echo(f"Found {resp.total} results for '{query}':\n")
            rows = [
                {
                    "id": r.skill_id[:12],
                    "name": r.name[:40],
                    "domain": r.domain[:15],
                    "quality": f"{r.quality_score:.2f}",
                    "bm25": f"{r.bm25_score:.2f}",
                    "repo": r.repo[:30],
                }
                for r in resp.results
            ]
            click.echo(_format_table(rows, ["id", "name", "domain", "quality", "bm25", "repo"]))
            if facets and resp.facets:
                click.echo("\nFacets:")
                for facet_name, counts in resp.facets.items():
                    click.echo(f"  {facet_name}:")
                    for label, count in counts[:5]:
                        click.echo(f"    {label}: {count}")
    finally:
        session.close()


# ── Autocomplete ──────────────────────────────────────────────────────


@cli.command()
@click.argument("prefix")
@click.option("--limit", type=int, default=10, help="Max suggestions")
@click.pass_context
def autocomplete(ctx: click.Context, prefix: str, limit: int) -> None:
    """Autocomplete skill names by prefix."""
    from skillsbank.search import autocomplete as do_autocomplete

    session = _get_session(ctx.obj["db"])
    try:
        results = do_autocomplete(session, prefix, limit=limit)
        if ctx.obj["json"]:
            _json_out(results, ctx.obj["compact"])
        else:
            for r in results:
                click.echo(f"  {r}")
    finally:
        session.close()


# ── Recommend ─────────────────────────────────────────────────────────


@cli.command("recommend")
@click.argument("task")
@click.option("--installed", multiple=True, help="Already-installed skill IDs to exclude")
@click.option("--limit", type=int, default=10, help="Max recommendations")
@click.pass_context
def recommend_cmd(ctx: click.Context, task: str, installed: tuple[str, ...], limit: int) -> None:
    """Recommend skills for a task description."""
    from skillsbank.recommender import recommend as do_recommend

    session = _get_session(ctx.obj["db"])
    try:
        result = do_recommend(session, task, installed_ids=list(installed), limit=limit)
        if ctx.obj["json"]:
            _json_out(
                {
                    "task": task,
                    "recommendations": [
                        {
                            "skill_id": r.skill_id,
                            "name": r.name,
                            "summary": r.summary,
                            "score": round(r.score, 3),
                            "reason": r.reason.value,
                            "reason_detail": r.reason_detail,
                            "domain": r.domain,
                            "quality_score": round(r.quality_score, 3),
                        }
                        for r in result.recommendations
                    ],
                },
                ctx.obj["compact"],
            )
        else:
            click.echo(f"Recommendations for: {task}\n")
            for i, r in enumerate(result.recommendations, 1):
                click.echo(f"  {i}. {r.name} [{r.reason.value}] (score: {r.score:.2f})")
                click.echo(f"     {r.summary[:80]}")
                click.echo(f"     repo: {r.source_repo} | domain: {r.domain}")
                click.echo()
    finally:
        session.close()


@cli.command("recommend-for")
@click.argument("skill_id")
@click.option("--limit", type=int, default=10, help="Max recommendations")
@click.pass_context
def recommend_for_cmd(ctx: click.Context, skill_id: str, limit: int) -> None:
    """Recommend skills similar/complementary to a specific skill."""
    from skillsbank.recommender import recommend_for_skill

    session = _get_session(ctx.obj["db"])
    try:
        results = recommend_for_skill(session, skill_id, limit=limit)
        if ctx.obj["json"]:
            _json_out(
                {
                    "skill_id": skill_id,
                    "recommendations": [
                        {
                            "skill_id": r.skill_id,
                            "name": r.name,
                            "score": round(r.score, 3),
                            "reason": r.reason.value,
                        }
                        for r in results
                    ],
                },
                ctx.obj["compact"],
            )
        else:
            click.echo(f"Skills similar/complementary to {skill_id}:\n")
            for r in results:
                click.echo(f"  {r.name} [{r.reason.value}] (score: {r.score:.2f})")
    finally:
        session.close()


# ── Export ────────────────────────────────────────────────────────────


@cli.command("export")
@click.argument("format", type=click.Choice(["json", "markdown", "csv"]))
@click.argument("output", type=click.Path())
@click.option("--domain", default=None, help="Filter by domain")
@click.option("--repo", default=None, help="Filter by repo")
@click.option("--min-quality", type=float, default=None, help="Minimum quality score")
@click.option("--limit", type=int, default=None, help="Max skills to export")
@click.pass_context
def export_cmd(
    ctx: click.Context,
    format: str,
    output: str,
    domain: str | None,
    repo: str | None,
    min_quality: float | None,
    limit: int | None,
) -> None:
    """Export skills to JSON, Markdown, or CSV."""
    from skillsbank.exports import ExportOptions, export_csv, export_json, export_markdown

    session = _get_session(ctx.obj["db"])
    try:
        opts = ExportOptions(
            format=format,
            domain=domain,
            repo=repo,
            min_quality=min_quality,
            limit=limit,
        )
        if format == "json":
            stats = export_json(session, output, opts)
        elif format == "markdown":
            stats = export_markdown(session, output, opts)
        else:
            stats = export_csv(session, output, opts)
            click.echo(f"Exported {stats['count']} skills to {output}")
    finally:
        session.close()


# ── Skills ────────────────────────────────────────────────────────────


@cli.group("skills")
def skills_group() -> None:
    """Browse and inspect skills."""


@skills_group.command("list")
@click.option("--domain", default=None, help="Filter by domain")
@click.option("--repo", default=None, help="Filter by repo")
@click.option("--limit", type=int, default=50, help="Max results")
@click.option("--offset", type=int, default=0, help="Skip N results")
@click.pass_context
def skills_list(ctx: click.Context, domain: str | None, repo: str | None, limit: int, offset: int) -> None:
    """List skills in the registry."""
    session = _get_session(ctx.obj["db"])
    try:
        q = session.query(SkillRow).filter(SkillRow.lifecycle != "archived")
        if domain:
            q = q.join(VersionRow, VersionRow.skill_id == SkillRow.id).filter(VersionRow.domain_primary == domain)
        if repo:
            q = q.join(VersionRow, VersionRow.skill_id == SkillRow.id).filter(VersionRow.source_repo == repo)
        total = q.count()
        skills = q.offset(offset).limit(limit).all()
        if ctx.obj["json"]:
            _json_out(
                {
                    "total": total,
                    "skills": [
                        {"id": s.id, "name": s.name, "domain": s.primary_source, "versions": s.version_count}
                        for s in skills
                    ],
                },
                ctx.obj["compact"],
            )
        else:
            click.echo(f"Skills ({total} total, showing {len(skills)}):\n")
            rows = [
                {
                    "id": s.id[:12],
                    "name": s.name[:40],
                    "versions": s.version_count,
                    "source": (s.primary_source or "")[:30],
                }
                for s in skills
            ]
            click.echo(_format_table(rows, ["id", "name", "versions", "source"]))
    finally:
        session.close()


@skills_group.command("get")
@click.argument("skill_id")
@click.pass_context
def skills_get(ctx: click.Context, skill_id: str) -> None:
    """Get detailed info for a skill."""
    session = _get_session(ctx.obj["db"])
    try:
        skill = session.get(SkillRow, skill_id)
        if not skill:
            click.echo(f"Skill not found: {skill_id}", err=True)
            sys.exit(1)
        version = (
            session.query(VersionRow)
            .filter(VersionRow.skill_id == skill_id)
            .order_by(VersionRow.imported_at.desc())
            .first()
        )
        caps = []
        tags = []
        if version:
            caps = [
                c.name for c in session.query(CapabilityRow).filter(CapabilityRow.version_id_fk == version.id).all()
            ]
            tags = [t.name for t in session.query(TagRow).filter(TagRow.version_id_fk == version.id).all()]

        if ctx.obj["json"]:
            data = {
                "id": skill.id,
                "name": skill.name,
                "display_name": skill.display_name,
                "lifecycle": skill.lifecycle,
                "version_count": skill.version_count,
                "primary_source": skill.primary_source,
            }
            if version:
                data["version"] = {
                    "version_id": version.version_id,
                    "summary": version.summary,
                    "domain": version.domain_primary,
                    "quality_score": version.quality.get("overall_score") if version.quality else None,
                    "capabilities": caps,
                    "tags": tags,
                }
            _json_out(data, ctx.obj["compact"])
        else:
            click.echo(f"Skill: {skill.name}")
            click.echo(f"  ID: {skill.id}")
            click.echo(f"  Lifecycle: {skill.lifecycle}")
            click.echo(f"  Versions: {skill.version_count}")
            click.echo(f"  Source: {skill.primary_source}")
            if version:
                click.echo(f"  Domain: {version.domain_primary}")
                click.echo(f"  Summary: {version.summary[:100] if version.summary else 'N/A'}")
                if version.quality:
                    click.echo(f"  Quality: {version.quality.get('overall_score', 'N/A')}")
                if caps:
                    click.echo(f"  Capabilities: {', '.join(caps[:10])}")
                if tags:
                    click.echo(f"  Tags: {', '.join(tags[:10])}")
    finally:
        session.close()


# ── Repos ─────────────────────────────────────────────────────────────


@cli.command("repos")
@click.pass_context
def repos_cmd(ctx: click.Context) -> None:
    """List repositories in the registry."""
    session = _get_session(ctx.obj["db"])
    try:
        repos = session.query(RepoRow).order_by(RepoRow.skill_count.desc()).all()
        if ctx.obj["json"]:
            _json_out(
                [
                    {
                        "id": r.id,
                        "owner": r.owner,
                        "name": r.name,
                        "url": r.url,
                        "skill_count": r.skill_count,
                        "ecosystem": r.ecosystem,
                    }
                    for r in repos
                ],
                ctx.obj["compact"],
            )
        else:
            click.echo(f"Repositories ({len(repos)}):\n")
            rows = [
                {
                    "owner": (r.owner or "?")[:20],
                    "name": (r.name or "?")[:25],
                    "skills": r.skill_count or 0,
                    "ecosystem": (r.ecosystem or "")[:15],
                }
                for r in repos
            ]
            click.echo(_format_table(rows, ["owner", "name", "skills", "ecosystem"]))
    finally:
        session.close()


# ── Compose ───────────────────────────────────────────────────────────


@cli.command("compose")
@click.argument("skill_ids", nargs=-1, required=True)
@click.option("--name", default="composite", help="Name for the composite skill")
@click.option("--strategy", type=click.Choice(["sequential", "parallel", "pipeline"]), default="sequential")
@click.option(
    "--conflict-resolution", type=click.Choice(["warn", "fail", "prefer_first", "prefer_last"]), default="warn"
)
@click.pass_context
def compose_cmd(
    ctx: click.Context,
    skill_ids: tuple[str, ...],
    name: str,
    strategy: str,
    conflict_resolution: str,
) -> None:
    """Compose multiple skills into a pipeline."""
    from skillsbank.composition import CompositionStrategy, ConflictResolution, compose_skills

    session = _get_session(ctx.obj["db"])
    try:
        strat_map = {
            "sequential": CompositionStrategy.SEQUENTIAL,
            "parallel": CompositionStrategy.PARALLEL,
            "pipeline": CompositionStrategy.PIPELINE,
        }
        res_map = {
            "warn": ConflictResolution.WARN,
            "fail": ConflictResolution.FAIL,
            "prefer_first": ConflictResolution.PREFER_FIRST,
            "prefer_last": ConflictResolution.PREFER_LAST,
        }
        result = compose_skills(
            session,
            list(skill_ids),
            name=name,
            strategy=strat_map[strategy],
            conflict_resolution=res_map[conflict_resolution],
        )
        if ctx.obj["json"]:
            _json_out(
                {
                    "name": result.composite.name,
                    "valid": result.composite.is_valid,
                    "total_components": result.total_components,
                    "unique_repos": result.unique_repos,
                    "install_order": result.install_order,
                    "warnings": result.warnings,
                    "conflicts": [
                        {"type": c.conflict_type, "description": c.description, "severity": c.severity}
                        for c in result.composite.conflicts
                    ],
                },
                ctx.obj["compact"],
            )
        else:
            click.echo(f"Composite: {result.composite.name}")
            click.echo(f"  Valid: {result.composite.is_valid}")
            click.echo(f"  Components: {result.total_components}")
            click.echo(f"  Unique repos: {result.unique_repos}")
            if result.install_order:
                click.echo(f"  Install order: {' → '.join(result.install_order)}")
            if result.warnings:
                click.echo("  Warnings:")
                for w in result.warnings:
                    click.echo(f"    - {w}")
            if result.composite.conflicts:
                click.echo("  Conflicts:")
                for c in result.composite.conflicts:
                    click.echo(f"    [{c.severity}] {c.conflict_type}: {c.description}")
    finally:
        session.close()


# ── Dedup ─────────────────────────────────────────────────────────────


@cli.command("dedup")
@click.option("--min-score", type=float, default=0.60, help="Minimum similarity score")
@click.pass_context
def dedup_cmd(ctx: click.Context, min_score: float) -> None:
    """Run duplicate detection across all skills."""
    from skillsbank.dedup import detect_duplicates

    session = _get_session(ctx.obj["db"])
    try:
        click.echo("Running duplicate detection...")
        result = detect_duplicates(session, min_score=min_score)
        if ctx.obj["json"]:
            _json_out(
                {
                    "pairs_compared": result.pairs_compared,
                    "exact": result.exact_duplicates,
                    "near": result.near_duplicates,
                    "functional": result.functional_overlaps,
                    "related": result.related,
                    "elapsed_seconds": round(result.elapsed_seconds, 1),
                },
                ctx.obj["compact"],
            )
        else:
            click.echo(f"Compared {result.pairs_compared} pairs in {result.elapsed_seconds:.1f}s")
            click.echo(f"  Exact duplicates: {result.exact_duplicates}")
            click.echo(f"  Near duplicates: {result.near_duplicates}")
            click.echo(f"  Functional overlaps: {result.functional_overlaps}")
            click.echo(f"  Related: {result.related}")
    finally:
        session.close()


# ── Sync ──────────────────────────────────────────────────────────────


@cli.command("import")
@click.argument("v3_path", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Preview changes without applying")
@click.pass_context
def import_cmd(ctx: click.Context, v3_path: str, dry_run: bool) -> None:
    """Import or sync skills from a v3 JSON file."""
    from skillsbank.db.importer import import_v3_to_sqlite

    session = _get_session(ctx.obj["db"])
    try:
        if dry_run:
            import json

            with open(v3_path) as f:
                data = json.load(f)
            click.echo(f"Would import {len(data.get('skills', []))} skills from {v3_path}")
        else:
            stats = import_v3_to_sqlite(session, v3_path)
            click.echo("Import complete:")
            click.echo(f"  Skills imported: {stats.skills_imported}")
            click.echo(f"  Versions imported: {stats.versions_imported}")
            click.echo(f"  Repos imported: {stats.repos_imported}")
            click.echo(f"  Capabilities imported: {stats.capabilities_imported}")
            click.echo(f"  Tags imported: {stats.tags_imported}")
            if stats.errors:
                click.echo(f"  Errors: {len(stats.errors)}")
                for err in stats.errors[:5]:
                    click.echo(f"    - {err}")
    finally:
        session.close()


# ── Stats ─────────────────────────────────────────────────────────────


@cli.command("stats")
@click.pass_context
def stats_cmd(ctx: click.Context) -> None:
    """Show registry statistics."""
    session = _get_session(ctx.obj["db"])
    try:
        skill_count = session.query(func.count(SkillRow.id)).scalar()
        version_count = session.query(func.count(VersionRow.id)).scalar()
        repo_count = session.query(func.count(RepoRow.id)).scalar()
        cap_count = session.query(func.count(CapabilityRow.id)).scalar()
        tag_count = session.query(func.count(TagRow.id)).scalar()

        # Domain distribution
        domain_rows = (
            session.query(VersionRow.domain_primary, func.count(VersionRow.id))
            .group_by(VersionRow.domain_primary)
            .order_by(func.count(VersionRow.id).desc())
            .limit(10)
            .all()
        )

        # Quality stats
        avg_quality = session.execute(
            text("SELECT AVG(json_extract(quality, '$.overall_score')) FROM versions WHERE quality IS NOT NULL")
        ).scalar()

        data = {
            "skills": skill_count,
            "versions": version_count,
            "repos": repo_count,
            "capabilities": cap_count,
            "tags": tag_count,
            "avg_quality": round(avg_quality, 3) if avg_quality else None,
            "top_domains": {d: c for d, c in domain_rows if d},
        }

        if ctx.obj["json"]:
            _json_out(data, ctx.obj["compact"])
        else:
            click.echo("SkillsBank Registry Statistics")
            click.echo("=" * 40)
            click.echo(f"  Skills:       {skill_count:,}")
            click.echo(f"  Versions:     {version_count:,}")
            click.echo(f"  Repositories: {repo_count:,}")
            click.echo(f"  Capabilities: {cap_count:,}")
            click.echo(f"  Tags:         {tag_count:,}")
            if avg_quality:
                click.echo(f"  Avg Quality:  {avg_quality:.3f}")
            if domain_rows:
                click.echo("\nTop Domains:")
                for domain, count in domain_rows:
                    if domain:
                        click.echo(f"  {domain}: {count}")
    finally:
        session.close()


# ── Rebuild FTS ───────────────────────────────────────────────────────


@cli.command("rebuild-fts")
@click.pass_context
def rebuild_fts_cmd(ctx: click.Context) -> None:
    """Rebuild the full-text search index."""
    from skillsbank.search import rebuild_fts_index

    session = _get_session(ctx.obj["db"])
    try:
        counts = rebuild_fts_index(session)
        click.echo(f"FTS index rebuilt: {counts}")
    finally:
        session.close()


# ── Normalize ─────────────────────────────────────────────────────────


@cli.command("normalize")
@click.pass_context
def normalize_cmd(ctx: click.Context) -> None:
    """Normalize capability taxonomy in the database."""
    from skillsbank.db.taxonomy_sync import get_category_distribution, normalize_db_capabilities

    session = _get_session(ctx.obj["db"])
    try:
        stats = normalize_db_capabilities(session)
        dist = get_category_distribution(session)
        if ctx.obj["json"]:
            _json_out({"normalization": stats, "distribution": dist}, ctx.obj["compact"])
        else:
            click.echo(f"Normalized: {stats.get('normalized', 0)} capabilities")
            click.echo(f"Uncategorized: {stats.get('uncategorized', 0)}")
            click.echo("\nCategory Distribution:")
            for cat, count in sorted(dist.items(), key=lambda x: -x[1])[:15]:
                click.echo(f"  {cat}: {count}")
    finally:
        session.close()


# ── Deps ──────────────────────────────────────────────────────────────


@cli.command("deps")
@click.option("--skill-id", default=None, help="Show deps for a specific skill")
@click.pass_context
def deps_cmd(ctx: click.Context, skill_id: str | None) -> None:
    """Show dependency summary or per-skill dependencies."""
    from skillsbank.db.dep_sync import get_dependency_summary
    from skillsbank.deps.extractor import extract_from_version

    session = _get_session(ctx.obj["db"])
    try:
        if skill_id:
            v = session.query(VersionRow).filter(VersionRow.skill_id == skill_id).first()
            if not v:
                click.echo(f"Skill not found: {skill_id}", err=True)
                sys.exit(1)
            deps = extract_from_version(
                {
                    "summary": v.summary,
                    "long_description": v.long_description,
                    "raw_content": v.raw_content,
                    "declared_dependencies": v.declared_dependencies,
                    "inferred_dependencies": v.inferred_dependencies,
                }
            )
            if ctx.obj["json"]:
                _json_out(
                    [{"name": d.name, "category": d.category, "confidence": d.confidence} for d in deps],
                    ctx.obj["compact"],
                )
            else:
                click.echo(f"Dependencies for {skill_id} ({len(deps)} found):")
                for d in deps:
                    click.echo(f"  [{d.category}] {d.name} (confidence: {d.confidence:.2f})")
        else:
            summary = get_dependency_summary(session)
            if ctx.obj["json"]:
                _json_out(summary, ctx.obj["compact"])
            else:
                click.echo("Dependency Summary")
                click.echo("=" * 40)
                for cat, items in summary.items():
                    if not items:
                        continue
                    if isinstance(items, list):
                        click.echo(f"\n{cat}:")
                        for name, count in items[:10]:
                            click.echo(f"  {name}: {count}")
                    else:
                        click.echo(f"\n{cat}: {items}")
    finally:
        session.close()


# ── Doctor ────────────────────────────────────────────────────────────


@cli.command("doctor")
@click.pass_context
def doctor_cmd(ctx: click.Context) -> None:
    """Run health checks on the registry."""
    from skillsbank.analytics import run_health_checks

    session = _get_session(ctx.obj["db"])
    try:
        checks = run_health_checks(session)
        all_ok = all(c.status == "ok" for c in checks)

        if ctx.obj["json"]:
            _json_out(
                {
                    "healthy": all_ok,
                    "checks": [
                        {
                            "name": c.name,
                            "status": c.status,
                            "detail": c.detail,
                            "value": c.value,
                            "recommendation": c.recommendation,
                        }
                        for c in checks
                    ],
                },
                ctx.obj["compact"],
            )
        else:
            click.echo("SkillsBank Health Check")
            click.echo("=" * 50)
            for c in checks:
                icon = {"ok": "OK", "warn": "!!", "fail": "XX", "info": "--"}.get(c.status, "??")
                click.echo(f"  [{icon}] {c.name}: {c.detail}")
                if c.recommendation:
                    click.echo(f"         -> {c.recommendation}")
            click.echo()
            status = {"healthy": "HEALTHY", "degraded": "DEGRADED", "unhealthy": "ISSUES FOUND"}
            click.echo(f"Overall: {status.get(all_ok and 'healthy' or 'unhealthy', 'UNKNOWN')}")
    finally:
        session.close()


# ── Analytics ─────────────────────────────────────────────────────────


@cli.command("analytics")
@click.option(
    "--section",
    type=click.Choice(
        [
            "all",
            "health",
            "coverage",
            "gaps",
            "quality",
            "ecosystems",
            "domains",
            "categories",
            "risks",
            "compatibility",
            "dependencies",
            "duplicates",
        ]
    ),
    default="all",
    help="Which analytics section to show",
)
@click.pass_context
def analytics_cmd(ctx: click.Context, section: str) -> None:
    """Comprehensive registry analytics and diagnostics."""
    from skillsbank.analytics import (
        compute_agent_compatibility,
        compute_category_distribution,
        compute_coverage,
        compute_dependency_risks,
        compute_domain_distribution,
        compute_duplicate_summary,
        compute_ecosystem_health,
        compute_gaps,
        compute_quality_distribution,
        compute_risk_distribution,
        run_full_analytics,
        run_health_checks,
    )

    session = _get_session(ctx.obj["db"])
    try:
        if section == "all":
            report = run_full_analytics(session)
            if ctx.obj["json"]:
                _json_out(report.to_dict(), ctx.obj["compact"])
            else:
                _print_analytics_report(report)
        elif section == "health":
            checks = run_health_checks(session)
            if ctx.obj["json"]:
                _json_out(
                    [{"name": c.name, "status": c.status, "detail": c.detail} for c in checks], ctx.obj["compact"]
                )
            else:
                for c in checks:
                    click.echo(f"  [{c.status.upper():4s}] {c.name}: {c.detail}")
        elif section == "coverage":
            cov = compute_coverage(session)
            if ctx.obj["json"]:
                _json_out({"total": cov.total_skills, "percentages": cov.coverage_pct}, ctx.obj["compact"])
            else:
                click.echo(f"Coverage ({cov.total_skills} skills):")
                for field_name, pct in sorted(cov.coverage_pct.items(), key=lambda x: -x[1]):
                    bar = "#" * int(pct / 5)
                    click.echo(f"  {field_name:20s} {pct:5.1f}% {bar}")
        elif section == "gaps":
            gaps = compute_gaps(session)
            if ctx.obj["json"]:
                _json_out(
                    {
                        "missing_summary": len(gaps.missing_summary),
                        "missing_domain": len(gaps.missing_domain),
                        "uncategorized_capabilities": len(gaps.uncategorized_capabilities),
                        "empty_repos": gaps.empty_repos,
                        "high_risk_skills": len(gaps.high_risk_skills),
                    },
                    ctx.obj["compact"],
                )
            else:
                click.echo("Gap Analysis:")
                click.echo(f"  Missing summary:     {len(gaps.missing_summary)}")
                click.echo(f"  Missing domain:      {len(gaps.missing_domain)}")
                click.echo(f"  Uncategorized caps:  {len(gaps.uncategorized_capabilities)}")
                click.echo(f"  Empty repos:         {len(gaps.empty_repos)}")
                click.echo(f"  High-risk skills:    {len(gaps.high_risk_skills)}")
                if gaps.empty_repos:
                    click.echo(f"\n  Empty repos: {', '.join(gaps.empty_repos[:5])}")
        elif section == "quality":
            q = compute_quality_distribution(session)
            if ctx.obj["json"]:
                _json_out(
                    {"min": q.min, "max": q.max, "mean": q.mean, "median": q.median, "histogram": q.histogram},
                    ctx.obj["compact"],
                )
            else:
                click.echo("Quality Distribution:")
                click.echo(f"  Min: {q.min:.3f}  Max: {q.max:.3f}  Mean: {q.mean:.3f}  Median: {q.median:.3f}")
                click.echo(f"  P25: {q.p25:.3f}  P75: {q.p75:.3f}")
                click.echo("\n  Histogram:")
                for bucket, count in q.histogram.items():
                    bar = "#" * min(count, 50)
                    click.echo(f"    {bucket}: {count:4d} {bar}")
                if q.top_skills:
                    click.echo("\n  Top skills:")
                    for s in q.top_skills[:5]:
                        click.echo(f"    {s['name']}: {s['score']:.3f}")
        elif section == "ecosystems":
            ecos = compute_ecosystem_health(session)
            if ctx.obj["json"]:
                _json_out(
                    [
                        {"repo": e.repo_url, "skills": e.skill_count, "quality": e.avg_quality, "issues": e.issues}
                        for e in ecos[:20]
                    ],
                    ctx.obj["compact"],
                )
            else:
                click.echo(f"Ecosystem Health ({len(ecos)} repos):")
                for e in ecos[:20]:
                    issues = f" [{', '.join(e.issues)}]" if e.issues else ""
                    click.echo(f"  {e.owner}/{e.name}: {e.skill_count} skills, quality={e.avg_quality:.3f}{issues}")
        elif section == "domains":
            dist = compute_domain_distribution(session)
            if ctx.obj["json"]:
                _json_out(dist, ctx.obj["compact"])
            else:
                click.echo("Domain Distribution:")
                for domain, count in sorted(dist.items(), key=lambda x: -x[1]):
                    bar = "#" * min(count // 5, 40)
                    click.echo(f"  {domain:20s} {count:4d} {bar}")
        elif section == "categories":
            dist = compute_category_distribution(session)
            if ctx.obj["json"]:
                _json_out(dist, ctx.obj["compact"])
            else:
                click.echo("Capability Category Distribution:")
                for cat, count in sorted(dist.items(), key=lambda x: -x[1]):
                    bar = "#" * min(count // 5, 40)
                    click.echo(f"  {cat:20s} {count:4d} {bar}")
        elif section == "risks":
            dist = compute_risk_distribution(session)
            if ctx.obj["json"]:
                _json_out(dist, ctx.obj["compact"])
            else:
                click.echo("Security Risk Distribution:")
                for level, count in sorted(dist.items(), key=lambda x: -x[1]):
                    click.echo(f"  {level:12s} {count:4d}")
        elif section == "compatibility":
            compat = compute_agent_compatibility(session)
            if ctx.obj["json"]:
                _json_out(compat, ctx.obj["compact"])
            else:
                click.echo("Agent Compatibility:")
                for agent, levels in sorted(compat.items()):
                    click.echo(f"  {agent}:")
                    for level, count in sorted(levels.items(), key=lambda x: -x[1]):
                        click.echo(f"    {level}: {count}")
        elif section == "dependencies":
            risks = compute_dependency_risks(session)
            if ctx.obj["json"]:
                _json_out(risks, ctx.obj["compact"])
            else:
                click.echo(f"Dependency Risks ({len(risks)} found):")
                for r in risks[:20]:
                    click.echo(f"  [{r['severity']}] {r['skill_id']}: {r['detail']}")
        elif section == "duplicates":
            dup = compute_duplicate_summary(session)
            if ctx.obj["json"]:
                _json_out(dup, ctx.obj["compact"])
            else:
                click.echo("Duplicate Summary:")
                click.echo(f"  Total similarities: {dup.get('total_similarities', 0)}")
                click.echo(f"  Duplicate relationships: {dup.get('duplicate_relationships', 0)}")
                for cat, count in dup.get("distribution", {}).items():
                    click.echo(f"  {cat}: {count}")
    finally:
        session.close()


def _print_analytics_report(report: object) -> None:
    """Pretty-print a full analytics report."""
    r = report  # type: ignore[assignment]
    click.echo("SkillsBank Analytics Report")
    click.echo("=" * 50)
    click.echo(f"Generated: {r.generated_at}")
    click.echo(f"Overall Health: {r.overall_health.upper()}")
    click.echo()

    # Health checks
    click.echo("--- Health Checks ---")
    for c in r.checks:
        icon = {"ok": "OK", "warn": "!!", "fail": "XX", "info": "--"}.get(c.status, "??")
        click.echo(f"  [{icon}] {c.name}: {c.detail}")
    click.echo()

    # Coverage
    click.echo("--- Data Coverage ---")
    for field_name, pct in sorted(r.coverage.coverage_pct.items(), key=lambda x: -x[1]):
        bar = "#" * int(pct / 5)
        click.echo(f"  {field_name:20s} {pct:5.1f}% {bar}")
    click.echo()

    # Quality
    click.echo("--- Quality ---")
    click.echo(
        f"  Mean: {r.quality.mean:.3f}  Median: {r.quality.median:.3f}  Range: [{r.quality.min:.3f}, {r.quality.max:.3f}]"
    )
    click.echo()

    # Domains
    click.echo("--- Top Domains ---")
    for domain, count in list(r.domain_distribution.items())[:10]:
        click.echo(f"  {domain:20s} {count:4d}")
    click.echo()

    # Risk
    click.echo("--- Risk Distribution ---")
    for level, count in r.risk_distribution.items():
        click.echo(f"  {level:12s} {count:4d}")
    click.echo()

    # Ecosystems
    click.echo("--- Top Ecosystems ---")
    for e in r.ecosystems[:10]:
        issues = f" [{', '.join(e.issues)}]" if e.issues else ""
        click.echo(f"  {e.owner}/{e.name}: {e.skill_count} skills{issues}")
    click.echo()

    # Duplicates
    click.echo("--- Duplicates ---")
    click.echo(f"  Similarities: {r.duplicate_summary.get('total_similarities', 0)}")
    click.echo(f"  Duplicate pairs: {r.duplicate_summary.get('duplicate_relationships', 0)}")


# ── Entry point ───────────────────────────────────────────────────────


def main() -> None:
    """Entry point for `skillsbank` command."""
    cli()


if __name__ == "__main__":
    main()
