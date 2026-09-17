# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Derive size and coupling per component and per package from one observation (AD-21).

Report-only by decision: no verdict, no rule and no exit code reads these numbers. They
answer where the code is dense and where the analyzer sees least, which a global ratio
hides. The derivation reads modules, module-level edges and call records, so a report
rendered later from `architecture.json` bytes alone produces the same table.

The same measurements carry the AD-33 claim at the end of this file, which names a
component whose inside outgrows the level holding it. Deriving both here keeps one
source for a component's size, so the claim and the table cannot disagree.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal, TypeAlias

from .interfaces import component_owners, owner_of
from .model import ComparisonStatus, Observation, int_value, text_value

StructureLevel: TypeAlias = Literal["component", "package"]


@dataclass(frozen=True, slots=True)
class StructureMetric:
    """One scope measured: its modules, the edges inside it and the calls it makes."""

    scope: str
    level: StructureLevel
    modules: int
    inner_edges: int
    fan_in: int
    fan_out: int
    calls: int
    unresolved: int


def _module_names(observation: Observation) -> tuple[str, ...]:
    return tuple(
        name
        for record in observation.records("modules") or ()
        if (name := text_value(record.data.get("qualified_name")))
    )


def module_edges(observation: Observation) -> tuple[tuple[str, str, int], ...]:
    """Return every observed module-level edge as source, target and import sites.

    Public because the inside level derives from the same edges (AD-34): one reader keeps
    the two levels measuring the same thing.
    """
    edges: list[tuple[str, str, int]] = []
    for record in observation.records("dependency_edges") or ():
        if record.data.get("level") != "module":
            continue
        source = text_value(record.data.get("source"))
        target = text_value(record.data.get("target"))
        if source and target:
            edges.append((source, target, int_value(record.data.get("count"), default=1)))
    return tuple(edges)


def _calls_by_module(observation: Observation) -> tuple[Counter[str], Counter[str]]:
    total: Counter[str] = Counter()
    unresolved: Counter[str] = Counter()
    for record in observation.records("calls") or ():
        module = text_value(record.data.get("source_module"))
        if not module:
            continue
        total[module] += 1
        if record.data.get("status") == "unresolved":
            unresolved[module] += 1
    return total, unresolved


def _aggregate(
    level: StructureLevel,
    scope_of: dict[str, str],
    edges: tuple[tuple[str, str, int], ...],
    calls: Counter[str],
    unresolved: Counter[str],
) -> tuple[StructureMetric, ...]:
    modules: Counter[str] = Counter()
    inner: Counter[str] = Counter()
    fan_in: Counter[str] = Counter()
    fan_out: Counter[str] = Counter()
    call_count: Counter[str] = Counter()
    unresolved_count: Counter[str] = Counter()
    for module, scope in scope_of.items():
        modules[scope] += 1
        call_count[scope] += calls[module]
        unresolved_count[scope] += unresolved[module]
    for source, target, _ in edges:
        source_scope = scope_of.get(source)
        target_scope = scope_of.get(target)
        if source_scope is None or target_scope is None:
            continue
        if source_scope == target_scope:
            inner[source_scope] += 1
            continue
        fan_out[source_scope] += 1
        fan_in[target_scope] += 1
    return tuple(
        StructureMetric(
            scope=scope,
            level=level,
            modules=modules[scope],
            inner_edges=inner[scope],
            fan_in=fan_in[scope],
            fan_out=fan_out[scope],
            calls=call_count[scope],
            unresolved=unresolved_count[scope],
        )
        for scope in sorted(modules)
    )


def structure_metrics(observation: Observation) -> tuple[StructureMetric, ...]:
    """Measure every declared component and every observed package of one observation."""
    components = component_owners(observation)
    names = _module_names(observation)
    edges = module_edges(observation)
    calls, unresolved = _calls_by_module(observation)
    by_component = {
        module: owner for module in names if (owner := owner_of(module, components)) is not None
    }
    by_package = {module: module.rpartition(".")[0] or module for module in names}
    return _aggregate("component", by_component, edges, calls, unresolved) + _aggregate(
        "package", by_package, edges, calls, unresolved
    )


@dataclass(frozen=True, slots=True)
class OversizedInside:
    """One component that holds more than the level containing it (AD-33)."""

    scope: str
    modules: int
    inner_edges: int


@dataclass(frozen=True, slots=True)
class InsideSizes:
    """The claim: the top level's own size, and the components whose inside exceeds it."""

    status: ComparisonStatus
    components: int = 0
    component_edges: int = 0
    candidates: tuple[OversizedInside, ...] = ()

    def __post_init__(self) -> None:
        if self.status == "UNKNOWN" and (
            self.components or self.component_edges or self.candidates
        ):
            raise ValueError("an unsupported claim names no component")


def _component_edge_count(
    observation: Observation, components: tuple[tuple[str, tuple[str, ...]], ...]
) -> int:
    """Count the ordered component pairs the observed module edges cross."""
    return len(
        {
            (source_owner, target_owner)
            for source, target, _ in module_edges(observation)
            if (source_owner := owner_of(source, components)) is not None
            and (target_owner := owner_of(target, components)) is not None
            and source_owner != target_owner
        }
    )


def oversized_insides(observation: Observation) -> InsideSizes:
    """Name each component whose inside outgrows the top level, or UNKNOWN (AD-33).

    Both signals gate the claim: without dependency edges the comparison would measure
    against zero component edges and call every component with one inner edge large.
    """
    if observation.records("modules") is None or observation.records("dependency_edges") is None:
        return InsideSizes("UNKNOWN")
    components = component_owners(observation)
    edges = _component_edge_count(observation, components)
    candidates = tuple(
        OversizedInside(metric.scope, metric.modules, metric.inner_edges)
        for metric in structure_metrics(observation)
        if metric.level == "component"
        and (metric.modules > len(components) or metric.inner_edges > edges)
    )
    return InsideSizes("SUPPORTED", len(components), edges, candidates)
