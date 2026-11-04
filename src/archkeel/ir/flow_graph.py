# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The call graph of a snapshot: seams, lanes, external touchpoints and paths (AD-291)."""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    Entity,
    EntityKind,
    PresenceKind,
    RelationshipKind,
    ResolutionKind,
)
from archkeel.ir.facts import Evidence
from archkeel.ir.interfaces import component_owners, owner_of
from archkeel.ir.model import Observation, Record


class SeamKind(StrEnum):
    # A process boundary is not detected: the author claims it (AD-291).
    PARTIAL_CALL = "partial_call"
    UNRESOLVED_CALL = "unresolved_call"


class ExternalSystem(StrEnum):
    REDIS = "redis"
    RELATIONAL_DATABASE = "relational_database"
    MONGODB = "mongodb"
    OBJECT_STORAGE = "object_storage"
    KAFKA = "kafka"
    RABBITMQ = "rabbitmq"


class Direction(StrEnum):
    READS = "reads"
    WRITES = "writes"
    READS_WRITES = "reads_writes"
    TOUCHES = "touches"


# The one catalog of client libraries. A module name equals a key or starts with `<key>.`.
_LIBRARIES: Final = {
    "redis": ExternalSystem.REDIS,
    "sqlalchemy": ExternalSystem.RELATIONAL_DATABASE,
    "pymongo": ExternalSystem.MONGODB,
    "boto3": ExternalSystem.OBJECT_STORAGE,
    "botocore": ExternalSystem.OBJECT_STORAGE,
    "minio": ExternalSystem.OBJECT_STORAGE,
    "azure.storage": ExternalSystem.OBJECT_STORAGE,
    "kafka": ExternalSystem.KAFKA,
    "pika": ExternalSystem.RABBITMQ,
}
_CALLABLES: Final = frozenset({EntityKind.FUNCTION, EntityKind.METHOD})
_NO_REASON: Final = "no reason recorded"
_REEXPORT: Final = "call through a re-export: the analysis does not follow it"
_TRUNCATED: Final = "partial call that lists only some of its candidates"
# `--max-hops` bound: the path walk recurses once for each hop.
MAX_HOPS: Final = 100
# Each expansion of the path search costs one; a search that spends them all is not complete.
WORK_LIMIT: Final = 200_000


@dataclass(frozen=True, slots=True)
class Site:
    """One observed place: the record that states it and its source line."""

    record_id: str
    evidence_id: str | None = None
    file: str | None = None
    line: int | None = None


@dataclass(frozen=True, slots=True)
class Seam:
    """A place where the call analysis cannot name the target of a call."""

    kind: SeamKind
    node: str
    reason: str | None
    candidates: int | None = None
    calls: int | None = None


@dataclass(frozen=True, slots=True)
class CallEdge:
    """Calls from one function to another. A resolved call proves it: then `seams` is empty.

    A partial call has one seam for each site, in the order of `sites`: the sites differ in
    candidates and reason.
    """

    source: str
    target: str
    sites: tuple[Site, ...]
    seams: tuple[Seam, ...] = ()

    @property
    def seam(self) -> Seam | None:
        """The seam of the first site; the edge as a whole is a claim when this is set."""
        return self.seams[0] if self.seams else None


@dataclass(frozen=True, slots=True)
class Function:
    name: str
    kind: EntityKind
    module: str
    entity_id: str
    defined_at: Site | None


def function_label(function: Function) -> str:
    """Readable source label; the qualified function name remains the stable identity."""
    symbol = function.name.removeprefix(f"{function.module}.")
    if function.defined_at is None:
        return function.name
    return f"{function.defined_at.file}:{function.defined_at.line} · {symbol}"


@dataclass(frozen=True, slots=True)
class Touch:
    """A module that imports a client library of an external system."""

    system: ExternalSystem
    module: str
    library: str
    site: Site


@dataclass(frozen=True, slots=True)
class CallGraph:
    functions: Mapping[str, Function]
    edges: Mapping[str, Mapping[str, CallEdge]]
    unresolved: Mapping[str, Seam]
    touches: Mapping[str, tuple[Touch, ...]]


@dataclass(frozen=True, slots=True)
class PathSearch:
    paths: tuple[tuple[CallEdge, ...], ...]
    complete: bool


def module_names(entities: Mapping[str, Entity]) -> dict[str, str]:
    """Map each entity id to the name of the module that contains it."""
    result: dict[str, str] = {}
    for identity, entity in entities.items():
        current: Entity | None = entity
        while current is not None and current.kind != EntityKind.MODULE:
            current = entities.get(current.parent_id) if current.parent_id else None
        if current is not None:
            result[identity] = current.qualified_name
    return result


def module_lanes(observation: Observation, modules: Iterable[str]) -> dict[str, str]:
    """The owning component, else the second name of the module: `cli` in `shop.cli.main`."""
    owners = component_owners(observation)
    return {name: owner_of(name, owners) or _second_name(name) for name in modules}


def _second_name(module: str) -> str:
    parts = module.split(".")
    return parts[1] if len(parts) > 1 else module


def _system_of(library: str, namespaces: frozenset[str]) -> ExternalSystem | None:
    # A first-party package that is named like a client library is not that library.
    if library.split(".")[0] in namespaces:
        return None
    return next(
        (
            system
            for name, system in _LIBRARIES.items()
            if library == name or library.startswith(f"{name}.")
        ),
        None,
    )


def _unresolved_seam(node: str, reasons: Counter[str]) -> Seam:
    reason = min(reasons, key=lambda item: (-reasons[item], item))
    return Seam(SeamKind.UNRESOLVED_CALL, node, reason, calls=sum(reasons.values()))


def _site(record_id: str, evidence_ids: Sequence[str], evidence: Mapping[str, Evidence]) -> Site:
    first = evidence.get(evidence_ids[0]) if evidence_ids else None
    return Site(record_id, first.id, first.file, first.line) if first else Site(record_id)


def _edges(
    graph: ArchitectureGraph,
    names: Mapping[str, str],
    evidence: Mapping[str, Evidence],
    reexports: frozenset[str],
) -> tuple[dict[str, dict[str, CallEdge]], dict[str, Seam]]:
    proven: dict[tuple[str, str], list[Site]] = {}
    guessed: dict[tuple[str, str], list[tuple[Site, Seam]]] = {}
    reasons: dict[str, Counter[str]] = {}
    for item in graph.relationships:
        source = names.get(item.source_id)
        if item.kind != RelationshipKind.CALLS or source is None:
            continue
        site = _site(item.id, item.evidence_ids, evidence)
        if item.resolution == ResolutionKind.RESOLVED:
            target = names.get(item.target_id) if item.target_id else None
            if target is not None:
                proven.setdefault((source, target), []).append(site)
            elif item.target_id in reexports:
                reasons.setdefault(source, Counter())[_REEXPORT] += 1
        elif item.resolution == ResolutionKind.PARTIAL:
            count = item.candidate_count if item.candidate_count is not None else 0
            seam = Seam(SeamKind.PARTIAL_CALL, source, item.reason, candidates=count)
            for candidate in item.candidate_ids:
                if (target := names.get(candidate)) is not None:
                    guessed.setdefault((source, target), []).append((site, seam))
            if item.candidates_truncated:
                reasons.setdefault(source, Counter())[_TRUNCATED] += 1
        elif item.resolution == ResolutionKind.UNRESOLVED:
            reasons.setdefault(source, Counter())[item.reason or _NO_REASON] += 1
    edges: dict[str, dict[str, CallEdge]] = {}
    # A resolved call proves the pair; a partial call to the same pair adds nothing.
    for (source, target), partial in sorted(guessed.items()):
        if (source, target) not in proven:
            sites, seams = zip(*partial, strict=True)
            edges.setdefault(source, {})[target] = CallEdge(source, target, sites, seams)
    for (source, target), resolved_sites in sorted(proven.items()):
        edges.setdefault(source, {})[target] = CallEdge(source, target, tuple(resolved_sites))
    ordered = {source: dict(sorted(row.items())) for source, row in sorted(edges.items())}
    return ordered, {node: _unresolved_seam(node, found) for node, found in sorted(reasons.items())}


def _touches(
    imports: Iterable[Record], evidence: Mapping[str, Evidence], namespaces: frozenset[str]
) -> dict[str, tuple[Touch, ...]]:
    found: dict[str, list[Touch]] = {}
    for record in imports:
        module, library = record.data.get("source_module"), record.data.get("target_module")
        if not isinstance(module, str) or not isinstance(library, str):
            continue
        system = _system_of(library, namespaces)
        if system is None or record.data.get("under_type_checking") is True:
            continue
        site = _site(record.id, record.evidence_ids, evidence)
        found.setdefault(module, []).append(Touch(system, module, library, site))
    return {
        module: tuple(
            sorted(
                items,
                key=lambda t: (
                    t.system,
                    t.library,
                    t.site.file or "",
                    t.site.line or 0,
                    t.site.record_id,
                ),
            )
        )
        for module, items in sorted(found.items())
    }


def build_call_graph(graph: ArchitectureGraph, imports: Iterable[Record] = ()) -> CallGraph:
    """Lift the call relationships between defined functions and methods onto their names."""
    entities = {entity.id: entity for entity in graph.entities}
    module_of = module_names(entities)
    evidence = {item.id: item for item in graph.evidence}
    names: dict[str, str] = {}
    functions: dict[str, Function] = {}
    for entity in graph.entities:
        if (
            entity.kind in _CALLABLES
            and entity.presence == PresenceKind.DEFINED
            and entity.id in module_of
        ):
            names[entity.id] = entity.qualified_name
            defined = _site(entity.id, entity.evidence_ids, evidence)
            functions.setdefault(
                entity.qualified_name,
                Function(
                    entity.qualified_name, entity.kind, module_of[entity.id], entity.id, defined
                ),
            )
    namespaces = frozenset(name.split(".")[0] for name in module_of.values())
    # A defined first-party name that is only referenced is a re-export, such as `shop.store.X`.
    reexports = frozenset(
        entity.id
        for entity in graph.entities
        if entity.presence == PresenceKind.REFERENCED
        and entity.qualified_name.split(".")[0] in namespaces
    )
    edges, unresolved = _edges(graph, names, evidence, reexports)
    return CallGraph(functions, edges, unresolved, _touches(imports, evidence, namespaces))


def touchpoints(calls: CallGraph, node: str) -> tuple[Touch, ...]:
    """External-client imports in the module of the node, or of a function it calls (resolved)."""
    function = calls.functions.get(node)
    modules = {node} if function is None else {function.module}
    if function is not None:
        modules |= {
            calls.functions[target].module
            for target, edge in calls.edges.get(node, {}).items()
            if edge.seam is None
        }
    return tuple(touch for module in sorted(modules) for touch in calls.touches.get(module, ()))


@dataclass(slots=True)
class _Work:
    left: int


def _distances(calls: CallGraph, target: str, *, proven_only: bool) -> dict[str, int]:
    """Hops from each function to the target, by a reverse breadth-first search."""
    incoming: dict[str, list[str]] = {}
    for source, row in calls.edges.items():
        for name, edge in row.items():
            if edge.seam is None or not proven_only:
                incoming.setdefault(name, []).append(source)
    distance = {target: 0}
    queue = deque([target])
    while queue:
        node = queue.popleft()
        for previous in incoming.get(node, ()):
            if previous not in distance:
                distance[previous] = distance[node] + 1
                queue.append(previous)
    return distance


def _walk(
    calls: CallGraph,
    node: str,
    target: str,
    left: int,
    distance: Mapping[str, int],
    proven_only: bool,
    trail: list[CallEdge],
    visited: set[str],
    work: _Work,
) -> Iterator[tuple[CallEdge, ...]]:
    """Yield each simple path from `node` to the target with exactly `left` more hops."""
    if node == target:
        if left == 0:
            yield tuple(trail)
        return
    for name, edge in calls.edges.get(node, {}).items():
        if work.left <= 0:
            return
        if name in visited or distance.get(name, left) > left - 1:
            continue
        if proven_only and edge.seam is not None:
            continue
        work.left -= 1
        visited.add(name)
        trail.append(edge)
        yield from _walk(calls, name, target, left - 1, distance, proven_only, trail, visited, work)
        trail.pop()
        visited.remove(name)


def _paths_to(
    calls: CallGraph, source: str, target: str, max_paths: int, max_hops: int, work: _Work
) -> list[tuple[CallEdge, ...]]:
    found: dict[tuple[str, ...], tuple[CallEdge, ...]] = {}
    # Paths over resolved calls only come first; the second pass adds those that cross a seam.
    for proven_only in (True, False):
        distance = _distances(calls, target, proven_only=proven_only)
        for hops in range(distance.get(source, max_hops + 1), max_hops + 1):
            walk = _walk(calls, source, target, hops, distance, proven_only, [], {source}, work)
            for path in walk:
                found.setdefault(tuple(edge.target for edge in path), path)
                if len(found) == max_paths:
                    return list(found.values())
            if work.left <= 0:
                return list(found.values())
    return list(found.values())


def _farthest(
    calls: CallGraph, source: str, max_paths: int, max_hops: int
) -> list[tuple[CallEdge, ...]]:
    """Without a target: the shortest resolved path to each of the farthest functions."""
    reached: dict[str, tuple[CallEdge, ...]] = {source: ()}
    queue = deque([source])
    while queue:
        node = queue.popleft()
        if len(reached[node]) == max_hops:
            continue
        for name, edge in calls.edges.get(node, {}).items():
            if edge.seam is None and name not in reached:
                reached[name] = (*reached[node], edge)
                queue.append(name)
    ranked = sorted(
        (name for name in reached if name != source), key=lambda n: (-len(reached[n]), n)
    )
    return [reached[name] for name in ranked[:max_paths]]


def find_paths(
    calls: CallGraph, source: str, target: str | None, *, max_paths: int, max_hops: int
) -> PathSearch:
    """Candidate paths of AD-291 item 8: deterministic order, bounded work."""
    if target is None:
        return PathSearch(tuple(_farthest(calls, source, max_paths, max_hops)), True)
    work = _Work(WORK_LIMIT)
    paths = _paths_to(calls, source, target, max_paths, max_hops, work)
    return PathSearch(tuple(paths), work.left > 0)
