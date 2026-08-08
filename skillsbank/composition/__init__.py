"""Skill composition: combine multiple skills into composite workflows."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session

from skillsbank.db.persistence_models import (
    CapabilityRow,
    RepoRow,
    SkillRow,
    VersionRow,
)
from skillsbank.deps.extractor import extract_from_version


class CompositionStrategy(str, Enum):
    SEQUENTIAL = "sequential"  # Run skills one after another
    PARALLEL = "parallel"  # Run skills concurrently
    PIPELINE = "pipeline"  # Output of one feeds into next
    CONDITIONAL = "conditional"  # Choose based on condition


class ConflictResolution(str, Enum):
    FAIL = "fail"  # Fail on any conflict
    WARN = "warn"  # Warn but proceed
    PREFER_FIRST = "prefer_first"  # First skill wins
    PREFER_LAST = "prefer_last"  # Last skill wins
    MERGE = "merge"  # Attempt to merge


@dataclass
class ComponentSkill:
    skill_id: str
    name: str
    order: int
    condition: str = ""  # For conditional composition
    input_mapping: dict[str, str] = field(default_factory=dict)  # Map prev output → this input
    config: dict[str, object] = field(default_factory=dict)


@dataclass
class CompositionConflict:
    conflict_type: str  # "dependency", "capability_overlap", "incompatible_runtime", "io_mismatch"
    description: str
    skill_a: str
    skill_b: str
    severity: str  # "error", "warning"
    resolution: str = ""


@dataclass
class CompositeSkill:
    name: str
    description: str
    strategy: CompositionStrategy
    components: list[ComponentSkill]
    conflicts: list[CompositionConflict] = field(default_factory=list)
    merged_capabilities: list[str] = field(default_factory=list)
    merged_dependencies: dict[str, list[str]] = field(default_factory=dict)
    pipeline_input: dict[str, object] = field(default_factory=dict)
    pipeline_output: dict[str, object] = field(default_factory=dict)
    is_valid: bool = True


@dataclass
class CompositionResult:
    composite: CompositeSkill
    install_order: list[str]  # skill_ids in recommended install order
    warnings: list[str]
    total_components: int
    unique_repos: int


# ── Conflict detection ───────────────────────────────────────────────────


def _detect_conflicts(
    session: Session,
    skill_ids: list[str],
    resolution: ConflictResolution,
) -> list[CompositionConflict]:
    """Detect conflicts between skills in a composition."""
    conflicts: list[CompositionConflict] = []

    # Gather data for each skill
    skill_data: dict[str, dict] = {}
    for sid in skill_ids:
        version = session.query(VersionRow).filter(VersionRow.skill_id == sid).first()
        if not version:
            conflicts.append(
                CompositionConflict(
                    conflict_type="missing_skill",
                    description=f"Skill {sid} not found in database",
                    skill_a=sid,
                    skill_b="",
                    severity="error",
                )
            )
            continue

        caps = (
            session.query(CapabilityRow.canonical, CapabilityRow.name)
            .filter(CapabilityRow.version_id_fk == version.id)
            .all()
        )
        deps = version.inferred_dependencies or {}
        declared = version.declared_dependencies or {}

        skill_data[sid] = {
            "name": version.name,
            "domain": version.domain_primary,
            "capabilities": {c.canonical or c.name for c in caps},
            "deps": deps,
            "declared_deps": declared,
            "format": version.input_format or version.output_format,
        }

    # Check for capability overlaps
    for i, sid_a in enumerate(skill_ids):
        if sid_a not in skill_data:
            continue
        for sid_b in skill_ids[i + 1 :]:
            if sid_b not in skill_data:
                continue
            caps_a = skill_data[sid_a]["capabilities"]
            caps_b = skill_data[sid_b]["capabilities"]
            overlap = caps_a & caps_b
            if overlap:
                severity = "warning" if resolution in (ConflictResolution.WARN, ConflictResolution.MERGE) else "error"
                conflicts.append(
                    CompositionConflict(
                        conflict_type="capability_overlap",
                        description=f"Overlapping capabilities: {', '.join(sorted(overlap)[:5])}",
                        skill_a=sid_a,
                        skill_b=sid_b,
                        severity=severity,
                        resolution=resolution.value if severity == "warning" else "",
                    )
                )

    # Check for dependency conflicts
    all_tools: dict[str, list[str]] = {}  # tool → [skill_ids that need it]
    for sid in skill_ids:
        if sid not in skill_data:
            continue
        deps = skill_data[sid]["deps"]
        if isinstance(deps, dict):
            for tool in deps.get("tools", []):
                tool_name = tool if isinstance(tool, str) else tool.get("name", "")
                if tool_name:
                    all_tools.setdefault(tool_name, []).append(sid)

    # Check for incompatible runtimes
    runtimes_seen: dict[str, list[str]] = {}
    for sid in skill_ids:
        if sid not in skill_data:
            continue
        deps = skill_data[sid]["deps"]
        if isinstance(deps, dict):
            for rt in deps.get("runtimes", []):
                rt_name = rt if isinstance(rt, str) else rt.get("name", "")
                if rt_name:
                    runtimes_seen.setdefault(rt_name, []).append(sid)

    return conflicts


# ── Merge functions ──────────────────────────────────────────────────────


def _merge_capabilities(
    session: Session,
    skill_ids: list[str],
) -> list[str]:
    """Merge capabilities from all skills, deduplicating."""
    all_caps: set[str] = set()
    for sid in skill_ids:
        version = session.query(VersionRow).filter(VersionRow.skill_id == sid).first()
        if not version:
            continue
        caps = (
            session.query(CapabilityRow.canonical, CapabilityRow.name)
            .filter(CapabilityRow.version_id_fk == version.id)
            .all()
        )
        for c in caps:
            all_caps.add(c.canonical or c.name)
    return sorted(all_caps)


def _merge_dependencies(
    session: Session,
    skill_ids: list[str],
) -> dict[str, list[str]]:
    """Merge dependencies from all skills, categorizing."""
    merged: dict[str, set[str]] = {
        "tools": set(),
        "packages": set(),
        "apis": set(),
        "runtimes": set(),
        "env_vars": set(),
    }
    for sid in skill_ids:
        version = session.query(VersionRow).filter(VersionRow.skill_id == sid).first()
        if not version:
            continue
        deps = version.inferred_dependencies or {}
        if isinstance(deps, dict):
            for cat in merged:
                items = deps.get(cat, [])
                for item in items:
                    name = item if isinstance(item, str) else item.get("name", "")
                    if name:
                        merged[cat].add(name)
    return {k: sorted(v) for k, v in merged.items() if v}


# ── Topological sort for pipeline ───────────────────────────────────────


def _topological_sort(
    session: Session,
    skill_ids: list[str],
    strategy: CompositionStrategy,
) -> list[str]:
    """Determine optimal ordering for skill installation/execution.

    For SEQUENTIAL: respect input_mapping order.
    For PIPELINE: topological sort based on I/O compatibility.
    For PARALLEL: no ordering needed, return as-is.
    For CONDITIONAL: respect component order.
    """
    if strategy == CompositionStrategy.PARALLEL:
        return list(skill_ids)

    # For pipeline, try to order by I/O compatibility
    if strategy == CompositionStrategy.PIPELINE:
        # Simple heuristic: skills that produce output go before those that consume
        # For now, just return in the order provided
        return list(skill_ids)

    return list(skill_ids)


# ── Main composition function ────────────────────────────────────────────


def compose_skills(
    session: Session,
    skill_ids: list[str],
    name: str = "",
    description: str = "",
    strategy: CompositionStrategy = CompositionStrategy.SEQUENTIAL,
    conflict_resolution: ConflictResolution = ConflictResolution.WARN,
    component_configs: list[dict[str, object]] | None = None,
) -> CompositionResult:
    """Compose multiple skills into a composite workflow.

    Args:
        session: Database session
        skill_ids: Ordered list of skill IDs to compose
        name: Name for the composite skill
        description: Description of the composite
        strategy: How skills should be orchestrated
        conflict_resolution: How to handle conflicts
        component_configs: Per-component configuration overrides
    """
    if not skill_ids:
        return CompositionResult(
            composite=CompositeSkill(
                name=name or "empty",
                description=description,
                strategy=strategy,
                components=[],
                is_valid=False,
            ),
            install_order=[],
            warnings=["No skills provided"],
            total_components=0,
            unique_repos=0,
        )

    # Detect conflicts
    conflicts = _detect_conflicts(session, skill_ids, conflict_resolution)
    has_errors = any(c.severity == "error" for c in conflicts)

    # Build components
    components = []
    for i, sid in enumerate(skill_ids):
        version = session.query(VersionRow).filter(VersionRow.skill_id == sid).first()
        config = component_configs[i] if component_configs and i < len(component_configs) else {}
        components.append(
            ComponentSkill(
                skill_id=sid,
                name=version.name if version else sid,
                order=i,
                condition=config.get("condition", ""),
                input_mapping=config.get("input_mapping", {}),
                config=config,
            )
        )

    # Merge capabilities and dependencies
    merged_caps = _merge_capabilities(session, skill_ids)
    merged_deps = _merge_dependencies(session, skill_ids)

    # Determine install order
    install_order = _topological_sort(session, skill_ids, strategy)

    # Count unique repos
    repos: set[str] = set()
    for sid in skill_ids:
        version = session.query(VersionRow.source_repo).filter(VersionRow.skill_id == sid).first()
        if version and version.source_repo:
            repos.add(version.source_repo)

    # Generate name/description if not provided
    if not name:
        names = []
        for sid in skill_ids[:3]:
            version = session.query(VersionRow.name).filter(VersionRow.skill_id == sid).first()
            if version:
                names.append(version.name)
        name = " + ".join(names) + ("..." if len(skill_ids) > 3 else "")

    if not description:
        description = f"Composite {strategy.value} skill with {len(skill_ids)} components"

    # Build pipeline I/O shapes
    pipeline_input: dict[str, object] = {}
    pipeline_output: dict[str, object] = {}
    if strategy == CompositionStrategy.PIPELINE and skill_ids:
        first_version = (
            session.query(VersionRow.input_format, VersionRow.input_json_schema)
            .filter(VersionRow.skill_id == skill_ids[0])
            .first()
        )
        last_version = (
            session.query(VersionRow.output_format, VersionRow.output_json_schema)
            .filter(VersionRow.skill_id == skill_ids[-1])
            .first()
        )
        if first_version:
            pipeline_input = {
                "format": first_version.input_format,
                "schema": first_version.input_json_schema,
            }
        if last_version:
            pipeline_output = {
                "format": last_version.output_format,
                "schema": last_version.output_json_schema,
            }

    composite = CompositeSkill(
        name=name,
        description=description,
        strategy=strategy,
        components=components,
        conflicts=conflicts,
        merged_capabilities=merged_caps,
        merged_dependencies=merged_deps,
        pipeline_input=pipeline_input,
        pipeline_output=pipeline_output,
        is_valid=not has_errors,
    )

    warnings = []
    if has_errors:
        error_conflicts = [c for c in conflicts if c.severity == "error"]
        warnings.append(f"{len(error_conflicts)} error(s) detected; composition is invalid")
    if conflict_resolution == ConflictResolution.WARN:
        warn_conflicts = [c for c in conflicts if c.severity == "warning"]
        if warn_conflicts:
            warnings.append(f"{len(warn_conflicts)} warning(s) detected")

    return CompositionResult(
        composite=composite,
        install_order=install_order,
        warnings=warnings,
        total_components=len(components),
        unique_repos=len(repos),
    )


def get_composition_summary(result: CompositionResult) -> dict[str, object]:
    """Get a summary dict of a composition result."""
    c = result.composite
    return {
        "name": c.name,
        "strategy": c.strategy.value,
        "total_components": result.total_components,
        "unique_repos": result.unique_repos,
        "is_valid": c.is_valid,
        "conflicts": len(c.conflicts),
        "errors": len([x for x in c.conflicts if x.severity == "error"]),
        "warnings_count": len(result.warnings),
        "merged_capabilities": len(c.merged_capabilities),
        "merged_dependencies": {k: len(v) for k, v in c.merged_dependencies.items()},
        "install_order": result.install_order,
        "pipeline_input_format": c.pipeline_input.get("format"),
        "pipeline_output_format": c.pipeline_output.get("format"),
    }


def suggest_compositions(
    session: Session,
    task: str,
    limit: int = 5,
) -> list[CompositionResult]:
    """Suggest skill compositions for a given task.

    Uses the recommender to find relevant skills, then tries common
    composition patterns.
    """
    from skillsbank.recommender import _extract_task_keywords, recommend

    task_keywords = _extract_task_keywords(task)
    if not task_keywords:
        return []

    # Get recommendations
    recs = recommend(session, task=task, limit=10)
    if len(recs.recommendations) < 2:
        return []

    suggestions: list[CompositionResult] = []

    # Try pairwise compositions
    for i in range(min(len(recs.recommendations), limit)):
        for j in range(i + 1, min(len(recs.recommendations), limit)):
            pair = [recs.recommendations[i].skill_id, recs.recommendations[j].skill_id]
            result = compose_skills(
                session,
                pair,
                strategy=CompositionStrategy.SEQUENTIAL,
                conflict_resolution=ConflictResolution.WARN,
            )
            if result.composite.is_valid:
                suggestions.append(result)

    # Sort by fewest conflicts, most capabilities
    suggestions.sort(
        key=lambda s: (
            len(s.composite.conflicts),
            -len(s.composite.merged_capabilities),
        )
    )

    return suggestions[:limit]
