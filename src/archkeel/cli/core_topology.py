# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Decode the optional topology display. It cannot supply a verdict or a scope proof."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from .core_evidence import Location
from .core_json import CoreError, as_count, as_object, as_text

LIMITS: Final = {
    "components": 4096,
    "modules": 10_000,
    "edges": 20_000,
    "component_edges": 20_000,
    "evidence_per_edge": 5,
    "requires": 20_000,
    "layers": 4096,
}


class Ownership(StrEnum):
    """Whether exactly one component owns a module."""

    OWNED = "owned"
    UNOWNED = "unowned"
    AMBIGUOUS = "ambiguous"


class Resolution(StrEnum):
    """Whether an import resolved to a module, failed to resolve or is external."""

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    EXTERNAL = "external"


@dataclass(frozen=True, slots=True)
class Component:
    """A component of the contract as the topology lists it."""

    id: str
    name: str
    parent: str | None
    packages: tuple[str, ...]
    exact_modules: tuple[str, ...]
    planned: bool
    layer: str | None
    public: tuple[str, ...]
    responsibilities: tuple[str, ...]
    forbidden_responsibilities: tuple[str, ...]
    planned_public: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Module:
    """A scanned module, its path and its owning component."""

    name: str
    path: str
    component: str | None
    ownership: Ownership
    language: str


@dataclass(frozen=True, slots=True)
class Edge:
    """An import edge between two modules or two components, with its evidence and rules."""

    id: str
    source: str
    target: str
    resolution: Resolution
    count: int
    evidence: tuple[Location, ...]
    evidence_total: int
    rules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Require:
    """One declared `requires` entry and the observed imports that use it (AD-594)."""

    source: str
    target: str
    imports: int
    rationale: str
    through: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LayerOrder:
    """The layers of one `layer_order` rule, from the inner layer to the outer layer."""

    rule: str
    layers: tuple[str, ...]
    part: str | None = None


@dataclass(frozen=True, slots=True)
class Topology:
    """The topology part of a frame: components, modules and edges."""

    complete: bool
    truncated: bool
    gaps: tuple[str, ...]
    total: Mapping[str, int]
    components: tuple[Component, ...]
    modules: tuple[Module, ...]
    edges: tuple[Edge, ...]
    component_edges: tuple[Edge, ...]
    requires: tuple[Require, ...]
    layers: tuple[LayerOrder, ...]


def _bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise CoreError("topology: expected a boolean")
    return value


def _optional(value: object) -> str | None:
    return None if value is None else as_text(value, "topology")


def _list(value: object, limit: int) -> list[object]:
    if not isinstance(value, list) or len(value) > limit:
        raise CoreError("topology: invalid or over-budget list")
    return value


def _strings(value: object) -> tuple[str, ...]:
    return tuple(as_text(item, "topology") for item in _list(value, 100_000))


def _component(value: object) -> Component:
    row = as_object(value, "topology.component")
    return Component(
        as_text(row["id"], "id"),
        as_text(row["name"], "name"),
        _optional(row["parent"]),
        _strings(row["packages"]),
        _strings(row["exact_modules"]),
        _bool(row["planned"]),
        _optional(row["layer"]),
        _strings(row["public"]),
        _strings(row["responsibilities"]),
        _strings(row["forbidden_responsibilities"]),
        _strings(row["planned_public"]),
    )


def _module(value: object) -> Module:
    row = as_object(value, "topology.module")
    try:
        ownership = Ownership(as_text(row["ownership"], "ownership"))
    except ValueError as error:
        raise CoreError("topology: unknown ownership") from error
    component = _optional(row["component"])
    if (ownership is Ownership.OWNED) != (component is not None):
        raise CoreError("topology: ownership and component differ")
    return Module(
        as_text(row["name"], "name"),
        as_text(row["path"], "path"),
        component,
        ownership,
        as_text(row["language"], "language"),
    )


def _edge(value: object, rules: Mapping[str, object]) -> Edge:
    row = as_object(value, "topology.edge")
    try:
        resolution = Resolution(as_text(row["resolution"], "resolution"))
    except ValueError as error:
        raise CoreError("topology: unknown resolution") from error
    evidence = []
    for item in _list(row["evidence"], LIMITS["evidence_per_edge"]):
        location = as_object(item, "topology.location")
        evidence.append(
            Location(as_text(location["path"], "path"), as_count(location["line"], "line"))
        )
    count = as_count(row["count"], "count")
    total = as_count(row["evidence_total"], "evidence_total")
    linked = _strings(row["rules"])
    if (
        count == 0
        or len(evidence) != min(total, LIMITS["evidence_per_edge"])
        or not set(linked) <= rules.keys()
    ):
        raise CoreError("topology: inconsistent edge counts or rule links")
    return Edge(
        as_text(row["id"], "id"),
        as_text(row["source"], "source"),
        as_text(row["target"], "target"),
        resolution,
        count,
        tuple(evidence),
        total,
        linked,
    )


def _require(value: object) -> Require:
    row = as_object(value, "topology.require")
    return Require(
        as_text(row["source"], "source"),
        as_text(row["target"], "target"),
        as_count(row["imports"], "imports"),
        as_text(row["rationale"], "rationale"),
        _strings(row["through"]),
    )


def _layer_order(value: object) -> LayerOrder:
    # The rule is a rule of the contract. A frame that decides no rule can still state it.
    row = as_object(value, "topology.layer_order")
    part = row.get("part")
    return LayerOrder(
        as_text(row["rule"], "rule"),
        _strings(row["layers"]),
        as_text(part, "part") if part is not None else None,
    )


# A component edge names a component or one of these labels, never a module.
_OWNER_LABELS: Final = frozenset({"unowned", "ambiguous"})
_TARGET_LABELS: Final = _OWNER_LABELS | {resolution.value for resolution in Resolution}


def _check_references(topology: "Topology") -> None:
    """Each edge end names a listed row. A list that the budget cut can omit the row.

    A module edge starts at a module; it ends at a module, or at the outside name of an external
    or unresolved import. A component edge starts at a component or `unowned` or `ambiguous`.
    It ends at a component, at one of those labels or at a resolution name (the fallback)."""
    components = {item.id for item in topology.components}
    modules = {item.name for item in topology.modules}
    cut_components = topology.total["components"] > len(components)
    cut_modules = topology.total["modules"] > len(modules)
    for edge in topology.edges:
        local = edge.resolution is Resolution.RESOLVED
        if not cut_modules and (
            edge.source not in modules or (local and edge.target not in modules)
        ):
            raise CoreError("topology: a module edge names no listed module")
    for edge in topology.component_edges:
        if not cut_components and (
            edge.source not in components | _OWNER_LABELS
            or edge.target not in components | _TARGET_LABELS
        ):
            raise CoreError("topology: a component edge names no listed component")
    for require in topology.requires:
        if not cut_components and not {require.source, require.target} <= components:
            raise CoreError("topology: a requirement names no listed component")


def read_topology(value: object, scope: str, rules: Mapping[str, object]) -> Topology:
    """Read the topology part of a frame into typed values and fail closed."""

    row = as_object(value, "topology")
    if as_count(row["version"], "topology.version") != 1:
        raise CoreError("topology: unsupported version")
    budgets = as_object(row["budgets"], "topology.budgets")
    if budgets != LIMITS or any(isinstance(v, bool) for v in budgets.values()):
        raise CoreError("topology: unknown budgets")
    total = {
        key: as_count(value, key)
        for key, value in as_object(row["total"], "topology.total").items()
    }
    complete, truncated = _bool(row["complete"]), _bool(row["truncated"])
    gaps = _strings(row["gaps"])
    lists = {
        key: _list(row[key], LIMITS[key])
        for key in ("components", "modules", "edges", "component_edges", "requires", "layers")
    }
    if any(len(items) != min(total[key], LIMITS[key]) for key, items in lists.items()):
        raise CoreError("topology: inconsistent list counts")
    over = any(total[key] > limit for key, limit in LIMITS.items())
    if (
        truncated != over
        or complete != (not gaps and not truncated)
        or (scope != "complete" and scope not in gaps)
    ):
        raise CoreError("topology: inconsistent completeness")
    topology = Topology(
        complete,
        truncated,
        gaps,
        total,
        tuple(_component(item) for item in lists["components"]),
        tuple(_module(item) for item in lists["modules"]),
        tuple(_edge(item, rules) for item in lists["edges"]),
        tuple(_edge(item, rules) for item in lists["component_edges"]),
        tuple(_require(item) for item in lists["requires"]),
        tuple(_layer_order(item) for item in lists["layers"]),
    )
    _check_references(topology)
    for items in (topology.components, topology.modules, topology.edges, topology.component_edges):
        keys = [item.name if isinstance(item, Module) else item.id for item in items]
        if len(set(keys)) != len(keys):
            raise CoreError("topology: repeated identity")
    pairs = [(item.source, item.target) for item in topology.requires]
    orders = [item.rule for item in topology.layers]
    if len(set(pairs)) != len(pairs) or len(set(orders)) != len(orders):
        raise CoreError("topology: repeated requirement or layer order")
    return topology


def require_topology(frame: Mapping[str, object], request: Mapping[str, object] | None) -> None:
    """A requested section that the frame does not hold is a refusal. A refused collection has
    no reply to project: its own refusal is the message."""
    self_test = frame.get("self_test")
    collect = self_test.get("collect") if isinstance(self_test, Mapping) else None
    if isinstance(collect, Mapping) and "refused" in collect:
        return
    if "topology" not in frame and request is not None and request.get("topology"):
        raise CoreError("the core did not produce the requested topology section")


def frame_topology(frame: Mapping[str, object], rules: Mapping[str, object]) -> Topology | None:
    """The decoded section of a frame, or `None` when the frame has none."""
    if "topology" not in frame:
        return None
    return read_topology(frame["topology"], as_text(frame["scope"], "scope"), rules)
