# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Decode the `explain` part of the frame (AD-484): rule shapes, cycle paths and gap holds.

The part states what the model and the evaluator hold. It cannot supply a verdict, a scope proof
or a gap. Each list has a budget, and a list over its budget is cut with `truncated` and its
exact total.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, TypeVar

from .core_json import CoreError, as_count, as_object, as_text
from .core_schema import budget


class _Direction(StrEnum):
    """The direction that a rule gives to the pairs it judges."""

    FORBIDS = "forbids"
    ALLOWS = "allows"
    REQUIRES = "requires"
    ISOLATES = "isolates"
    ORDERS = "orders"
    ACYCLIC = "acyclic"
    NONE = "none"


class _HoldKind(StrEnum):
    """The reason class that holds a rule at UNKNOWN."""

    COVERAGE_GAPS = "coverage_gaps"
    PAIR_GAPS = "pair_gaps"
    ALLOWED_PAIR_GAPS = "allowed_pair_gaps"
    SCOPED_GAPS = "scoped_gaps"
    UNKNOWN_IMPORTS = "unknown_imports"
    INTERFACE_IMPORTS = "interface_imports"
    NO_SOURCE_FILES = "no_source_files"
    OTHER = "other"


class _InterfaceGap(StrEnum):
    """The missing fact that holds an `interface_boundary` import."""

    UNREAD_BINDING = "unread_binding"
    PUBLICATION_ROUTE = "publication_route"
    PUBLICATION_SURFACE = "publication_surface"
    TYPE_PUBLICATION = "type_publication"


class _PairOrigin(StrEnum):
    """Why a module pair holds an `interface_boundary` rule."""

    UNOBSERVED_MODULE = "unobserved_module"
    DISPATCH = "dispatch"
    NOT_EXECUTION_ONLY = "not_execution_only"
    UNOWNED_END = "unowned_end"
    NAMED_SITE = "named_site"


class _HoldClass(StrEnum):
    """The cause class that the collector states for a held import."""

    NOT_STATED = "not_stated"
    AMBIGUOUS_REEXPORT = "ambiguous_reexport"
    UNCERTAIN_HOP = "uncertain_hop"
    UNREAD_ALL = "unread_all"
    OUTSIDE_WRITE = "outside_write"
    ESCAPED = "escaped"
    ESCAPED_WRITE = "escaped_write"
    ESCAPED_NAMESPACE = "escaped_namespace"
    ESCAPED_CHILD_MODULE = "escaped_child_module"
    ESCAPED_VALUE = "escaped_value"
    ESCAPED_NAME = "escaped_name"
    TYPE_CHECKING_REEXPORT = "type_checking_reexport"


_CAUSES: Final = frozenset(
    {"scope_incomplete", "no_receipt", "undecided", "ownership_blocker", "no_decided_rule"}
)
_Word = TypeVar("_Word", bound=StrEnum)


@dataclass(frozen=True, slots=True)
class RuleShape:
    """The kind of a rule, its direction and the sources and targets it selects."""

    kind: str
    direction: _Direction
    source: tuple[str, ...]
    target: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DeclaredEdge:
    """A possible import that a declaration supplies: its id, its site module and the target."""

    declaration: str
    source: str
    target: str


@dataclass(frozen=True, slots=True)
class Step:
    """One import edge on a path of a cycle, with the evidence for it."""

    source: str
    target: str
    source_component: str | None
    target_component: str | None
    imports: int
    evidence: tuple[str, ...]
    evidence_total: int
    declared: tuple[DeclaredEdge, ...] = ()


@dataclass(frozen=True, slots=True)
class CyclePath:
    """One cycle: its members and the import path through them."""

    id: str
    index: int
    members: tuple[str, ...]
    path: tuple[Step, ...]
    steps_total: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class Cycles:
    """The cycles of one rule, counted and possibly truncated."""

    total: int
    truncated: bool
    items: tuple[CyclePath, ...]


@dataclass(frozen=True, slots=True)
class HeldImport:
    """One import that holds an `interface_boundary` rule, with the cause that the core states."""

    source: str
    target: str
    name: str | None
    gap: _InterfaceGap
    cause_class: _HoldClass
    cause: Mapping[str, object] | None
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InterfaceHolds:
    """The held imports of one `interface_boundary` rule: the count of each class and the first."""

    classes: tuple[tuple[_InterfaceGap, _HoldClass, int], ...]
    imports: tuple[HeldImport, ...]
    places: tuple[tuple[_HoldClass, str, int], ...] = ()


@dataclass(frozen=True, slots=True)
class RuleHolds:
    """What holds one rule at UNKNOWN: the cause, the gaps and the pairs."""

    cause: str
    kind: _HoldKind
    gaps: tuple[str, ...]
    pairs: tuple[tuple[str, str], ...]
    total: int
    truncated: bool
    unnamed_imports: int
    interface: InterfaceHolds | None = None
    origins: tuple[tuple[_PairOrigin, int], ...] = ()
    pair_origins: tuple[_PairOrigin | None, ...] = ()


@dataclass(frozen=True, slots=True)
class GapHolds:
    """One gap and the rules that it holds at UNKNOWN."""

    id: str
    kind: str
    reason: str
    rules: tuple[str, ...]
    rules_total: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class Explain:
    """The explanation part of a frame: rule shapes, cycles, holds and gaps."""

    rules: Mapping[str, RuleShape]
    cycles: Mapping[str, Cycles]
    holds: Mapping[str, RuleHolds]
    gaps: tuple[GapHolds, ...]
    gaps_total: int
    gaps_holding: int
    gaps_truncated: bool


def _bool(value: object, where: str) -> bool:
    if not isinstance(value, bool):
        raise CoreError(f"the core frame field {where} is not a boolean")
    return value


def _list(value: object, where: str, limit: int) -> list[object]:
    if not isinstance(value, list) or len(value) > limit:
        raise CoreError(f"the core frame field {where} is not a list within its budget")
    return value


def _texts(value: object, where: str, limit: int = 100_000) -> tuple[str, ...]:
    return tuple(as_text(item, where) for item in _list(value, where, limit))


def _word(kind: type[_Word], value: object, where: str) -> _Word:
    try:
        return kind(as_text(value, where))
    except ValueError as error:
        raise CoreError(f"the core frame field {where} has an unknown word") from error


def _optional(value: object, where: str) -> str | None:
    return None if value is None else as_text(value, where)


def _shape(value: object, where: str) -> RuleShape:
    row = as_object(value, where)
    return RuleShape(
        as_text(row["kind"], where),
        _word(_Direction, row["direction"], where),
        _texts(row["source"], where),
        _texts(row["target"], where),
    )


def _step(value: object, where: str) -> Step:
    row = as_object(value, where)
    evidence = _texts(row["evidence"], where, budget("evidence_per_step"))
    total = as_count(row["evidence_total"], where)
    if len(evidence) != min(total, budget("evidence_per_step")):
        raise CoreError(f"the core frame field {where} has an inconsistent evidence count")
    return Step(
        as_text(row["from"], where),
        as_text(row["to"], where),
        _optional(row["from_component"], where),
        _optional(row["to_component"], where),
        as_count(row["imports"], where),
        evidence,
        total,
        tuple(_declared_edge(item, where) for item in _items(row.get("declared", []), where)),
    )


def _items(value: object, where: str) -> list[object]:
    if not isinstance(value, list):
        raise CoreError(f"the core frame field {where} is not a list")
    return value


def _declared_edge(value: object, where: str) -> DeclaredEdge:
    row = as_object(value, where)
    return DeclaredEdge(
        as_text(row["declaration"], where),
        as_text(row["source"], where),
        as_text(row["target"], where),
    )


def _closed(path: tuple[Step, ...], truncated: bool, where: str) -> None:
    """The steps follow each other. A whole path ends where it starts."""
    for before, after in zip(path, path[1:], strict=False):
        if before.target != after.source:
            raise CoreError(f"the core frame field {where} has a broken path")
    if path and not truncated and path[-1].target != path[0].source:
        raise CoreError(f"the core frame field {where} has a path that does not close")


def _cycle(value: object, where: str) -> CyclePath:
    row = as_object(value, where)
    steps = _list(row["path"], where, budget("path_steps"))
    path = tuple(_step(item, where) for item in steps)
    total = as_count(row["steps_total"], where)
    truncated = _bool(row["truncated"], where)
    cut = total > budget("path_steps")
    if len(path) != min(total, budget("path_steps")) or truncated != cut:
        raise CoreError(f"the core frame field {where} has an inconsistent step count")
    _closed(path, truncated, where)
    return CyclePath(
        as_text(row["id"], where),
        as_count(row["index"], where),
        _texts(row["members"], where),
        path,
        total,
        truncated,
    )


def _cycles(value: object, where: str) -> Cycles:
    row = as_object(value, where)
    listed = _list(row["items"], where, budget("cycles_per_rule"))
    items = tuple(_cycle(item, where) for item in listed)
    total = as_count(row["total"], where)
    truncated = _bool(row["truncated"], where)
    cut = total > budget("cycles_per_rule")
    if len(items) != min(total, budget("cycles_per_rule")) or truncated != cut:
        raise CoreError(f"the core frame field {where} has an inconsistent cycle count")
    return Cycles(total, truncated, items)


def _pair(value: object, where: str) -> tuple[str, str]:
    row = as_object(value, where)
    return as_text(row["source"], where), as_text(row["target"], where)


def _pair_origin(value: object, where: str) -> _PairOrigin | None:
    origin = as_object(value, where).get("origin")
    return None if origin is None else _word(_PairOrigin, origin, where)


def _origins(value: object, where: str) -> tuple[tuple[_PairOrigin, int], ...]:
    rows = [as_object(item, where) for item in _list(value or [], where, 100_000)]
    return tuple(
        (_word(_PairOrigin, r["origin"], where), as_count(r["count"], where)) for r in rows
    )


def _held_import(value: object, where: str) -> HeldImport:
    row = as_object(value, where)
    name, cause = row["name"], row["cause"]
    return HeldImport(
        as_text(row["source"], where),
        as_text(row["target"], where),
        None if name is None else as_text(name, where),
        _word(_InterfaceGap, row["gap"], where),
        _word(_HoldClass, row["class"], where),
        None if cause is None else as_object(cause, where),
        _texts(row["evidence"], where),
    )


def _interface(value: object, where: str) -> InterfaceHolds:
    row = as_object(value, where)
    classes = tuple(
        (
            _word(_InterfaceGap, as_object(item, where)["gap"], where),
            _word(_HoldClass, as_object(item, where)["class"], where),
            as_count(as_object(item, where)["count"], where),
        )
        for item in _list(row["classes"], where, 100_000)
    )
    imports = tuple(
        _held_import(item, where) for item in _list(row["imports"], where, budget("held_per_rule"))
    )
    places = tuple(
        (
            _word(_HoldClass, as_object(item, where)["class"], where),
            as_text(as_object(item, where)["at"], where),
            as_count(as_object(item, where)["count"], where),
        )
        for item in _list(row.get("places", []), where, 100_000)
    )
    return InterfaceHolds(classes, imports, places)


def _rule_holds(value: object, where: str) -> RuleHolds:
    row = as_object(value, where)
    cause = as_text(row["cause"], where)
    if cause not in _CAUSES:
        raise CoreError(f"the core frame field {where} has an unknown cause")
    limit = budget("held_per_rule")
    gaps = _texts(row["gaps"], where, limit)
    pairs = tuple(_pair(item, where) for item in _list(row["pairs"], where, limit))
    total = as_count(row["total"], where)
    truncated = _bool(row["truncated"], where)
    interface = row.get("interface")
    held = None if interface is None else _interface(interface, where)
    listed = max(len(gaps), len(pairs), len(held.imports) if held else 0)
    if truncated != (total > limit) or listed > min(total, limit):
        raise CoreError(f"the core frame field {where} has an inconsistent hold count")
    return RuleHolds(
        cause,
        _word(_HoldKind, row["kind"], where),
        gaps,
        pairs,
        total,
        truncated,
        as_count(row["unnamed_imports"], where),
        held,
        _origins(row.get("origins"), where),
        tuple(_pair_origin(item, where) for item in _list(row["pairs"], where, limit)),
    )


def _gap(value: object, where: str) -> GapHolds:
    row = as_object(value, where)
    rules = _texts(row["rules"], where, budget("rules_per_gap"))
    total = as_count(row["rules_total"], where)
    truncated = _bool(row["truncated"], where)
    cut = total > budget("rules_per_gap")
    if len(rules) != min(total, budget("rules_per_gap")) or truncated != cut:
        raise CoreError(f"the core frame field {where} has an inconsistent rule count")
    return GapHolds(
        as_text(row["id"], where),
        as_text(row["kind"], where),
        as_text(row["reason"], where),
        rules,
        total,
        truncated,
    )


def read_explain(value: object, violations: Mapping[str, int]) -> Explain:
    """The decoded part. A cycle list names a rule of the frame with that many violations.

    A hold can name a row that is no rule of the contract: a named gap or the UML target row.
    """
    row = as_object(value, "explain")
    shapes = {
        rule: _shape(shape, f"explain.rules.{rule}")
        for rule, shape in as_object(row["rules"], "explain.rules").items()
    }
    cycles = {
        rule: _cycles(item, f"explain.cycles.{rule}")
        for rule, item in as_object(row["cycles"], "explain.cycles").items()
    }
    for rule, found in cycles.items():
        count = violations.get(rule)
        if count is None or any(item.index >= count for item in found.items):
            raise CoreError(f"the core frame field explain.cycles.{rule} names no violation")
    holds = as_object(row["holds"], "explain.holds")
    per_rule = {
        rule: _rule_holds(item, f"explain.holds.rules.{rule}")
        for rule, item in as_object(holds["rules"], "explain.holds.rules").items()
    }
    listed = _list(holds["gaps"], "explain.holds.gaps", budget("gaps"))
    gaps = tuple(_gap(item, "explain.holds.gaps") for item in listed)
    gaps_holding = as_count(holds["gaps_holding"], "explain.holds")
    gaps_truncated = _bool(holds["gaps_truncated"], "explain.holds")
    cut = gaps_holding > budget("gaps")
    if len(gaps) != min(gaps_holding, budget("gaps")) or gaps_truncated != cut:
        raise CoreError("the core frame field explain.holds has an inconsistent gap count")
    return Explain(
        shapes,
        cycles,
        per_rule,
        gaps,
        as_count(holds["gaps_total"], "explain.holds"),
        gaps_holding,
        gaps_truncated,
    )
