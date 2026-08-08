"""Sync extracted dependencies to SQLite.

Updates VersionRow declared/inferred_dependencies with parsed data.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from skillsbank.db.persistence_models import VersionRow
from skillsbank.deps.extractor import DepType, ExtractedDependency, extract_from_version


def _deps_to_db_format(deps: list[ExtractedDependency]) -> dict[str, list[dict[str, Any]]]:
    """Convert ExtractedDependency list to DB-compatible dict.

    Returns dict with keys: tools, apis, packages, env_vars, runtimes.
    Each key maps to a list of {name, version_constraint?, ecosystem?, confidence, source, context?}.
    """
    result: dict[str, list[dict[str, Any]]] = {
        "tools": [],
        "apis": [],
        "packages": [],
        "env_vars": [],
        "runtimes": [],
    }

    type_to_key = {
        DepType.TOOL: "tools",
        DepType.API: "apis",
        DepType.PACKAGE: "packages",
        DepType.ENV_VAR: "env_vars",
        DepType.RUNTIME: "runtimes",
    }

    for dep in deps:
        key = type_to_key.get(dep.dep_type)
        if key:
            entry: dict[str, Any] = {
                "name": dep.name,
                "confidence": dep.confidence,
                "source": dep.source,
            }
            if dep.version_constraint:
                entry["version_constraint"] = dep.version_constraint
            if dep.ecosystem:
                entry["ecosystem"] = dep.ecosystem
            if dep.context:
                entry["context"] = dep.context
            result[key].append(entry)

    return result


def sync_dependencies_to_db(
    session: Session,
    *,
    include_env_vars: bool = False,
    min_confidence: float = 0.70,
) -> dict[str, int]:
    """Extract and sync dependencies for all versions in DB.

    Args:
        session: SQLAlchemy session
        include_env_vars: Whether to extract env var requirements
        min_confidence: Minimum confidence threshold

    Returns:
        Stats dict with counts
    """
    stats = {
        "versions_processed": 0,
        "versions_updated": 0,
        "total_deps_extracted": 0,
        "by_type": {"tools": 0, "apis": 0, "packages": 0, "env_vars": 0, "runtimes": 0},
    }

    session.execute(select(VersionRow).where(VersionRow.inferred_dependencies == None)).scalars().all()

    # Also process versions that have no inferred deps at all
    all_rows = session.execute(select(VersionRow)).scalars().all()

    for row in all_rows:
        stats["versions_processed"] += 1

        # Build version dict for extractor
        version_dict: dict[str, Any] = {
            "skill_id": row.skill_id,
            "name": row.name,
            "summary": row.summary,
            "long_description": row.long_description,
            "raw_content": row.raw_content,
            "declared_dependencies": row.declared_dependencies or {},
        }

        deps = extract_from_version(version_dict, include_env_vars=include_env_vars)
        deps = [d for d in deps if d.confidence >= min_confidence]

        if deps:
            db_format = _deps_to_db_format(deps)
            total = sum(len(v) for v in db_format.values())
            if total > 0:
                row.inferred_dependencies = db_format
                stats["versions_updated"] += 1
                stats["total_deps_extracted"] += total
                for k, v in db_format.items():
                    stats["by_type"][k] += len(v)

    session.commit()
    return stats


def get_dependency_summary(session: Session) -> dict[str, Any]:
    """Get summary of dependency data in DB.

    Returns dict with:
    - total_versions: count of versions
    - versions_with_declared: count with declared deps
    - versions_with_inferred: count with inferred deps
    - top_tools: most common tool dependencies
    - top_packages: most common package dependencies
    - top_apis: most common API dependencies
    """
    from collections import Counter

    all_versions = session.execute(select(VersionRow)).scalars().all()

    declared_count = 0
    inferred_count = 0
    tool_counter: Counter[str] = Counter()
    pkg_counter: Counter[str] = Counter()
    api_counter: Counter[str] = Counter()
    runtime_counter: Counter[str] = Counter()

    for row in all_versions:
        dd = row.declared_dependencies or {}
        id = row.inferred_dependencies or {}

        if any(dd.get(k) for k in ["tools", "apis", "packages", "env_vars", "runtimes"]):
            declared_count += 1

        if any(id.get(k) for k in ["tools", "apis", "packages", "env_vars", "runtimes"]):
            inferred_count += 1
            for item in id.get("tools", []):
                name = item.get("name", "") if isinstance(item, dict) else str(item)
                if name:
                    tool_counter[name] += 1
            for item in id.get("packages", []):
                name = item.get("name", "") if isinstance(item, dict) else str(item)
                if name:
                    pkg_counter[name] += 1
            for item in id.get("apis", []):
                name = item.get("name", "") if isinstance(item, dict) else str(item)
                if name:
                    api_counter[name] += 1
            for item in id.get("runtimes", []):
                name = item.get("name", "") if isinstance(item, dict) else str(item)
                if name:
                    runtime_counter[name] += 1

    return {
        "total_versions": len(all_versions),
        "versions_with_declared": declared_count,
        "versions_with_inferred": inferred_count,
        "top_tools": tool_counter.most_common(20),
        "top_packages": pkg_counter.most_common(20),
        "top_apis": api_counter.most_common(20),
        "top_runtimes": runtime_counter.most_common(10),
    }
