# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-335: each rule kind and field that names a module is checked for a scope below a crate root.

Consumer: `check/evaluation/crate_scope.py`. The Rust collector writes no edge inside a crate, so a
rule that names a module below a crate root must be UNKNOWN. The tables below list every rule kind
and every field of the catalog. A new rule kind or a new field fails the test until a person
decides whether it names a module and adds it to `EDGE_FIELDS` or to the reviewed lists.
"""

from __future__ import annotations

import dataclasses
import typing
from types import SimpleNamespace
from typing import Any

import pytest

from archkeel.check.evaluation.crate_scope import EDGE_FIELDS, NO_INTERNAL_EDGES, _rule_scopes
from archkeel.ir.architecture_graph import ArchitectureRuleKind as Kind
from archkeel.ir.model import (
    AllowedDependencyRule,
    ArchitectureRule,
    DecisionMaker,
    ForbiddenDependencyRule,
    SiblingIsolationRule,
)
from archkeel.ir.profiles import RUST

INFRASTRUCTURE = {"id", "kind", "rationale", "provenance", "decided_by"}
# Every field of a rule that this profile decides, as reviewed on the day of AD-335. A field that
# is not here is new: decide whether it names a module, then add it here or to `EDGE_FIELDS`.
REVIEWED = {
    Kind.FORBIDDEN_DEPENDENCY: {
        "source",
        "target",
        "include_type_checking",
        "target_symbol",
        "allowed_sources",
        "source_match",
        "target_match",
        "target_kind",
    },
    Kind.ALLOWED_DEPENDENCY: {"source", "target"},
    Kind.SIBLING_ISOLATION: {"members", "include_type_checking"},
    Kind.COMPLETE_ASSIGNMENT: {"source"},
    Kind.COMPLETE_EXTERNAL_SCOPE: {"source"},
    Kind.COMPLETE_REQUIRES: {"include_type_checking"},
    Kind.EXTERNAL_DEPENDENCY_SCOPE: {"dependency", "allowed_sources", "exact_sources"},
    Kind.FORBIDDEN_CONSTRUCT: {
        "source",
        "constructs",
        "allowed_sources",
        "exact_sources",
        "allowed_type_ignores",
        "selector",
    },
    Kind.LAYER_ORDER: {"layers", "components"},
    Kind.NO_COMPONENT_CYCLES: {"level", "components"},
    Kind.ROOT_LAYOUT: {"root", "allowed_children"},
}


def _classes() -> dict[Kind, type]:
    found = {}
    for cls in typing.get_args(ArchitectureRule):
        kind = typing.get_args(typing.get_type_hints(cls)["kind"])[0]
        found[Kind(kind)] = cls
    return found


def _fields(cls: type) -> set[str]:
    return {field.name for field in dataclasses.fields(cls)} - INFRASTRUCTURE


def test_every_rule_kind_is_unsupported_checked_or_reviewed_as_reading_no_inside_edge() -> None:
    classes = _classes()
    assert set(classes) == set(Kind), "a rule kind has no class"
    for kind in Kind:
        covered = kind.value in RUST.unsupported_rules or kind in EDGE_FIELDS
        assert covered or kind in NO_INTERNAL_EDGES, f"{kind}: decide how the Rust scope reads it"
    assert not set(EDGE_FIELDS) & NO_INTERNAL_EDGES


def test_every_field_of_a_decided_rule_kind_is_reviewed() -> None:
    classes = _classes()
    decided = {kind for kind in Kind if kind.value not in RUST.unsupported_rules}
    assert decided == set(REVIEWED)
    for kind in decided:
        assert _fields(classes[kind]) == REVIEWED[kind], f"{kind}: a field is new or gone"
        assert set(EDGE_FIELDS.get(kind, ())) <= REVIEWED[kind]


def _rule(kind: Kind, **values: Any) -> Any:
    common = {"id": "R", "kind": kind, "rationale": "x", "provenance": ("p",)}
    common["decided_by"] = DecisionMaker.ARCHITECT
    if kind is Kind.FORBIDDEN_DEPENDENCY:
        defaults = {"source": "ns.a", "target": "ns.b", "include_type_checking": True}
        return ForbiddenDependencyRule(**common, **{**defaults, **values})
    if kind is Kind.ALLOWED_DEPENDENCY:
        return AllowedDependencyRule(**common, **{"source": "ns.a", "target": "ns.b", **values})
    return SiblingIsolationRule(**common, **{"members": ("ns.a", "ns.b"), **values})


def _flagged(rule: Any) -> list[tuple[str, str]]:
    return _rule_scopes(SimpleNamespace(rules=(rule,)), 1)  # type: ignore[arg-type]


CASES = [
    (Kind.FORBIDDEN_DEPENDENCY, "source", "ns.crate.m"),
    (Kind.FORBIDDEN_DEPENDENCY, "target", "ns.crate.m"),
    (Kind.FORBIDDEN_DEPENDENCY, "allowed_sources", ("ns.crate.m",)),
    (Kind.ALLOWED_DEPENDENCY, "source", "ns.crate.m"),
    (Kind.ALLOWED_DEPENDENCY, "target", "ns.crate.m"),
    (Kind.SIBLING_ISOLATION, "members", ("ns.one.a", "ns.two")),
    (Kind.SIBLING_ISOLATION, "members", ("ns.one", "ns.two.b")),
]


@pytest.mark.parametrize(("kind", "field", "value"), CASES)
def test_each_module_field_below_a_crate_root_is_a_scope_that_needs_inside_edges(
    kind: Kind, field: str, value: object
) -> None:
    rule = _rule(kind, **{field: value})
    assert [identity for identity, _ in _flagged(rule)] == ["R"]


def test_names_at_or_above_the_crate_root_are_not_flagged_unless_they_cover_the_same_crate() -> (
    None
):
    assert _flagged(_rule(Kind.SIBLING_ISOLATION, members=("ns.one", "ns.two"))) == []
    assert _flagged(_rule(Kind.FORBIDDEN_DEPENDENCY, source="ns.one", target="ns.two")) == []
    covering = _flagged(_rule(Kind.FORBIDDEN_DEPENDENCY, source="ns", target="ns.one"))
    assert [what for _, what in covering] == [
        "rule forbidden_dependency that covers the modules of a crate"
    ]


def test_a_profile_must_declare_whether_it_reads_only_crate_edges() -> None:
    from archkeel.ir.profiles import Profile

    field = next(f for f in dataclasses.fields(Profile) if f.name == "crate_edges_only")
    # No default: a new profile that forgets the field fails at its construction.
    assert field.default is dataclasses.MISSING and field.kw_only
    assert RUST.crate_edges_only
