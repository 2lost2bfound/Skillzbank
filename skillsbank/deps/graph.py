"""Dependency graph operations.

Builds and queries dependency relationships between skills.
Detects conflicts, circular dependencies, and transitive dependencies.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from skillsbank.deps.extractor import DepType, ExtractedDependency


@dataclass
class ConflictInfo:
    """A dependency conflict between two skills."""

    dep_name: str
    skill_a_id: str
    skill_a_constraint: str | None
    skill_b_id: str
    skill_b_constraint: str | None
    conflict_type: str  # "version", "exclusive", "incompatible"
    description: str = ""


@dataclass
class DepNode:
    """A node in the dependency graph."""

    skill_id: str
    skill_name: str
    dependencies: list[ExtractedDependency] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)  # skills that depend on this


class DependencyGraph:
    """In-memory dependency graph for skill analysis.

    Nodes are skills. Edges represent dependency relationships:
    - Skill A -> Skill B means A depends on B (B is a dependency of A)
    - Skill A -> Tool/Package/API means A requires that external resource
    """

    def __init__(self) -> None:
        self._nodes: dict[str, DepNode] = {}
        self._edges: dict[str, list[str]] = defaultdict(list)  # skill_id -> [dep_skill_ids]
        self._reverse_edges: dict[str, list[str]] = defaultdict(list)  # dep_skill_id -> [skill_ids]
        self._external_deps: dict[str, list[ExtractedDependency]] = defaultdict(list)  # skill_id -> external deps

    def add_skill(self, skill_id: str, skill_name: str, dependencies: list[ExtractedDependency]) -> None:
        """Add a skill with its dependencies to the graph."""
        if skill_id in self._nodes:
            self._nodes[skill_id].dependencies = dependencies
        else:
            self._nodes[skill_id] = DepNode(
                skill_id=skill_id,
                skill_name=skill_name,
                dependencies=dependencies,
            )

        # Store raw deps; resolve_edges() will build edges later
        self._nodes[skill_id].dependencies = dependencies
        # Classify external deps immediately
        self._external_deps[skill_id] = [d for d in dependencies if d.dep_type != DepType.PACKAGE]

    def resolve_edges(self) -> None:
        """Resolve all skill-skill edges after all skills are added.

        Must be called after all add_skill calls. Handles cross-references
        that weren't available during individual add_skill calls.
        """
        skill_names = {n.skill_name.lower(): n.skill_id for n in self._nodes.values()}
        self._edges.clear()
        self._reverse_edges.clear()
        self._external_deps.clear()

        for sid, node in self._nodes.items():
            for dep in node.dependencies:
                if dep.dep_type == DepType.PACKAGE:
                    target_id = skill_names.get(dep.name.lower())
                    if target_id and target_id != sid:
                        self._edges[sid].append(target_id)
                        self._reverse_edges[target_id].append(sid)
                        if sid not in self._nodes[target_id].dependents:
                            self._nodes[target_id].dependents.append(sid)
                    else:
                        self._external_deps[sid].append(dep)
                else:
                    self._external_deps[sid].append(dep)

    def _find_skill_by_name(self, name: str) -> str | None:
        """Find skill ID by name (case-insensitive)."""
        name_lower = name.lower()
        for node in self._nodes.values():
            if node.skill_name.lower() == name_lower:
                return node.skill_id
        return None

    def get_direct_dependencies(self, skill_id: str) -> list[str]:
        """Get direct skill dependencies."""
        return list(self._edges.get(skill_id, []))

    def get_dependents(self, skill_id: str) -> list[str]:
        """Get skills that depend on this skill."""
        return list(self._reverse_edges.get(skill_id, []))

    def get_transitive_dependencies(self, skill_id: str) -> set[str]:
        """Get all transitive skill dependencies (BFS)."""
        visited: set[str] = set()
        queue = deque(self._edges.get(skill_id, []))
        while queue:
            dep = queue.popleft()
            if dep not in visited:
                visited.add(dep)
                queue.extend(self._edges.get(dep, []))
        return visited

    def get_transitive_dependents(self, skill_id: str) -> set[str]:
        """Get all skills that transitively depend on this skill."""
        visited: set[str] = set()
        queue = deque(self._reverse_edges.get(skill_id, []))
        while queue:
            dep = queue.popleft()
            if dep not in visited:
                visited.add(dep)
                queue.extend(self._reverse_edges.get(dep, []))
        return visited

    def detect_cycles(self) -> list[list[str]]:
        """Detect circular dependency chains using Tarjan's algorithm."""
        index_counter = [0]
        stack: list[str] = []
        on_stack: set[str] = set()
        indices: dict[str, int] = {}
        lowlinks: dict[str, int] = {}
        cycles: list[list[str]] = []

        def strongconnect(v: str) -> None:
            indices[v] = index_counter[0]
            lowlinks[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack.add(v)

            for w in self._edges.get(v, []):
                if w not in indices:
                    strongconnect(w)
                    lowlinks[v] = min(lowlinks[v], lowlinks[w])
                elif w in on_stack:
                    lowlinks[v] = min(lowlinks[v], indices[w])

            if lowlinks[v] == indices[v]:
                component: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    component.append(w)
                    if w == v:
                        break
                if len(component) > 1:
                    cycles.append(component)

        for node_id in self._nodes:
            if node_id not in indices:
                strongconnect(node_id)

        return cycles

    def detect_conflicts(self) -> list[ConflictInfo]:
        """Detect dependency conflicts between skills.

        Checks for:
        - Version conflicts: same package, incompatible version constraints
        - Exclusive conflicts: mutually exclusive tools
        """
        conflicts: list[ConflictInfo] = []

        # Group external deps by name
        dep_owners: dict[str, list[tuple[str, ExtractedDependency]]] = defaultdict(list)
        for skill_id, deps in self._external_deps.items():
            for dep in deps:
                dep_owners[dep.name.lower()].append((skill_id, dep))

        # Check for version conflicts
        for dep_name, owners in dep_owners.items():
            if len(owners) < 2:
                continue
            # Check if same dep type with different version constraints
            by_type: dict[DepType, list[tuple[str, ExtractedDependency]]] = defaultdict(list)
            for skill_id, dep in owners:
                by_type[dep.dep_type].append((skill_id, dep))

            for type_owners in by_type.values():
                if len(type_owners) < 2:
                    continue
                # Simple version conflict detection
                constrained = [(sid, d) for sid, d in type_owners if d.version_constraint]
                if len(constrained) >= 2:
                    for i in range(len(constrained)):
                        for j in range(i + 1, len(constrained)):
                            sid_a, dep_a = constrained[i]
                            sid_b, dep_b = constrained[j]
                            if dep_a.version_constraint != dep_b.version_constraint:
                                conflicts.append(
                                    ConflictInfo(
                                        dep_name=dep_name,
                                        skill_a_id=sid_a,
                                        skill_a_constraint=dep_a.version_constraint,
                                        skill_b_id=sid_b,
                                        skill_b_constraint=dep_b.version_constraint,
                                        conflict_type="version",
                                        description=(
                                            f"Version conflict on {dep_name}: "
                                            f"{sid_a} requires {dep_a.version_constraint}, "
                                            f"{sid_b} requires {dep_b.version_constraint}"
                                        ),
                                    )
                                )

        return conflicts

    def get_external_dependencies(self, skill_id: str) -> list[ExtractedDependency]:
        """Get external (non-skill) dependencies for a skill."""
        return list(self._external_deps.get(skill_id, []))

    def get_stats(self) -> dict[str, Any]:
        """Get graph statistics."""
        total_edges = sum(len(v) for v in self._edges.values())
        total_external = sum(len(v) for v in self._external_deps.values())
        return {
            "total_skills": len(self._nodes),
            "total_skill_edges": total_edges,
            "total_external_deps": total_external,
            "skills_with_dependencies": len(self._edges),
            "skills_with_dependents": len(self._reverse_edges),
            "cycles_detected": len(self.detect_cycles()),
        }

    @classmethod
    def from_versions(
        cls,
        versions: list[dict[str, Any]],
        *,
        include_env_vars: bool = False,
    ) -> DependencyGraph:
        """Build a dependency graph from v3 version dicts.

        Args:
            versions: List of version dicts from registry.v3.json
            include_env_vars: Whether to include env var requirements

        Returns:
            Populated DependencyGraph
        """
        from skillsbank.deps.extractor import extract_from_version

        graph = cls()

        # First pass: add all skills
        for v in versions:
            skill_id = v.get("skill_id", "")
            name = v.get("name", "")
            if skill_id and name:
                graph._nodes[skill_id] = DepNode(
                    skill_id=skill_id,
                    skill_name=name,
                )

        # Second pass: extract dependencies and add to graph
        for v in versions:
            skill_id = v.get("skill_id", "")
            if not skill_id:
                continue
            deps = extract_from_version(v, include_env_vars=include_env_vars)
            name = v.get("name", "")
            graph.add_skill(skill_id, name, deps)

        # Resolve cross-skill edges now that all skills are loaded
        graph.resolve_edges()

        return graph
