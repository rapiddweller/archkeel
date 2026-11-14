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

from .core_json import CoreError, _count, _fields, _object, _text

BUDGETS: Final = {
    "cycles_per_rule": 50,
    "path_steps": 64,
    "evidence_per_step": 5,
    "held_per_rule": 20,
    "rules_per_gap": 200,
    "gaps": 500,
}


class Direction(StrEnum):
    FORBIDS = "forbids"
    ALLOWS = "allows"
    REQUIRES = "requires"
    ISOLATES = "isolates"
    ORDERS = "orders"
    ACYCLIC = "acyclic"
    NONE = "none"


class HoldKind(StrEnum):
    COVERAGE_GAPS = "coverage_gaps"
    PAIR_GAPS = "pair_gaps"
    ALLOWED_PAIR_GAPS = "allowed_pair_gaps"
    UNKNOWN_IMPORTS = "unknown_imports"
    NO_SOURCE_FILES = "no_source_files"
    OTHER = "other"


_CAUSES: Final = frozenset(
    {"scope_incomplete", "no_receipt", "undecided", "ownership_blocker", "no_decided_rule"}
)
_Word = TypeVar("_Word", bound=StrEnum)


@dataclass(frozen=True, slots=True)
class RuleShape:
    kind: str
    direction: Direction
    source: tuple[str, ...]
    target: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Step:
    source: str
    target: str
    source_component: str | None
    target_component: str | None
    imports: int
    evidence: tuple[str, ...]
    evidence_total: int


@dataclass(frozen=True, slots=True)
class CyclePath:
    id: str
    index: int
    members: tuple[str, ...]
    path: tuple[Step, ...]
    steps_total: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class Cycles:
    total: int
    truncated: bool
    items: tuple[CyclePath, ...]


@dataclass(frozen=True, slots=True)
class RuleHolds:
    cause: str
    kind: HoldKind
    gaps: tuple[str, ...]
    pairs: tuple[tuple[str, str], ...]
    total: int
    truncated: bool
    unnamed_imports: int


@dataclass(frozen=True, slots=True)
class GapHolds:
    id: str
    kind: str
    reason: str
    rules: tuple[str, ...]
    rules_total: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class Explain:
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
    return tuple(_text(item, where) for item in _list(value, where, limit))


def _word(kind: type[_Word], value: object, where: str) -> _Word:
    try:
        return kind(_text(value, where))
    except ValueError as error:
        raise CoreError(f"the core frame field {where} has an unknown word") from error


def _optional(value: object, where: str) -> str | None:
    return None if value is None else _text(value, where)


def _shape(value: object, where: str) -> RuleShape:
    row = _fields(value, where, frozenset({"kind", "direction", "source", "target"}))
    return RuleShape(
        _text(row["kind"], where),
        _word(Direction, row["direction"], where),
        _texts(row["source"], where),
        _texts(row["target"], where),
    )


def _step(value: object, where: str) -> Step:
    names = frozenset(
        {"from", "to", "from_component", "to_component", "imports", "evidence", "evidence_total"}
    )
    row = _fields(value, where, names)
    evidence = _texts(row["evidence"], where, BUDGETS["evidence_per_step"])
    total = _count(row["evidence_total"], where)
    if len(evidence) != min(total, BUDGETS["evidence_per_step"]):
        raise CoreError(f"the core frame field {where} has an inconsistent evidence count")
    return Step(
        _text(row["from"], where),
        _text(row["to"], where),
        _optional(row["from_component"], where),
        _optional(row["to_component"], where),
        _count(row["imports"], where),
        evidence,
        total,
    )


def _closed(path: tuple[Step, ...], truncated: bool, where: str) -> None:
    """The steps follow each other. A whole path ends where it starts."""
    for before, after in zip(path, path[1:], strict=False):
        if before.target != after.source:
            raise CoreError(f"the core frame field {where} has a broken path")
    if path and not truncated and path[-1].target != path[0].source:
        raise CoreError(f"the core frame field {where} has a path that does not close")


def _cycle(value: object, where: str) -> CyclePath:
    names = frozenset({"id", "index", "members", "path", "steps_total", "truncated"})
    row = _fields(value, where, names)
    steps = _list(row["path"], where, BUDGETS["path_steps"])
    path = tuple(_step(item, where) for item in steps)
    total = _count(row["steps_total"], where)
    truncated = _bool(row["truncated"], where)
    cut = total > BUDGETS["path_steps"]
    if len(path) != min(total, BUDGETS["path_steps"]) or truncated != cut:
        raise CoreError(f"the core frame field {where} has an inconsistent step count")
    _closed(path, truncated, where)
    return CyclePath(
        _text(row["id"], where),
        _count(row["index"], where),
        _texts(row["members"], where),
        path,
        total,
        truncated,
    )


def _cycles(value: object, where: str) -> Cycles:
    row = _fields(value, where, frozenset({"total", "truncated", "items"}))
    listed = _list(row["items"], where, BUDGETS["cycles_per_rule"])
    items = tuple(_cycle(item, where) for item in listed)
    total = _count(row["total"], where)
    truncated = _bool(row["truncated"], where)
    cut = total > BUDGETS["cycles_per_rule"]
    if len(items) != min(total, BUDGETS["cycles_per_rule"]) or truncated != cut:
        raise CoreError(f"the core frame field {where} has an inconsistent cycle count")
    return Cycles(total, truncated, items)


def _pair(value: object, where: str) -> tuple[str, str]:
    row = _fields(value, where, frozenset({"source", "target"}))
    return _text(row["source"], where), _text(row["target"], where)


def _rule_holds(value: object, where: str) -> RuleHolds:
    names = frozenset({"cause", "kind", "gaps", "pairs", "total", "truncated", "unnamed_imports"})
    row = _fields(value, where, names)
    cause = _text(row["cause"], where)
    if cause not in _CAUSES:
        raise CoreError(f"the core frame field {where} has an unknown cause")
    limit = BUDGETS["held_per_rule"]
    gaps = _texts(row["gaps"], where, limit)
    pairs = tuple(_pair(item, where) for item in _list(row["pairs"], where, limit))
    total = _count(row["total"], where)
    truncated = _bool(row["truncated"], where)
    if truncated != (total > limit) or max(len(gaps), len(pairs)) > min(total, limit):
        raise CoreError(f"the core frame field {where} has an inconsistent hold count")
    return RuleHolds(
        cause,
        _word(HoldKind, row["kind"], where),
        gaps,
        pairs,
        total,
        truncated,
        _count(row["unnamed_imports"], where),
    )


def _gap(value: object, where: str) -> GapHolds:
    names = frozenset({"id", "kind", "reason", "rules", "rules_total", "truncated"})
    row = _fields(value, where, names)
    rules = _texts(row["rules"], where, BUDGETS["rules_per_gap"])
    total = _count(row["rules_total"], where)
    truncated = _bool(row["truncated"], where)
    cut = total > BUDGETS["rules_per_gap"]
    if len(rules) != min(total, BUDGETS["rules_per_gap"]) or truncated != cut:
        raise CoreError(f"the core frame field {where} has an inconsistent rule count")
    return GapHolds(
        _text(row["id"], where),
        _text(row["kind"], where),
        _text(row["reason"], where),
        rules,
        total,
        truncated,
    )


def read_explain(
    value: object, rules: Mapping[str, object], violations: Mapping[str, int]
) -> Explain:
    """The decoded part. A cycle list names a rule of the frame with that many violations."""
    row = _fields(value, "explain", frozenset({"version", "budgets", "rules", "cycles", "holds"}))
    if _count(row["version"], "explain.version") != 1:
        raise CoreError("the core frame field explain has an unknown version")
    if _object(row["budgets"], "explain.budgets") != BUDGETS:
        raise CoreError("the core frame field explain has other budgets")
    shapes = {
        rule: _shape(shape, f"explain.rules.{rule}")
        for rule, shape in _object(row["rules"], "explain.rules").items()
    }
    cycles = {
        rule: _cycles(item, f"explain.cycles.{rule}")
        for rule, item in _object(row["cycles"], "explain.cycles").items()
    }
    for rule, found in cycles.items():
        count = violations.get(rule)
        if count is None or any(item.index >= count for item in found.items):
            raise CoreError(f"the core frame field explain.cycles.{rule} names no violation")
    names = frozenset({"rules", "gaps", "gaps_total", "gaps_holding", "gaps_truncated"})
    holds = _fields(row["holds"], "explain.holds", names)
    per_rule = {
        rule: _rule_holds(item, f"explain.holds.rules.{rule}")
        for rule, item in _object(holds["rules"], "explain.holds.rules").items()
    }
    listed = _list(holds["gaps"], "explain.holds.gaps", BUDGETS["gaps"])
    gaps = tuple(_gap(item, "explain.holds.gaps") for item in listed)
    gaps_holding = _count(holds["gaps_holding"], "explain.holds")
    gaps_truncated = _bool(holds["gaps_truncated"], "explain.holds")
    cut = gaps_holding > BUDGETS["gaps"]
    if len(gaps) != min(gaps_holding, BUDGETS["gaps"]) or gaps_truncated != cut:
        raise CoreError("the core frame field explain.holds has an inconsistent gap count")
    if unknown := sorted(set(per_rule) - set(shapes) - set(rules)):
        raise CoreError(f"the core frame field explain.holds names no rule: {unknown[0]}")
    return Explain(
        shapes,
        cycles,
        per_rule,
        gaps,
        _count(holds["gaps_total"], "explain.holds"),
        gaps_holding,
        gaps_truncated,
    )
