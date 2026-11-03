# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check a view spec against one observed snapshot (AD-284); author text never becomes proof."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from typing import Final

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    CoverageStatus,
    Entity,
    EntityKind,
    PresenceKind,
    Relationship,
    RelationshipKind,
    ResolutionKind,
)
from archkeel.ir.facts import Evidence
from archkeel.ir.interfaces import component_owners, owner_of
from archkeel.ir.model import Observation, RawJson, Record, RecordData, Verdict
from archkeel.ir.source_graph import observed_graph

_COMPONENT: Final = "component_responsibility"
_INSIDE_COMPONENT: Final = "inside_component_responsibility"
_DYNAMIC_IMPORT: Final = "dynamic_import_limit"
_DYNAMIC_CALLS: Final = "dynamic_call_limit"
# Without a stated kind, a reference is checked as an import, then as a call; never as a mix.
_DEFAULT_KINDS: Final = (RelationshipKind.IMPORTS, RelationshipKind.CALLS)
_TYPE_ONLY: Final = "type-only import: not executed at runtime"
LIMITS: Final = (
    "A proven step is one direct edge of its kind: structure, not runtime order.",
    "An unknown reference is a coverage gap, never a proven absence.",
    "A claim is author text: the check does not look for it in the graph.",
)


class ViewSpecVersion(StrEnum):
    V1_0_0 = "1.0.0"


class ViewStatus(StrEnum):
    PROVEN = "proven"
    DECLARED = "declared"
    CLAIM = "claim"
    UNKNOWN = "unknown"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class ViewSnapshot:
    """The source and contract a view describes; a newer analyzer proves each reference again."""

    source_digest: str
    contract_digest: str


@dataclass(frozen=True, slots=True)
class ViewEdge:
    source: str
    target: str
    kind: RelationshipKind | None = None
    claim: bool = False
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ViewStep:
    node: str
    note: str | None = None
    kind: RelationshipKind | None = None
    claim: bool = False


@dataclass(frozen=True, slots=True)
class ViewSpec:
    schema_version: ViewSpecVersion
    title: str
    snapshot: ViewSnapshot
    nodes: tuple[str, ...]
    edges: tuple[ViewEdge, ...] = ()
    steps: tuple[ViewStep, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ViewEvidence:
    """One observed relationship, or the component declaration that holds a requires entry."""

    record_id: str
    kind: RelationshipKind
    source: str
    target: str
    evidence_id: str | None = None
    file: str | None = None
    line: int | None = None
    type_only: bool = False


@dataclass(frozen=True, slots=True)
class NodeCheck:
    id: str
    status: ViewStatus
    reason: str
    kind: EntityKind | None = None
    entity_id: str | None = None
    file: str | None = None


@dataclass(frozen=True, slots=True)
class LinkCheck:
    """An edge, or a step and the pair it closes with the step before it (none for the first)."""

    source: str | None
    target: str
    status: ViewStatus
    reason: str
    kind: RelationshipKind | None = None
    path: tuple[str, ...] = ()
    evidence: tuple[ViewEvidence, ...] = ()
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ViewCheck:
    schema_version: ViewSpecVersion
    title: str
    exit_code: int
    strict: bool
    snapshot: ViewSnapshot
    view_snapshot: ViewSnapshot
    snapshot_current: bool
    nodes: tuple[NodeCheck, ...]
    edges: tuple[LinkCheck, ...]
    steps: tuple[LinkCheck, ...]
    author_notes: tuple[str, ...]
    limits: tuple[str, ...] = LIMITS


def _fields(
    raw: RawJson, label: str, required: set[str], optional: set[str]
) -> Mapping[str, RawJson]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label} must be an object")
    keys = set(raw)
    if not required <= keys or keys - required - optional:
        allowed = sorted(required | optional)
        raise ValueError(f"{label} needs {sorted(required)} and allows only {allowed}")
    return raw


def _text(raw: RawJson, label: str) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"{label} must be non-empty text")
    text: str = raw
    if not text.strip():
        raise ValueError(f"{label} must be non-empty text")
    return text


def _texts(raw: RawJson, label: str) -> tuple[str, ...]:
    return tuple(_text(item, label) for item in _items(raw, label))


def _items(raw: RawJson, label: str) -> tuple[RawJson, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        raise ValueError(f"{label} must be an array")
    return tuple(raw)


def _claim(raw: RawJson, label: str) -> bool:
    if not isinstance(raw, bool):
        raise ValueError(f"{label}.claim must be true or false")
    return raw


def _kind(raw: RawJson, label: str) -> RelationshipKind | None:
    return None if raw is None else RelationshipKind(_text(raw, f"{label}.kind"))


def _note(raw: RawJson, label: str) -> str | None:
    return None if raw is None else _text(raw, f"{label}.note")


def _edge(raw: RawJson, label: str) -> ViewEdge:
    item = _fields(raw, label, {"source", "target"}, {"kind", "claim", "note"})
    return ViewEdge(
        _text(item["source"], f"{label}.source"),
        _text(item["target"], f"{label}.target"),
        _kind(item.get("kind"), label),
        _claim(item.get("claim", False), label),
        _note(item.get("note"), label),
    )


def _step(raw: RawJson, label: str) -> ViewStep:
    item = _fields(raw, label, {"node"}, {"note", "kind", "claim"})
    return ViewStep(
        _text(item["node"], f"{label}.node"),
        _note(item.get("note"), label),
        _kind(item.get("kind"), label),
        _claim(item.get("claim", False), label),
    )


def parse_view_spec(raw: RawJson) -> ViewSpec:
    """Decode a closed view spec; a field that states proof is not part of the format."""
    item = _fields(
        raw,
        "view spec",
        {"schema_version", "title", "snapshot", "nodes"},
        {"edges", "steps", "notes"},
    )
    snapshot = _fields(
        item["snapshot"],
        "snapshot",
        {"source_digest", "contract_digest"},
        set(),
    )
    nodes = _texts(item["nodes"], "nodes")
    edges = tuple(
        _edge(entry, f"edges[{index}]")
        for index, entry in enumerate(_items(item.get("edges", ()), "edges"))
    )
    steps = tuple(
        _step(entry, f"steps[{index}]")
        for index, entry in enumerate(_items(item.get("steps", ()), "steps"))
    )
    if len(set(nodes)) != len(nodes):
        raise ValueError("nodes must be unique")
    named = {edge.source for edge in edges} | {edge.target for edge in edges}
    named |= {step.node for step in steps}
    if named - set(nodes):
        raise ValueError(
            f"edges and steps name ids that are not in nodes: {sorted(named - set(nodes))}"
        )
    if steps and (steps[0].kind is not None or steps[0].claim):
        raise ValueError("the first step has no step before it, so it takes no kind or claim")
    return ViewSpec(
        ViewSpecVersion(_text(item["schema_version"], "schema_version")),
        _text(item["title"], "title"),
        ViewSnapshot(
            _text(snapshot["source_digest"], "snapshot.source_digest"),
            _text(snapshot["contract_digest"], "snapshot.contract_digest"),
        ),
        nodes,
        edges,
        steps,
        _texts(item.get("notes", ()), "notes"),
    )


def snapshot_identity(observation: Observation) -> ViewSnapshot:
    return ViewSnapshot(observation.source.source_digest, observation.contract.digest)


@dataclass(frozen=True, slots=True)
class _Layer:
    """One relationship kind between node keys, and why an absence cannot be decided."""

    edges: Mapping[tuple[str, str], tuple[ViewEvidence, ...]]
    gaps: Mapping[str, str]
    everywhere: str | None = None


@dataclass(frozen=True, slots=True)
class _Graph:
    modules: Mapping[str, Entity]
    names: frozenset[str]
    roots: tuple[str, ...]
    components: Mapping[str, Record]
    inside: frozenset[str]
    members: Mapping[str, tuple[str, ...]]
    layers: Mapping[RelationshipKind, _Layer]
    # A file the analyzer could not read or parse has no module record: its absence is not proven.
    complete: bool


def _module_names(entities: Mapping[str, Entity]) -> dict[str, str]:
    """Map each entity id to the name of the module that contains it."""
    result: dict[str, str] = {}
    for identity, entity in entities.items():
        current: Entity | None = entity
        while current is not None and current.kind != EntityKind.MODULE:
            current = entities.get(current.parent_id) if current.parent_id else None
        if current is not None:
            result[identity] = current.qualified_name
    return result


def _sites(
    item: Relationship,
    source: str,
    target: str,
    evidence: Mapping[str, Evidence],
    type_only: frozenset[str],
) -> tuple[ViewEvidence, ...]:
    sites = tuple(evidence[identity] for identity in item.evidence_ids if identity in evidence)
    marked = item.id in type_only
    return tuple(
        ViewEvidence(item.id, item.kind, source, target, site.id, site.file, site.line, marked)
        for site in sites
    ) or (ViewEvidence(item.id, item.kind, source, target, type_only=marked),)


def _observed_layers(
    observation: Observation, graph: ArchitectureGraph
) -> dict[RelationshipKind, _Layer]:
    """Lift each resolved relationship to a defined entity onto its source and target modules."""
    entities = {entity.id: entity for entity in graph.entities}
    evidence = {item.id: item for item in graph.evidence}
    type_only = frozenset(
        record.id
        for record in observation.records("imports") or ()
        if record.data.get("under_type_checking") is True
    )
    module_of = _module_names(entities)
    kinds = tuple(kind for kind in RelationshipKind if kind != RelationshipKind.REQUIRES)
    complete = {
        (coverage.scope_id, kind)
        for coverage in graph.coverage
        if coverage.status == CoverageStatus.COMPLETE
        for kind in coverage.relationship_kinds
    }
    edges: dict[RelationshipKind, dict[tuple[str, str], tuple[ViewEvidence, ...]]] = {
        kind: {} for kind in kinds
    }
    gaps: dict[RelationshipKind, dict[str, str]] = {
        kind: {
            entity.qualified_name: f"the snapshot does not cover each {kind} of "
            f"{entity.qualified_name}"
            for entity in graph.entities
            if entity.kind == EntityKind.MODULE and entity.presence == PresenceKind.DEFINED
            if (entity.id, kind) not in complete
        }
        for kind in kinds
    }
    everywhere: dict[RelationshipKind, str] = {}
    for item in graph.relationships:
        target = entities.get(item.target_id) if item.target_id else None
        resolved = item.resolution == ResolutionKind.RESOLVED and target is not None
        presence = target.presence if target is not None else None
        # Importing a name no module defines leaves the project; calling one can be a re-export.
        if item.kind not in edges or (
            resolved
            and item.kind == RelationshipKind.IMPORTS
            and presence == PresenceKind.REFERENCED
        ):
            continue
        source = module_of.get(item.source_id)
        target_module = (
            module_of.get(target.id)
            if target is not None and resolved and presence == PresenceKind.DEFINED
            else None
        )
        kind_edges: dict[tuple[str, str], tuple[ViewEvidence, ...]] = edges[item.kind]
        kind_gaps: dict[str, str] = gaps[item.kind]
        if source is None:
            if item.kind not in everywhere:
                everywhere[item.kind] = f"a {item.kind} relationship has no source module"
        elif target_module is None:
            if source not in kind_gaps:
                kind_gaps[source] = f"{source} has an unresolved or re-exported {item.kind} target"
        elif target_module != source:
            key = (source, target_module)
            sites = _sites(item, source, target_module, evidence, type_only)
            kind_edges[key] = (*kind_edges.get(key, ()), *sites)
    for record in observation.records("unknowns") or ():
        module = record.data.get("source_module")
        if record.kind == _DYNAMIC_IMPORT and isinstance(module, str):
            gaps[RelationshipKind.IMPORTS][module] = f"{module} has a dynamic import"
        elif record.kind == _DYNAMIC_CALLS:
            everywhere[RelationshipKind.CALLS] = f"{record.title}: a call edge is never absent"
    incomplete = (
        "the source observation is incomplete"
        if observation.coverage.status != Verdict.PASS
        else None
    )
    return {
        kind: _Layer(edges[kind], gaps[kind], incomplete or everywhere.get(kind)) for kind in kinds
    }


def _requires(components: Mapping[str, Record]) -> _Layer:
    labels = {record.title: identity for identity, record in components.items()}
    edges: dict[tuple[str, str], tuple[ViewEvidence, ...]] = {}
    declared = False
    for identity, record in components.items():
        entries = record.data.get("requires", ())
        for entry in entries if isinstance(entries, tuple) else ():
            declared = True
            label = entry.get("component") if isinstance(entry, RecordData) else None
            if isinstance(label, str) and label in labels:
                target = labels[label]
                edges[(identity, target)] = (
                    ViewEvidence(identity, RelationshipKind.REQUIRES, identity, target),
                )
    # Without a single requires entry, the contract does not use requires: absence is not decided.
    return _Layer(edges, {}, None if declared else "the contract declares no requires entry")


def _view_graph(observation: Observation) -> _Graph:
    """The one graph loader: a snapshot with or without a contract gives the same shape."""
    graph = observed_graph(observation)
    declarations = observation.records("declarations") or ()
    components = {record.id: record for record in declarations if record.kind == _COMPONENT}
    owners = component_owners(observation)
    modules = {
        entity.qualified_name: entity
        for entity in graph.entities
        if entity.kind == EntityKind.MODULE and entity.presence == PresenceKind.DEFINED
    }
    owned = {name: owner_of(name, owners) for name in sorted(modules)}
    layers = _observed_layers(observation, graph)
    layers[RelationshipKind.REQUIRES] = _requires(components)
    return _Graph(
        modules,
        frozenset(
            entity.qualified_name
            for entity in graph.entities
            if entity.presence == PresenceKind.DEFINED
        ),
        observation.source.scope,
        components,
        frozenset(record.id for record in declarations if record.kind == _INSIDE_COMPONENT),
        {
            identity: tuple(name for name, owner in owned.items() if owner == record.title)
            for identity, record in components.items()
        },
        layers,
        observation.coverage.status == Verdict.PASS and not observation.coverage.failures,
    )


def _keys(graph: _Graph, node: str, kind: RelationshipKind) -> tuple[str, ...]:
    if kind == RelationshipKind.REQUIRES:
        return (node,) if node in graph.components else ()
    return (node,) if node in graph.modules else graph.members.get(node, ())


def _node(graph: _Graph, node: str) -> NodeCheck:
    module = graph.modules.get(node)
    if module is not None:
        return NodeCheck(
            node,
            ViewStatus.PROVEN,
            "an observed module",
            EntityKind.MODULE,
            module.id,
            module.file_path,
        )
    if node in graph.components:
        owned = len(graph.members[node])
        return NodeCheck(
            node,
            ViewStatus.DECLARED,
            f"a contract component; observed modules it owns: {owned}",
            EntityKind.COMPONENT,
        )
    if node in graph.inside:
        return NodeCheck(node, ViewStatus.UNKNOWN, "an inside component is not a view node yet")
    if node in graph.names:
        reason = "a symbol of the snapshot, not a view node: name its module or component"
        return NodeCheck(node, ViewStatus.UNKNOWN, reason)
    roots = ", ".join(graph.roots)
    namespaces = {name.partition(".")[0] for name in graph.modules}
    if not graph.complete:
        reason = f"not in the snapshot, which has incomplete source coverage of {roots}"
        return NodeCheck(node, ViewStatus.UNKNOWN, reason)
    # A path, or a dotted name outside the scanned namespaces: the scan cannot answer it.
    if "/" in node or ("." in node and node.partition(".")[0] not in namespaces):
        reason = f"not a module name in the scanned roots {roots}"
        return NodeCheck(node, ViewStatus.UNKNOWN, reason)
    reason = f"no component, module or symbol has this id in the scanned roots {roots}"
    return NodeCheck(node, ViewStatus.MISSING, reason)


def _one_kind(
    graph: _Graph, source: str, target: str, kind: RelationshipKind, *, step: bool
) -> LinkCheck:
    """Prove one direct edge of one kind; a longer path proves neither an edge nor a step."""
    layer = graph.layers[kind]
    sources, targets = _keys(graph, source, kind), _keys(graph, target, kind)
    if not sources or not targets:
        # A component whose modules all failed to parse has no ends, but they can exist.
        unsupported = kind == RelationshipKind.REQUIRES or layer.everywhere is not None
        reason = layer.everywhere or f"{source} or {target} has no {kind} end in the snapshot"
        if kind == RelationshipKind.REQUIRES:
            reason = "requires relates two contract components"
        status = ViewStatus.UNKNOWN if unsupported else ViewStatus.MISSING
        return LinkCheck(source, target, status, reason, kind)
    pairs = [(key, other) for key in sources for other in targets if (key, other) in layer.edges]
    if pairs:
        evidence = tuple(site for pair in pairs for site in layer.edges[pair])
        if kind == RelationshipKind.REQUIRES:
            reason, found = "a requires entry of the contract", ViewStatus.DECLARED
        elif evidence and all(site.type_only for site in evidence):
            reason, found = f"an observed {kind} relationship; {_TYPE_ONLY}", ViewStatus.PROVEN
        else:
            reason, found = f"an observed {kind} relationship", ViewStatus.PROVEN
        return LinkCheck(source, target, found, reason, kind, pairs[0] if step else (), evidence)
    gaps = [layer.everywhere] if layer.everywhere else []
    gaps += [layer.gaps[key] for key in sources if key in layer.gaps]
    if gaps:
        return LinkCheck(source, target, ViewStatus.UNKNOWN, gaps[0], kind)
    # `from p import sub` records only p.sub, but Python also runs p/__init__.py.
    if kind == RelationshipKind.IMPORTS and any(
        key in sources and other.startswith(f"{end}.")
        for key, other in layer.edges
        for end in targets
    ):
        reason = f"{source} imports a submodule of {target}; the package import is not recorded"
        return LinkCheck(source, target, ViewStatus.UNKNOWN, reason, kind)
    if step:
        reason = f"no direct {kind} edge: a step needs one; add the nodes between as steps"
        return LinkCheck(source, target, ViewStatus.UNKNOWN, reason, kind)
    reverse = any((other, key) in layer.edges for other in targets for key in sources)
    reason = (
        f"only the reverse {kind} direction {target} -> {source} is observed"
        if reverse
        else f"no {kind} relationship, and the coverage is complete"
    )
    return LinkCheck(source, target, ViewStatus.MISSING, reason, kind)


def _link(
    graph: _Graph,
    nodes: Mapping[str, NodeCheck],
    source: str,
    target: str,
    kind: RelationshipKind | None,
    *,
    claim: bool,
    note: str | None,
    step: bool,
) -> LinkCheck:
    if claim:
        reason = "author claim: not checked against the graph"
        return LinkCheck(source, target, ViewStatus.CLAIM, reason, kind, note=note)
    ends = {nodes[source].status, nodes[target].status}
    for status in (ViewStatus.MISSING, ViewStatus.UNKNOWN):
        if status in ends:
            return LinkCheck(source, target, status, f"an end node is {status}", kind, note=note)
    results = [
        _one_kind(graph, source, target, item, step=step)
        for item in ((kind,) if kind is not None else _DEFAULT_KINDS)
    ]
    proof = next(
        (item for item in results if item.status in {ViewStatus.PROVEN, ViewStatus.DECLARED}), None
    )
    if proof is not None:
        return replace(proof, note=note)
    unknown = any(item.status is ViewStatus.UNKNOWN for item in results)
    status = ViewStatus.UNKNOWN if unknown else ViewStatus.MISSING
    reason = "; ".join(item.reason for item in results)
    return LinkCheck(source, target, status, reason, kind, note=note)


def check_view(spec: ViewSpec, observation: Observation, *, strict: bool) -> ViewCheck:
    """Check each reference against the snapshot the spec names; a claim stays author text."""
    identity = snapshot_identity(observation)
    current = identity == spec.snapshot
    befores = (None, *(step.node for step in spec.steps[:-1])) if spec.steps else ()
    pairs = tuple(zip(befores, spec.steps, strict=True))
    nodes: tuple[NodeCheck, ...]
    edges: tuple[LinkCheck, ...]
    steps: tuple[LinkCheck, ...]
    if not current:
        stale = "the view names another snapshot: check it against that snapshot"
        nodes = tuple(NodeCheck(node, ViewStatus.UNKNOWN, stale) for node in spec.nodes)
        edges = tuple(
            LinkCheck(
                edge.source, edge.target, ViewStatus.UNKNOWN, stale, edge.kind, note=edge.note
            )
            for edge in spec.edges
        )
        steps = tuple(
            LinkCheck(before, step.node, ViewStatus.UNKNOWN, stale, step.kind, note=step.note)
            for before, step in pairs
        )
    else:
        graph = _view_graph(observation)
        checked = {node: _node(graph, node) for node in spec.nodes}
        nodes = tuple(checked.values())
        edges = tuple(
            _link(
                graph,
                checked,
                edge.source,
                edge.target,
                edge.kind,
                claim=edge.claim,
                note=edge.note,
                step=False,
            )
            for edge in spec.edges
        )
        steps = tuple(
            LinkCheck(
                None,
                step.node,
                checked[step.node].status,
                checked[step.node].reason,
                note=step.note,
            )
            if before is None
            else _link(
                graph,
                checked,
                before,
                step.node,
                step.kind,
                claim=step.claim,
                note=step.note,
                step=True,
            )
            for before, step in pairs
        )
    statuses = {node.status for node in nodes} | {link.status for link in (*edges, *steps)}
    failed = ViewStatus.MISSING in statuses or (strict and ViewStatus.UNKNOWN in statuses)
    return ViewCheck(
        spec.schema_version,
        spec.title,
        2 if not current else 1 if failed else 0,
        strict,
        identity,
        spec.snapshot,
        current,
        nodes,
        edges,
        steps,
        spec.notes,
    )


def view_check_json(check: ViewCheck) -> str:
    """The same check gives the same text."""
    return json.dumps(asdict(check), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def view_summary(check: ViewCheck) -> str:
    verdicts = {
        0: "no reference is missing",
        1: "a reference is missing" + (" or unknown (--strict)" if check.strict else ""),
        2: "not checked: the view names another snapshot",
    }
    lines = [f"View check {check.title!r}: exit {check.exit_code}, {verdicts[check.exit_code]}."]
    for label, items in (("Nodes", check.nodes), ("Edges", check.edges), ("Steps", check.steps)):
        counts = Counter(item.status for item in items)
        found = ", ".join(f"{counts[status]} {status}" for status in ViewStatus if counts[status])
        lines.append(f"{label}: {found or 'none'}")
    lines.append(check.limits[0])
    for node in check.nodes:
        if node.status in {ViewStatus.MISSING, ViewStatus.UNKNOWN}:
            lines.append(f"{node.status}: node {node.id}: {node.reason}")
    for link in (*check.edges, *check.steps):
        if link.status in {ViewStatus.MISSING, ViewStatus.UNKNOWN} and link.source is not None:
            lines.append(f"{link.status}: {link.source} -> {link.target}: {link.reason}")
    return "\n".join(lines)
