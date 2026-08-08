"""Export formats: v3 JSON, Markdown catalog, CSV."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from skillsbank.db.persistence_models import (
    CapabilityRow,
    RepoRow,
    SkillRow,
    TagRow,
    VersionRow,
)


@dataclass
class ExportOptions:
    format: str = "json"  # "json", "markdown", "csv"
    domain: str | None = None
    category: str | None = None
    min_quality: float | None = None
    max_risk: str | None = None
    repo: str | None = None
    lifecycle: str | None = None
    limit: int | None = None
    include_raw_content: bool = False
    include_capabilities: bool = True
    include_tags: bool = True
    include_dependencies: bool = True
    include_quality: bool = True


def _build_query(session: Session, opts: ExportOptions):
    """Build a filtered query for versions."""
    q = (
        session.query(VersionRow)
        .join(SkillRow, VersionRow.skill_id == SkillRow.id)
        .filter(SkillRow.lifecycle != "archived")
    )
    if opts.domain:
        q = q.filter(VersionRow.domain_primary == opts.domain)
    if opts.repo:
        q = q.filter(VersionRow.source_repo == opts.repo)
    if opts.lifecycle:
        q = q.filter(SkillRow.lifecycle == opts.lifecycle)
    if opts.limit:
        q = q.limit(opts.limit)
    return q


def _version_to_dict(
    version: VersionRow,
    capabilities: list[str],
    tags: list[str],
    opts: ExportOptions,
) -> dict:
    """Convert a version row to an export dict."""
    d: dict = {
        "id": version.skill_id,
        "name": version.name,
        "display_name": version.display_name,
        "summary": version.summary,
        "domain": version.domain_primary,
        "source_repo": version.source_repo,
        "source_path": version.source_path,
    }
    if opts.include_capabilities:
        d["capabilities"] = capabilities
    if opts.include_tags:
        d["tags"] = tags
    if opts.include_dependencies:
        d["declared_dependencies"] = version.declared_dependencies
        d["inferred_dependencies"] = version.inferred_dependencies
    if opts.include_quality:
        d["quality"] = version.quality
        d["security"] = version.security
        d["license"] = version.license
    if opts.include_raw_content:
        d["raw_content"] = version.raw_content
    return d


def export_json(
    session: Session,
    output_path: str,
    opts: ExportOptions | None = None,
) -> dict:
    """Export to v3-compatible JSON format."""
    opts = opts or ExportOptions()
    versions = _build_query(session, opts).all()

    skills_out = []
    for v in versions:
        caps = (
            session.query(CapabilityRow.canonical, CapabilityRow.name).filter(CapabilityRow.version_id_fk == v.id).all()
        )
        tags = session.query(TagRow.name).filter(TagRow.version_id_fk == v.id).all()
        skills_out.append(
            _version_to_dict(
                v,
                [c.canonical or c.name for c in caps],
                [t.name for t in tags],
                opts,
            )
        )

    data = {
        "schema_version": "3.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "total_skills": len(skills_out),
        "export_options": {
            "domain": opts.domain,
            "category": opts.category,
            "min_quality": opts.min_quality,
            "repo": opts.repo,
        },
        "skills": skills_out,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    return {"format": "json", "path": output_path, "count": len(skills_out)}


def export_markdown(
    session: Session,
    output_path: str,
    opts: ExportOptions | None = None,
) -> dict:
    """Export as a Markdown catalog."""
    opts = opts or ExportOptions()
    versions = _build_query(session, opts).all()

    lines = [
        "# SkillsBank Registry Catalog",
        "",
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Total skills: {len(versions)}",
        "",
    ]

    # Group by domain
    by_domain: dict[str, list] = {}
    for v in versions:
        domain = v.domain_primary or "uncategorized"
        by_domain.setdefault(domain, []).append(v)

    for domain in sorted(by_domain.keys()):
        skills = by_domain[domain]
        lines.append(f"## {domain.replace('_', ' ').title()} ({len(skills)})")
        lines.append("")
        for v in sorted(skills, key=lambda x: x.name or ""):
            lines.append(f"### {v.name}")
            lines.append("")
            if v.summary:
                lines.append(f"> {v.summary}")
                lines.append("")
            lines.append(f"- **ID**: `{v.skill_id}`")
            lines.append(f"- **Repo**: {v.source_repo}")
            if v.source_path:
                lines.append(f"- **Path**: `{v.source_path}`")

            # Capabilities
            if opts.include_capabilities:
                caps = (
                    session.query(CapabilityRow.canonical, CapabilityRow.name)
                    .filter(CapabilityRow.version_id_fk == v.id)
                    .all()
                )
                if caps:
                    cap_names = [c.canonical or c.name for c in caps[:10]]
                    lines.append(f"- **Capabilities**: {', '.join(cap_names)}")

            # Tags
            if opts.include_tags:
                tags = session.query(TagRow.name).filter(TagRow.version_id_fk == v.id).all()
                if tags:
                    tag_names = [t.name for t in tags[:10]]
                    lines.append(f"- **Tags**: {', '.join(tag_names)}")

            # Quality
            if opts.include_quality and v.quality:
                q = v.quality
                if isinstance(q, dict):
                    score = q.get("overall_score")
                    if score is not None:
                        lines.append(f"- **Quality**: {score:.2f}/1.0")

            lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return {"format": "markdown", "path": output_path, "count": len(versions)}


def export_csv(
    session: Session,
    output_path: str,
    opts: ExportOptions | None = None,
) -> dict:
    """Export as CSV."""
    opts = opts or ExportOptions()
    versions = _build_query(session, opts).all()

    fieldnames = [
        "id",
        "name",
        "display_name",
        "summary",
        "domain",
        "source_repo",
        "source_path",
    ]
    if opts.include_capabilities:
        fieldnames.append("capabilities")
    if opts.include_tags:
        fieldnames.append("tags")
    if opts.include_dependencies:
        fieldnames.extend(["declared_deps", "inferred_deps"])
    if opts.include_quality:
        fieldnames.extend(["quality_score", "security_risk", "license_type"])

    rows = []
    for v in versions:
        row: dict = {
            "id": v.skill_id,
            "name": v.name,
            "display_name": v.display_name,
            "summary": v.summary,
            "domain": v.domain_primary,
            "source_repo": v.source_repo,
            "source_path": v.source_path,
        }
        if opts.include_capabilities:
            caps = (
                session.query(CapabilityRow.canonical, CapabilityRow.name)
                .filter(CapabilityRow.version_id_fk == v.id)
                .all()
            )
            row["capabilities"] = "|".join(c.canonical or c.name for c in caps)
        if opts.include_tags:
            tags = session.query(TagRow.name).filter(TagRow.version_id_fk == v.id).all()
            row["tags"] = "|".join(t.name for t in tags)
        if opts.include_dependencies:
            row["declared_deps"] = json.dumps(v.declared_dependencies or {})
            row["inferred_deps"] = json.dumps(v.inferred_dependencies or {})
        if opts.include_quality:
            q = v.quality or {}
            row["quality_score"] = q.get("overall_score", "") if isinstance(q, dict) else ""
            s = v.security or {}
            row["security_risk"] = s.get("risk_level", "") if isinstance(s, dict) else ""
            l = v.license or {}
            row["license_type"] = l.get("type", "") if isinstance(l, dict) else ""
        rows.append(row)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return {"format": "csv", "path": output_path, "count": len(versions)}


def export_json_string(
    session: Session,
    opts: ExportOptions | None = None,
) -> str:
    """Export to JSON string (for API responses)."""
    opts = opts or ExportOptions()
    versions = _build_query(session, opts).all()

    skills_out = []
    for v in versions:
        caps = (
            session.query(CapabilityRow.canonical, CapabilityRow.name).filter(CapabilityRow.version_id_fk == v.id).all()
        )
        tags = session.query(TagRow.name).filter(TagRow.version_id_fk == v.id).all()
        skills_out.append(
            _version_to_dict(
                v,
                [c.canonical or c.name for c in caps],
                [t.name for t in tags],
                opts,
            )
        )

    data = {
        "schema_version": "3.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "total_skills": len(skills_out),
        "skills": skills_out,
    }
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def get_export_stats(session: Session) -> dict:
    """Get counts for export preview."""
    total_skills = session.query(SkillRow).filter(SkillRow.lifecycle != "archived").count()
    total_versions = session.query(VersionRow).count()
    domains = session.query(VersionRow.domain_primary, func.count()).group_by(VersionRow.domain_primary).all()
    repos = session.query(RepoRow).count()
    return {
        "total_skills": total_skills,
        "total_versions": total_versions,
        "total_repos": repos,
        "domains": {d: c for d, c in domains if d},
    }
