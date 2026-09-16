# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Derive size and coupling per component and per package from one observation (AD-21).

Report-only by decision: no verdict, no rule and no exit code reads these numbers. They
answer where the code is dense and where the analyzer sees least, which a global ratio
hides. The derivation reads modules, module-level edges and call records, so a report
rendered later from `architecture.json` bytes alone produces the same table.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal, TypeAlias

from .interfaces import component_owners, owner_of
from .model import Observation

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


def _name(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 1


def _module_names(observation: Observation) -> tuple[str, ...]:
    return tuple(
        name
        for record in observation.records("modules") or ()
        if (name := _name(record.data.get("qualified_name"))) is not None
    )


def _module_edges(observation: Observation) -> tuple[tuple[str, str, int], ...]:
    edges: list[tuple[str, str, int]] = []
    for record in observation.records("dependency_edges") or ():
        if record.data.get("level") != "module":
            continue
        source = _name(record.data.get("source"))
        target = _name(record.data.get("target"))
        if source is not None and target is not None:
            edges.append((source, target, _count(record.data.get("count"))))
    return tuple(edges)


def _calls_by_module(observation: Observation) -> tuple[Counter[str], Counter[str]]:
    total: Counter[str] = Counter()
    unresolved: Counter[str] = Counter()
    for record in observation.records("calls") or ():
        module = _name(record.data.get("source_module"))
        if module is None:
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
    edges = _module_edges(observation)
    calls, unresolved = _calls_by_module(observation)
    by_component = {
        module: owner for module in names if (owner := owner_of(module, components)) is not None
    }
    by_package = {module: module.rpartition(".")[0] or module for module in names}
    return _aggregate("component", by_component, edges, calls, unresolved) + _aggregate(
        "package", by_package, edges, calls, unresolved
    )
