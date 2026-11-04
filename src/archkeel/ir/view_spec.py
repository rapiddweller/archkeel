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
from typing import Final, Literal, TypeVar

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
from archkeel.ir.decisions import declares_a_target
from archkeel.ir.facts import Evidence
from archkeel.ir.flow_graph import (
    CallEdge,
    CallGraph,
    Direction,
    ExternalSystem,
    Seam,
    Site,
    Touch,
    build_call_graph,
    function_label,
    module_lanes,
    module_names,
    touchpoints,
)
from archkeel.ir.graph_codec import non_empty_text
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
STORY_LIMITS: Final = (
    "A proven step is one resolved call between two functions: structure, not runtime order.",
    "A partial call is a claim: the analysis lists candidates and does not prove the target.",
    "A process boundary is not detected. Title, note, question and each direction are claims.",
    "A touched system is an import of a client library of the catalog, not a proven access.",
)


class ViewSpecVersion(StrEnum):
    # Newest first: the schema `$id` names the first member, as for the graph versions.
    # AD-289: stops need 1.1.0. AD-291: a story needs 1.2.0. An older spec keeps its meaning.
    V1_2_0 = "1.2.0"
    V1_1_0 = "1.1.0"
    V1_0_0 = "1.0.0"


class AuthorKind(StrEnum):
    """AD-291: who wrote the text of a stored spec; the check does not read it."""

    AGENT = "agent"
    HUMAN = "human"


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
class ViewExternal:
    """An author claim: the step reaches this system. The check observes the touchpoint."""

    system: ExternalSystem
    direction: Direction


@dataclass(frozen=True, slots=True)
class ViewStep:
    node: str
    note: str | None = None
    kind: RelationshipKind | None = None
    claim: bool = False
    # AD-291: story fields, author text; they need a story and schema_version 1.2.0.
    chapter: str | None = None
    title: str | None = None
    question: str | None = None
    external: tuple[ViewExternal, ...] = ()


@dataclass(frozen=True, slots=True)
class ViewStop:
    """A tour stop: a node and author text; it claims no relation, so it takes no kind."""

    node: str
    title: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ViewChapter:
    id: str
    title: str


@dataclass(frozen=True, slots=True)
class ViewStory:
    id: str
    title: str
    chapters: tuple[ViewChapter, ...] = ()


@dataclass(frozen=True, slots=True)
class ViewSpec:
    schema_version: ViewSpecVersion
    title: str
    snapshot: ViewSnapshot
    nodes: tuple[str, ...]
    edges: tuple[ViewEdge, ...] = ()
    steps: tuple[ViewStep, ...] = ()
    notes: tuple[str, ...] = ()
    stops: tuple[ViewStop, ...] = ()
    story: ViewStory | None = None
    # AD-291: where a stored spec comes from; optional, author text, they need schema_version 1.2.0.
    created: str | None = None
    git_head: str | None = None
    author_kind: AuthorKind | None = None
    agent: str | None = None


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


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidateEvidence(ViewEvidence):
    """AD-291: a call site of a partial call. `candidates` marks it, so it is never proof."""

    candidates: int


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
    evidence: tuple[ViewEvidence | CandidateEvidence, ...] = ()
    note: str | None = None


@dataclass(frozen=True, slots=True)
class StopImports:
    """Distinct observed module pairs of one direction; with a gap the count is a lower bound."""

    pairs: int
    evidence: tuple[ViewEvidence, ...]
    gap: str | None = None


@dataclass(frozen=True, slots=True)
class StopFinding:
    record_id: str
    kind: str
    title: str


@dataclass(frozen=True, slots=True)
class StopFacts:
    """Measured from the snapshot only; the spec cannot state any of it."""

    modules: int
    imports_out: StopImports
    imports_in: StopImports
    violations: tuple[StopFinding, ...]
    unknowns: tuple[StopFinding, ...]


@dataclass(frozen=True, slots=True)
class StopCheck:
    """A stop is never a proof: its node status comes from the node, its facts from the graph."""

    node: str
    status: ViewStatus
    reason: str
    title: str | None = None
    note: str | None = None
    facts: StopFacts | None = None


@dataclass(frozen=True, slots=True)
class ExternalCheck:
    """`touched` is observed with import evidence; `direction` is the author claim, if any."""

    system: ExternalSystem
    touched: bool
    evidence: tuple[Touch, ...] = ()
    direction: Direction | None = None


@dataclass(frozen=True, slots=True)
class StoryStepCheck:
    """The facts of one story step. Its status and call sites are `steps[index]` of the check."""

    index: int
    node: str
    label: str
    chapter: str | None
    title: str | None
    question: str | None
    lane: str | None
    defined_at: Site | None
    seam: Seam | None
    external: tuple[ExternalCheck, ...]


@dataclass(frozen=True, slots=True)
class StoryVerdict:
    """Counts only. A claim is never counted as proven."""

    proven: int
    declared: int
    claim: int
    unknown: int
    missing: int
    systems: tuple[ExternalSystem, ...]
    modules: int


@dataclass(frozen=True, slots=True)
class StoryCheck:
    id: str
    title: str
    chapters: tuple[ViewChapter, ...]
    steps: tuple[StoryStepCheck, ...]
    verdict: StoryVerdict
    limits: tuple[str, ...] = STORY_LIMITS


@dataclass(frozen=True, slots=True)
class ViewCheck:
    result_schema_version: Literal["1.3.0"]
    schema_version: ViewSpecVersion
    title: str
    exit_code: int
    strict: bool
    snapshot: ViewSnapshot
    view_snapshot: ViewSnapshot
    snapshot_current: bool
    snapshot_completeness: Literal["complete", "incomplete"]
    nodes: tuple[NodeCheck, ...]
    edges: tuple[LinkCheck, ...]
    steps: tuple[LinkCheck, ...]
    author_notes: tuple[str, ...]
    stops: tuple[StopCheck, ...]
    limits: tuple[str, ...] = LIMITS
    # AD-291: only a 1.2.0 spec with a story has this block; the JSON leaves it out otherwise.
    story: StoryCheck | None = None


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


def _texts(raw: RawJson, label: str) -> tuple[str, ...]:
    return tuple(non_empty_text(item, label) for item in _items(raw, label))


def _items(raw: RawJson, label: str) -> tuple[RawJson, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        raise ValueError(f"{label} must be an array")
    return tuple(raw)


def _claim(raw: RawJson, label: str) -> bool:
    if not isinstance(raw, bool):
        raise ValueError(f"{label}.claim must be true or false")
    return raw


def _kind(raw: RawJson, label: str) -> RelationshipKind | None:
    return None if raw is None else RelationshipKind(non_empty_text(raw, f"{label}.kind"))


def _note(raw: RawJson, label: str) -> str | None:
    return None if raw is None else non_empty_text(raw, f"{label}.note")


_E = TypeVar("_E", bound=StrEnum)
_STORY_KEYS: Final = frozenset({"chapter", "title", "question", "external"})
_PROVENANCE_KEYS: Final = ("created", "git_head", "author_kind", "agent")


def _member(kind: type[_E], raw: RawJson, label: str) -> _E:
    try:
        return kind(non_empty_text(raw, label))
    except ValueError:
        raise ValueError(f"{label} must be one of {[item.value for item in kind]}") from None


def _optional(raw: RawJson, label: str) -> str | None:
    return None if raw is None else non_empty_text(raw, label)


def _external(raw: RawJson, label: str) -> ViewExternal:
    item = _fields(raw, label, {"system", "direction"}, set())
    return ViewExternal(
        _member(ExternalSystem, item["system"], f"{label}.system"),
        _member(Direction, item["direction"], f"{label}.direction"),
    )


def _chapter(raw: RawJson, label: str) -> ViewChapter:
    item = _fields(raw, label, {"id", "title"}, set())
    return ViewChapter(
        non_empty_text(item["id"], f"{label}.id"), non_empty_text(item["title"], f"{label}.title")
    )


def _story(raw: RawJson) -> ViewStory:
    item = _fields(raw, "story", {"id", "title"}, {"chapters"})
    chapters = tuple(
        _chapter(entry, f"story.chapters[{index}]")
        for index, entry in enumerate(_items(item.get("chapters", ()), "story.chapters"))
    )
    if len({chapter.id for chapter in chapters}) != len(chapters):
        raise ValueError("story.chapters must have unique ids")
    return ViewStory(
        non_empty_text(item["id"], "story.id"),
        non_empty_text(item["title"], "story.title"),
        chapters,
    )


def _edge(raw: RawJson, label: str) -> ViewEdge:
    item = _fields(raw, label, {"source", "target"}, {"kind", "claim", "note"})
    return ViewEdge(
        non_empty_text(item["source"], f"{label}.source"),
        non_empty_text(item["target"], f"{label}.target"),
        _kind(item.get("kind"), label),
        _claim(item.get("claim", False), label),
        _note(item.get("note"), label),
    )


def _step(raw: RawJson, label: str) -> ViewStep:
    item = _fields(
        raw, label, {"node"}, {"note", "kind", "claim", "chapter", "title", "question", "external"}
    )
    external = tuple(
        _external(entry, f"{label}.external[{index}]")
        for index, entry in enumerate(_items(item.get("external", ()), f"{label}.external"))
    )
    if len({entry.system for entry in external}) != len(external):
        raise ValueError(f"{label}.external names a system twice")
    return ViewStep(
        non_empty_text(item["node"], f"{label}.node"),
        _note(item.get("note"), label),
        _kind(item.get("kind"), label),
        _claim(item.get("claim", False), label),
        _optional(item.get("chapter"), f"{label}.chapter"),
        _optional(item.get("title"), f"{label}.title"),
        _optional(item.get("question"), f"{label}.question"),
        external,
    )


def _stop(raw: RawJson, label: str) -> ViewStop:
    item = _fields(raw, label, {"node"}, {"title", "note"})
    title = item.get("title")
    return ViewStop(
        non_empty_text(item["node"], f"{label}.node"),
        None if title is None else non_empty_text(title, f"{label}.title"),
        _note(item.get("note"), label),
    )


def parse_view_spec(raw: RawJson) -> ViewSpec:
    """Decode a closed view spec; a field that states proof is not part of the format."""
    item = _fields(
        raw,
        "view spec",
        {"schema_version", "title", "snapshot", "nodes"},
        {"edges", "steps", "notes", "stops", "story", *_PROVENANCE_KEYS},
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
    stops = tuple(
        _stop(entry, f"stops[{index}]")
        for index, entry in enumerate(_items(item.get("stops", ()), "stops"))
    )
    version = ViewSpecVersion(non_empty_text(item["schema_version"], "schema_version"))
    if "stops" in item and version is ViewSpecVersion.V1_0_0:
        raise ValueError("stops need schema_version 1.1.0")
    story = _story(item["story"]) if "story" in item else None
    if version is not ViewSpecVersion.V1_2_0 and not set(_PROVENANCE_KEYS).isdisjoint(item):
        raise ValueError("created, git_head, author_kind and agent need schema_version 1.2.0")
    keyed = any(
        isinstance(entry, Mapping) and not _STORY_KEYS.isdisjoint(entry)
        for entry in _items(item.get("steps", ()), "steps")
    )
    _check_story_fields(version, story, steps, keyed=keyed)
    if len(set(nodes)) != len(nodes):
        raise ValueError("nodes must be unique")
    named = {edge.source for edge in edges} | {edge.target for edge in edges}
    named |= {step.node for step in steps} | {stop.node for stop in stops}
    if named - set(nodes):
        raise ValueError(
            f"edges, steps and stops name ids that are not in nodes: {sorted(named - set(nodes))}"
        )
    if steps and (steps[0].kind is not None or steps[0].claim):
        raise ValueError("the first step has no step before it, so it takes no kind or claim")
    return ViewSpec(
        version,
        non_empty_text(item["title"], "title"),
        ViewSnapshot(
            non_empty_text(snapshot["source_digest"], "snapshot.source_digest"),
            non_empty_text(snapshot["contract_digest"], "snapshot.contract_digest"),
        ),
        nodes,
        edges,
        steps,
        _texts(item.get("notes", ()), "notes"),
        stops,
        story,
        _optional(item.get("created"), "created"),
        _optional(item.get("git_head"), "git_head"),
        None
        if item.get("author_kind") is None
        else _member(AuthorKind, item["author_kind"], "author_kind"),
        _optional(item.get("agent"), "agent"),
    )


def _check_story_fields(
    version: ViewSpecVersion, story: ViewStory | None, steps: tuple[ViewStep, ...], *, keyed: bool
) -> None:
    # A key counts also with a null value, as in the schema: only 1.2.0 knows these keys.
    if (story is not None or keyed) and version is not ViewSpecVersion.V1_2_0:
        raise ValueError("a story needs schema_version 1.2.0")
    if story is None:
        if keyed:
            raise ValueError("chapter, title, question and external need a story")
        return
    known = {chapter.id for chapter in story.chapters}
    for index, step in enumerate(steps):
        if step.chapter is None and known:
            raise ValueError(f"steps[{index}] must name a chapter of the story")
        if step.chapter is not None and step.chapter not in known:
            raise ValueError(f"steps[{index}].chapter names no chapter of the story")


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
    packages: frozenset[str]
    names: frozenset[str]
    roots: tuple[str, ...]
    components: Mapping[str, Record]
    inside: frozenset[str]
    members: Mapping[str, tuple[str, ...]]
    layers: Mapping[RelationshipKind, _Layer]
    # A file the analyzer could not read or parse has no module record: its absence is not proven.
    complete: bool
    # AD-285: bare component groups, such as the explore layout, declare nothing.
    declared: bool
    # AD-289: the violation and unknown records whose subject or fact lies in each module.
    violations: Mapping[str, tuple[Record, ...]]
    unknowns: Mapping[str, tuple[Record, ...]]
    # AD-291: the call graph exists for a spec with a story only; lanes name each module's lane.
    calls: CallGraph | None
    lanes: Mapping[str, str]


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
    module_of = module_names(entities)
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


def _touched(
    observation: Observation, graph: ArchitectureGraph
) -> dict[str, dict[str, tuple[Record, ...]]]:
    """For violations and unknowns: map each module to the records that name it or a symbol in it.

    A fact id of an import or call record touches both its modules: a forbidden import also
    touches its target, a re-export included.
    """
    entities = {entity.id: entity for entity in graph.entities}
    module_of = module_names(entities)
    names = {
        entity.qualified_name: module_of[entity.id]
        for entity in graph.entities
        if entity.presence == PresenceKind.DEFINED and entity.id in module_of
    }
    ends = {
        item.id: {
            value
            for key in ("source_module", "target_module")
            if isinstance(value := item.data.get(key), str)
        }
        for kind in ("imports", "calls")
        for item in observation.records(kind) or ()
    }
    result: dict[str, dict[str, tuple[Record, ...]]] = {}
    for section in ("violations", "unknowns"):
        touched: dict[str, list[Record]] = {}
        for record in observation.records(section) or ():
            modules: set[str] = set()
            for reference in (*record.subjects, *record.fact_ids):
                found = names.get(reference) or module_of.get(reference)
                modules |= {found} if found is not None else ends.get(reference, set())
            for module in sorted(modules):
                touched.setdefault(module, []).append(record)
        result[section] = {module: tuple(records) for module, records in touched.items()}
    return result


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


def _view_graph(observation: Observation, *, story: bool) -> _Graph:
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
    touched = _touched(observation, graph)
    return _Graph(
        modules,
        frozenset(
            entity.qualified_name for entity in graph.entities if entity.kind == EntityKind.PACKAGE
        ),
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
        declares_a_target(observation),
        touched["violations"],
        touched["unknowns"],
        build_call_graph(graph, observation.records("imports") or ()) if story else None,
        module_lanes(observation, modules),
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
    function = graph.calls.functions.get(node) if graph.calls is not None else None
    if function is not None:
        file = function.defined_at.file if function.defined_at is not None else None
        reason = f"an observed {function.kind}"
        return NodeCheck(node, ViewStatus.PROVEN, reason, function.kind, function.entity_id, file)
    if node in graph.components and not graph.declared:
        owned = len(graph.members[node])
        reason = f"a component group that declares nothing; observed modules it holds: {owned}"
        return NodeCheck(node, ViewStatus.UNKNOWN, reason, EntityKind.COMPONENT)
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
    if node in graph.packages:
        reason = "a package: name a module or a component"
        return NodeCheck(node, ViewStatus.UNKNOWN, reason)
    if node in graph.names:
        reason = "a symbol of the snapshot, not a view node: name its module or component"
        return NodeCheck(node, ViewStatus.UNKNOWN, reason)
    roots = ", ".join(graph.roots)
    namespaces = {str.partition(name, ".")[0] for name in graph.modules}
    if not graph.complete:
        reason = f"not in the snapshot, which has incomplete source coverage of {roots}"
        return NodeCheck(node, ViewStatus.UNKNOWN, reason)
    # A path, or a dotted name outside the scanned namespaces: the scan cannot answer it.
    if "/" in node or ("." in node and node.partition(".")[0] not in namespaces):
        reason = f"not a module name in the scanned roots {roots}"
        return NodeCheck(node, ViewStatus.UNKNOWN, reason)
    reason = f"no component, module or symbol has this id in the scanned roots {roots}"
    return NodeCheck(node, ViewStatus.MISSING, reason)


def _imports(layer: _Layer, keys: frozenset[str], *, out: bool) -> StopImports:
    end = 0 if out else 1
    pairs = sorted(pair for pair in layer.edges if pair[end] in keys and pair[1 - end] not in keys)
    gap = layer.everywhere
    if gap is None and out:
        gap = next((layer.gaps[key] for key in sorted(keys) if key in layer.gaps), None)
    elif gap is None:
        # An import from any other module can hide behind that module's gap.
        others = sorted(set(layer.gaps) - keys)
        if others:
            gap = (
                f"{len(others)} other modules have an import gap, such as: {layer.gaps[others[0]]}"
            )
    return StopImports(len(pairs), tuple(site for pair in pairs for site in layer.edges[pair]), gap)


def _findings(
    records: Mapping[str, tuple[Record, ...]], keys: frozenset[str]
) -> tuple[StopFinding, ...]:
    found = {record.id: record for key in keys for record in records.get(key, ())}
    return tuple(
        StopFinding(record.id, record.kind, record.title) for _, record in sorted(found.items())
    )


def _facts(graph: _Graph, node: str) -> StopFacts:
    keys = frozenset(_keys(graph, node, RelationshipKind.IMPORTS))
    layer = graph.layers[RelationshipKind.IMPORTS]
    return StopFacts(
        len(keys),
        _imports(layer, keys, out=True),
        _imports(layer, keys, out=False),
        _findings(graph.violations, keys),
        _findings(graph.unknowns, keys),
    )


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
        key in sources and str.startswith(other, f"{end}.")
        for key, other in layer.edges
        for end in targets
    ):
        reason = f"{source} imports a submodule of {target}; the package import is not recorded"
        return LinkCheck(source, target, ViewStatus.UNKNOWN, reason, kind)
    if step:
        reason = f"no direct {kind} edge: a step needs one; add the nodes between as steps"
        return LinkCheck(source, target, ViewStatus.MISSING, reason, kind)
    reverse = any((other, key) in layer.edges for other in targets for key in sources)
    reason = (
        f"only the reverse {kind} direction {target} -> {source} is observed"
        if reverse
        else f"no {kind} relationship, and the coverage is complete"
    )
    return LinkCheck(source, target, ViewStatus.MISSING, reason, kind)


def call_evidence(edge: CallEdge) -> tuple[ViewEvidence | CandidateEvidence, ...]:
    """Each call site. A partial call carries `candidates`, so it differs in shape from proof."""
    if edge.seams:
        return tuple(
            CandidateEvidence(
                site.record_id,
                RelationshipKind.CALLS,
                edge.source,
                edge.target,
                site.evidence_id,
                site.file,
                site.line,
                candidates=seam.candidates or 0,
            )
            for site, seam in zip(edge.sites, edge.seams, strict=True)
        )
    return tuple(
        ViewEvidence(
            site.record_id,
            RelationshipKind.CALLS,
            edge.source,
            edge.target,
            site.evidence_id,
            site.file,
            site.line,
        )
        for site in edge.sites
    )


def call_status(edge: CallEdge) -> tuple[ViewStatus, str]:
    """A resolved call proves the pair. A partial call is a claim: the target is a candidate."""
    if edge.seam is None:
        return ViewStatus.PROVEN, "an observed resolved call"
    reason = (
        f"a partial call with {edge.seam.candidates} candidates: "
        "the analysis does not prove the target"
    )
    return ViewStatus.CLAIM, reason


def _function_link(
    graph: _Graph,
    calls: CallGraph,
    source: str,
    target: str,
    kind: RelationshipKind | None,
    note: str | None,
    *,
    step: bool,
) -> LinkCheck:
    """AD-291: two functions relate by one direct call; a partial call is a claim, never proof."""
    if source not in calls.functions or target not in calls.functions:
        reason = "a function and a module are not one step: name two functions or two modules"
        return LinkCheck(source, target, ViewStatus.UNKNOWN, reason, kind, note=note)
    if kind not in {None, RelationshipKind.CALLS}:
        reason = f"two functions relate by calls, not {kind}"
        return LinkCheck(source, target, ViewStatus.UNKNOWN, reason, kind, note=note)
    calling = RelationshipKind.CALLS
    edge = calls.edges.get(source, {}).get(target)
    if edge is None:
        # The same rule as `_one_kind`: a module gap or a dynamic call limit hides the call.
        layer = graph.layers[calling]
        seam = calls.unresolved.get(source)
        gap = layer.everywhere or layer.gaps.get(calls.functions[source].module)
        if seam is not None:
            reason = f"{seam.calls} calls of {source} have no named target: {seam.reason}"
        else:
            reason = gap or f"no call from {source} to {target}, and the coverage is complete"
        status = ViewStatus.UNKNOWN if seam is not None or gap else ViewStatus.MISSING
        return LinkCheck(source, target, status, reason, calling, note=note)
    status, reason = call_status(edge)
    path = (source, target) if step else ()
    return LinkCheck(source, target, status, reason, calling, path, call_evidence(edge), note)


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
    story_context: bool,
) -> LinkCheck:
    if claim and not (story_context and step):
        reason = "author claim: not checked against the graph"
        return LinkCheck(source, target, ViewStatus.CLAIM, reason, kind, note=note)
    ends = {nodes[source].status, nodes[target].status}
    for status in (ViewStatus.MISSING, ViewStatus.UNKNOWN):
        if status in ends:
            return LinkCheck(source, target, status, f"an end node is {status}", kind, note=note)
    if claim:
        reason = "author claim: not checked against the graph"
        return LinkCheck(source, target, ViewStatus.CLAIM, reason, kind, note=note)
    calls = graph.calls
    if calls is not None and (source in calls.functions or target in calls.functions):
        return _function_link(graph, calls, source, target, kind, note, step=step)
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


def _stop_check(stop: ViewStop, node: NodeCheck, graph: _Graph | None) -> StopCheck:
    """A stop repeats its node check; only an observed module or a declared component has facts."""
    facts = (
        _facts(graph, stop.node)
        if graph is not None and node.status in {ViewStatus.PROVEN, ViewStatus.DECLARED}
        else None
    )
    return StopCheck(stop.node, node.status, node.reason, stop.title, stop.note, facts)


def _module_of(graph: _Graph, node: str) -> str | None:
    function = graph.calls.functions.get(node) if graph.calls is not None else None
    return function.module if function is not None else node if node in graph.modules else None


def _seam_into(calls: CallGraph, before: str | None, node: str) -> Seam | None:
    """The seam of the call from the step before: its partial call, else its unresolved calls."""
    if before is None or node not in calls.functions:
        return None
    edge = calls.edges.get(before, {}).get(node)
    return edge.seam if edge is not None else calls.unresolved.get(before)


def external_checks(
    touches: tuple[Touch, ...], claims: Mapping[ExternalSystem, Direction] | None = None
) -> tuple[ExternalCheck, ...]:
    """One entry per system: the observed touchpoints and the claimed direction, if any."""
    claimed = claims or {}
    found: dict[ExternalSystem, list[Touch]] = {}
    for touch in touches:
        found.setdefault(touch.system, []).append(touch)
    return tuple(
        ExternalCheck(system, system in found, tuple(found.get(system, ())), claimed.get(system))
        for system in sorted(claimed.keys() | found.keys())
    )


def _story_check(
    spec: ViewSpec, story: ViewStory, graph: _Graph | None, steps: tuple[LinkCheck, ...]
) -> StoryCheck:
    """Facts for each step, from the call graph only; the author text is copied, not read."""
    calls = graph.calls if graph is not None else None
    checked: list[StoryStepCheck] = []
    modules: set[str] = set()
    for index, step in enumerate(spec.steps):
        module = _module_of(graph, step.node) if graph is not None else None
        modules |= {module} if module is not None else set()
        function = calls.functions.get(step.node) if calls is not None else None
        before = spec.steps[index - 1].node if index else None
        touches = touchpoints(calls, step.node) if calls is not None else ()
        checked.append(
            StoryStepCheck(
                index,
                step.node,
                function_label(function) if function is not None else step.node,
                step.chapter,
                step.title,
                step.question,
                graph.lanes.get(module) if graph is not None and module is not None else None,
                function.defined_at if function is not None else None,
                _seam_into(calls, before, step.node) if calls is not None else None,
                external_checks(touches, {item.system: item.direction for item in step.external}),
            )
        )
    counts = Counter(link.status for link in steps)
    systems = sorted({item.system for step in checked for item in step.external if item.touched})
    verdict = StoryVerdict(
        counts[ViewStatus.PROVEN],
        counts[ViewStatus.DECLARED],
        counts[ViewStatus.CLAIM],
        counts[ViewStatus.UNKNOWN],
        counts[ViewStatus.MISSING],
        tuple(systems),
        len(modules),
    )
    return StoryCheck(story.id, story.title, story.chapters, tuple(checked), verdict)


def check_view(spec: ViewSpec, observation: Observation, *, strict: bool) -> ViewCheck:
    """Check each reference against the snapshot the spec names; a claim stays author text."""
    return _check_view(spec, observation, strict=strict)


def _check_view(
    spec: ViewSpec,
    observation: Observation,
    *,
    strict: bool,
    prepared_graph: _Graph | None = None,
) -> ViewCheck:
    identity = snapshot_identity(observation)
    current = identity == spec.snapshot
    befores = (None, *(step.node for step in spec.steps[:-1])) if spec.steps else ()
    pairs = tuple(zip(befores, spec.steps, strict=True))
    nodes: tuple[NodeCheck, ...]
    edges: tuple[LinkCheck, ...]
    steps: tuple[LinkCheck, ...]
    graph: _Graph | None = None
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
        graph = prepared_graph or _view_graph(observation, story=spec.story is not None)
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
                story_context=spec.story is not None,
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
                story_context=spec.story is not None,
            )
            for before, step in pairs
        )
    by_id = {node.id: node for node in nodes}
    stops = tuple(_stop_check(stop, by_id[stop.node], graph) for stop in spec.stops)
    statuses = {node.status for node in nodes} | {link.status for link in (*edges, *steps)}
    failed = ViewStatus.MISSING in statuses or (strict and ViewStatus.UNKNOWN in statuses)
    return ViewCheck(
        "1.3.0",
        spec.schema_version,
        spec.title,
        2 if not current else 1 if failed else 0,
        strict,
        identity,
        spec.snapshot,
        current,
        "complete"
        if observation.coverage.status is Verdict.PASS and not observation.coverage.failures
        else "incomplete",
        nodes,
        edges,
        steps,
        spec.notes,
        stops,
        story=_story_check(spec, spec.story, graph, steps) if spec.story is not None else None,
    )


class ViewCheckSession:
    """Reuse one snapshot graph when several stored stories are checked together."""

    def __init__(self, observation: Observation) -> None:
        self.observation = observation
        self._graph = _view_graph(observation, story=True)

    def check(self, spec: ViewSpec, *, strict: bool) -> ViewCheck:
        return _check_view(spec, self.observation, strict=strict, prepared_graph=self._graph)


def view_check_json(check: ViewCheck) -> str:
    """The same check gives the same text."""
    data = asdict(check)
    if check.story is None:
        del data["story"]
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def view_summary(check: ViewCheck) -> str:
    verdicts = {
        0: "no reference is missing",
        1: "a reference is missing" + (" or unknown (--strict)" if check.strict else ""),
        2: "not checked: the view names another snapshot",
    }
    lines = [f"View check {check.title!r}: exit {check.exit_code}, {verdicts[check.exit_code]}."]
    if check.snapshot_completeness == "incomplete":
        lines.append(
            "Warning: the source snapshot is incomplete; UNKNOWN means evidence is missing."
        )
    for label, items in (("Nodes", check.nodes), ("Edges", check.edges), ("Steps", check.steps)):
        counts = Counter(item.status for item in items)
        found = ", ".join(f"{counts[status]} {status}" for status in ViewStatus if counts[status])
        lines.append(f"{label}: {found or 'none'}")
    lines.append(check.limits[0])
    if check.story is not None:
        verdict = check.story.verdict
        systems = ", ".join(verdict.systems) or "none"
        lines.append(
            f"Story {check.story.id!r}: {verdict.proven} proven, {verdict.claim} claim, "
            f"{verdict.unknown} unknown, {verdict.missing} missing; systems touched: {systems}; "
            f"modules touched: {verdict.modules}"
        )
    if check.stops:
        measured = sum(stop.facts is not None for stop in check.stops)
        lines.append(f"Stops: {len(check.stops)}, {measured} with measured facts")
    for node in check.nodes:
        if node.status in {ViewStatus.MISSING, ViewStatus.UNKNOWN}:
            lines.append(f"{node.status}: node {node.id}: {node.reason}")
    for link in (*check.edges, *check.steps):
        if link.status in {ViewStatus.MISSING, ViewStatus.UNKNOWN} and link.source is not None:
            lines.append(f"{link.status}: {link.source} -> {link.target}: {link.reason}")
    return "\n".join(lines)
