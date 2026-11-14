# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Decode the optional topology display. It cannot supply a verdict or a scope proof."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from .core_evidence import Location
from .core_json import CoreError, _count, _fields, _object, _text

LIMITS: Final = {
    "components": 4096,
    "modules": 10_000,
    "edges": 20_000,
    "component_edges": 20_000,
    "evidence_per_edge": 5,
}


class Ownership(StrEnum):
    OWNED = "owned"
    UNOWNED = "unowned"
    AMBIGUOUS = "ambiguous"


class Resolution(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    EXTERNAL = "external"


@dataclass(frozen=True, slots=True)
class Component:
    id: str
    name: str
    parent: str | None
    packages: tuple[str, ...]
    exact_modules: tuple[str, ...]
    planned: bool


@dataclass(frozen=True, slots=True)
class Module:
    name: str
    path: str
    component: str | None
    ownership: Ownership


@dataclass(frozen=True, slots=True)
class Edge:
    id: str
    source: str
    target: str
    resolution: Resolution
    count: int
    evidence: tuple[Location, ...]
    evidence_total: int
    rules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Topology:
    complete: bool
    truncated: bool
    gaps: tuple[str, ...]
    total: Mapping[str, int]
    components: tuple[Component, ...]
    modules: tuple[Module, ...]
    edges: tuple[Edge, ...]
    component_edges: tuple[Edge, ...]


def _bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise CoreError("topology: expected a boolean")
    return value


def _optional(value: object) -> str | None:
    return None if value is None else _text(value, "topology")


def _list(value: object, limit: int) -> list[object]:
    if not isinstance(value, list) or len(value) > limit:
        raise CoreError("topology: invalid or over-budget list")
    return value


def _strings(value: object) -> tuple[str, ...]:
    return tuple(_text(item, "topology") for item in _list(value, 100_000))


def _component(value: object) -> Component:
    row = _fields(value, "topology.component", frozenset(Component.__dataclass_fields__))
    return Component(
        _text(row["id"], "id"),
        _text(row["name"], "name"),
        _optional(row["parent"]),
        _strings(row["packages"]),
        _strings(row["exact_modules"]),
        _bool(row["planned"]),
    )


def _module(value: object) -> Module:
    row = _fields(value, "topology.module", frozenset(Module.__dataclass_fields__))
    try:
        ownership = Ownership(_text(row["ownership"], "ownership"))
    except ValueError as error:
        raise CoreError("topology: unknown ownership") from error
    component = _optional(row["component"])
    if (ownership is Ownership.OWNED) != (component is not None):
        raise CoreError("topology: ownership and component differ")
    return Module(_text(row["name"], "name"), _text(row["path"], "path"), component, ownership)


def _edge(value: object, rules: Mapping[str, object]) -> Edge:
    row = _fields(value, "topology.edge", frozenset(Edge.__dataclass_fields__))
    try:
        resolution = Resolution(_text(row["resolution"], "resolution"))
    except ValueError as error:
        raise CoreError("topology: unknown resolution") from error
    evidence = []
    for item in _list(row["evidence"], LIMITS["evidence_per_edge"]):
        location = _fields(item, "topology.location", frozenset({"path", "line"}))
        evidence.append(Location(_text(location["path"], "path"), _count(location["line"], "line")))
    count = _count(row["count"], "count")
    total = _count(row["evidence_total"], "evidence_total")
    linked = _strings(row["rules"])
    if (
        count == 0
        or len(evidence) != min(total, LIMITS["evidence_per_edge"])
        or not set(linked) <= rules.keys()
    ):
        raise CoreError("topology: inconsistent edge counts or rule links")
    return Edge(
        _text(row["id"], "id"),
        _text(row["source"], "source"),
        _text(row["target"], "target"),
        resolution,
        count,
        tuple(evidence),
        total,
        linked,
    )


def read_topology(value: object, scope: str, rules: Mapping[str, object]) -> Topology:
    row = _fields(
        value,
        "topology",
        frozenset(
            {
                "version",
                "complete",
                "gaps",
                "truncated",
                "budgets",
                "total",
                "components",
                "modules",
                "edges",
                "component_edges",
            }
        ),
    )
    if _count(row["version"], "topology.version") != 1:
        raise CoreError("topology: unsupported version")
    budgets = _object(row["budgets"], "topology.budgets")
    if budgets != LIMITS or any(isinstance(v, bool) for v in budgets.values()):
        raise CoreError("topology: unknown budgets")
    total = {
        key: _count(value, key)
        for key, value in _fields(row["total"], "topology.total", frozenset(LIMITS)).items()
    }
    complete, truncated = _bool(row["complete"]), _bool(row["truncated"])
    gaps = _strings(row["gaps"])
    lists = {
        key: _list(row[key], LIMITS[key])
        for key in ("components", "modules", "edges", "component_edges")
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
    )
    for items in (topology.components, topology.modules, topology.edges, topology.component_edges):
        keys = [item.name if isinstance(item, Module) else item.id for item in items]
        if len(set(keys)) != len(keys):
            raise CoreError("topology: repeated identity")
    return topology


def require_topology(frame: Mapping[str, object], request: Mapping[str, object] | None) -> None:
    """A requested section that the frame does not hold is a refusal."""
    if "topology" not in frame and request is not None and request.get("topology"):
        raise CoreError("the core did not produce the requested topology section")


def frame_topology(frame: Mapping[str, object], rules: Mapping[str, object]) -> Topology | None:
    """The decoded section of a frame, or `None` when the frame has none."""
    if "topology" not in frame:
        return None
    return read_topology(frame["topology"], _text(frame["scope"], "scope"), rules)
