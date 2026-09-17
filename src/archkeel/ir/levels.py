# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Derive what a declared inside level decides, from one observation alone (AD-34).

A component whose contract names an inside is recorded with its own sub-components, their
packages and their `requires` (AD-20). The verdict here is the one the level above already
uses: a pair crossing two sub-components is covered when the source names the target, and
uncovered otherwise, because absence forbids (AD-32).

What this module does not decide is how a pair is drawn. `observed` and `undecided` are
rendering distinctions with no verdict behind them (AD-24b), so the derivation reports
whether a pair is covered and leaves the colour to the view.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .interfaces import component_owners, owner_of
from .model import Observation, Record, text_value
from .structure import module_edges


@dataclass(frozen=True, slots=True)
class InsideComponent:
    """One sub-component of a declared inside, holding the modules the observation places in it.

    `packages` is what the contract declared; `modules` is what the observation found in them.
    Both travel, because a reader matching modules to owners needs the declared scopes, not the
    names that happened to match.
    """

    label: str
    packages: tuple[str, ...]
    modules: tuple[str, ...]
    public: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class InsideEdge:
    """One ordered pair of sub-components that the observed module imports cross.

    It carries no verdict. The analyzer evaluates the inside contract's `complete_requires`
    and records an uncovered crossing as a violation like any other, so the view reads the
    verdict where every other edge's verdict lives. A second boolean here would be a second
    source for one judgement, free to disagree with the exit code.
    """

    source: str
    target: str
    import_sites: int


@dataclass(frozen=True, slots=True)
class InsideLevel:
    """One component's inside: what it declares, and what the observation makes of it.

    `unassigned` names the parent's modules no sub-component owns. They are carried rather
    than dropped: a module that disappears between two levels is exactly what this tool
    exists to prevent.
    """

    parent: str
    components: tuple[InsideComponent, ...]
    edges: tuple[InsideEdge, ...]
    unassigned: tuple[str, ...]


def _declared_insides(observation: Observation) -> dict[str, list[Record]]:
    grouped: dict[str, list[Record]] = defaultdict(list)
    for record in observation.records("declarations") or ():
        if record.kind != "inside_component_responsibility":
            continue
        if parent := text_value(record.data.get("parent_id")):
            grouped[parent].append(record)
    return grouped


def _public(record: Record) -> tuple[str, ...] | None:
    """An undeclared interface is None; a declared but empty one is an empty tuple."""
    # The codec turns a written list into a tuple, so a list never reaches this reader.
    value = record.data.get("public")
    if not isinstance(value, tuple):
        return None
    return tuple(item for item in value if isinstance(item, str))


def _crossings(
    observation: Observation, inner: tuple[tuple[str, tuple[str, ...]], ...]
) -> dict[tuple[str, str], int]:
    """Sum import sites per ordered sub-component pair; a pair inside one of them never crosses."""
    totals: dict[tuple[str, str], int] = defaultdict(int)
    for source, target, count in module_edges(observation):
        owner_source = owner_of(source, inner)
        owner_target = owner_of(target, inner)
        if owner_source is None or owner_target is None or owner_source == owner_target:
            continue
        totals[(owner_source, owner_target)] += count
    return totals


def inside_levels(observation: Observation) -> tuple[InsideLevel, ...]:
    """Return one level per component whose contract names an inside, ordered by that component."""
    grouped = _declared_insides(observation)
    if not grouped:
        return ()
    outer = component_owners(observation)
    names = tuple(
        name
        for record in observation.records("modules") or ()
        if (name := text_value(record.data.get("qualified_name")))
    )
    levels: list[InsideLevel] = []
    for parent, records in sorted(grouped.items()):
        inner = tuple((record.title, record.subjects) for record in records)
        owned: dict[str, list[str]] = defaultdict(list)
        unassigned: list[str] = []
        for module in sorted(name for name in names if owner_of(name, outer) == parent):
            owner = owner_of(module, inner)
            if owner is None:
                unassigned.append(module)
            else:
                owned[owner].append(module)
        components = tuple(
            sorted(
                (
                    InsideComponent(
                        record.title,
                        record.subjects,
                        tuple(owned[record.title]),
                        _public(record),
                    )
                    for record in records
                ),
                key=lambda item: item.label,
            )
        )
        edges = tuple(
            InsideEdge(source, target, count)
            for (source, target), count in sorted(_crossings(observation, inner).items())
        )
        levels.append(InsideLevel(parent, components, edges, tuple(unassigned)))
    return tuple(levels)
