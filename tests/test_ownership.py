# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The one owner of the scope label and of module membership (#880 step S2, AD-321)."""

import re
from pathlib import Path

import pytest
from test_architecture_owner_characterization import (
    _intent,
    _label_target,
    _memberships_by_id,
    _ownership_model,
    _target,
)
from test_levels import _declaration

from archkeel.ir.ownership import (
    containing,
    deepest_owners,
    owner_of,
    partition,
    scope_key,
    scope_names,
    sole,
)

_IR = Path(__file__).resolve().parents[1] / "src" / "archkeel" / "ir"


def test_scope_key_joins_a_parent_key_and_a_label_with_a_colon() -> None:
    assert scope_key(None, "core") == "core"
    assert scope_key("core", "a") == "core:a"
    assert scope_key("core:a", "deep") == "core:a:deep"


def test_scope_names_orders_the_chain_from_the_root_down() -> None:
    names = scope_names(reversed(_label_target().component_intents))
    assert names["COMP-DEEP"] == "core:a:deep"
    assert names["COMP-LOOSE"] == "COMP-LOOSE"


def test_sole_returns_the_one_claimant_and_nothing_for_zero_or_many() -> None:
    assert sole(()) is None
    assert sole(("a",)) == "a"
    assert sole(("a", "b")) is None


def test_owner_of_needs_exactly_one_claimant_for_a_package_or_an_exact_module() -> None:
    components = (
        ("outer", ("pkg",), ()),
        ("exact", (), ("pkg.one",)),
        ("other", ("elsewhere",), ()),
    )
    assert owner_of("pkg.one", components) is None
    assert owner_of("pkg.two", components) == "outer"
    assert owner_of("pkg", components) == "outer"
    assert owner_of("pkgx", components) is None
    assert owner_of("elsewhere.x", components) == "other"


def test_partition_groups_names_by_their_one_owner_and_keeps_the_rest_unowned() -> None:
    components = (
        ("a", ("pkg.a",), ()),
        ("b", ("pkg.b",), ()),
        ("both", ("pkg.a.x",), ()),
    )
    names = ["pkg.b.m", "pkg.a.m", "pkg.a.x.m", "pkg.c", "pkg.b"]
    owned, unowned = partition(names, components)
    assert owned == {"b": ("pkg.b.m", "pkg.b"), "a": ("pkg.a.m",)}
    assert unowned == ("pkg.a.x.m", "pkg.c")
    assert partition([], components) == ({}, ())


def test_containing_lists_every_component_from_the_root_to_the_deepest_owner() -> None:
    intents = _label_target().component_intents
    assert containing(intents, "sample.core.a.deep.m") == ("COMP-CORE", "COMP-A", "COMP-DEEP")
    assert containing(intents, "sample.core.c") == ("COMP-CORE",)
    assert containing(intents, "sample.nowhere") == ()


def test_containing_stops_at_the_parent_when_two_children_claim_the_module() -> None:
    both = _target(
        _intent("core", "core", packages=("sample.core",)),
        _intent("one", "one", "core", packages=("sample.core.a",)),
        _intent("two", "two", "core", packages=("sample.core.a",)),
    ).component_intents
    assert containing(both, "sample.core.a.m") == ("core",)
    assert deepest_owners(both, "sample.core.a.m") == ("one", "two")


def test_containing_gives_a_child_nothing_when_its_parent_is_ambiguous() -> None:
    """AD-321: overlapping ownership owns nothing, and a child cannot own what its parent lacks.

    The old report_graph copy handed `sample.core.a.m` to `child` although neither `one` nor
    `two` owned it, so a member of the child was no member of its parent."""
    intents = _target(
        _intent("one", "one", packages=("sample.core",)),
        _intent("two", "two", packages=("sample.core",)),
        _intent("child", "child", "one", packages=("sample.core.a",)),
    ).component_intents
    assert containing(intents, "sample.core.a.m") == ()
    assert deepest_owners(intents, "sample.core.a.m") == ("one", "two")


def test_report_graph_memberships_give_a_child_nothing_below_an_ambiguous_parent() -> None:
    declarations = [
        _declaration("one", "component_responsibility", "one", ["sample.core"]),
        _declaration("two", "component_responsibility", "two", ["sample.core"]),
        _declaration(
            "one:child",
            "inside_component_responsibility",
            "child",
            ["sample.core.a"],
            parent_id="one",
        ),
    ]
    target = _target(
        _intent("one", "one", packages=("sample.core",)),
        _intent("two", "two", packages=("sample.core",)),
        _intent("child", "child", "one", packages=("sample.core.a",)),
    )
    members = _memberships_by_id(_ownership_model(declarations, ["sample.core.a.m"]), target)
    assert members == {"child": (), "one": (), "two": ()}


@pytest.mark.parametrize(
    ("file", "names"),
    [
        ("report_projection.py", ("_scope_names", "_scope_owners", "_deepest_owners")),
        ("module_explore.py", ("_scope_owners",)),
        ("interfaces.py", ("owner_of",)),
    ],
)
def test_the_copies_of_the_scope_label_and_the_membership_are_gone(
    file: str, names: tuple[str, ...]
) -> None:
    """Only `ownership` defines these names. Another definition is a second copy."""
    text = (_IR / file).read_text(encoding="utf-8")
    for name in names:
        assert re.search(rf"^def {name}\b", text, re.MULTILINE) is None, f"{file} defines {name}"


def test_no_module_writes_the_scope_label_fallback_again() -> None:
    """`intent.label or ...` is the label fallback. It lives in `ownership` and in no other file."""
    found = [
        path.name
        for path in sorted(_IR.glob("*.py"))
        if path.name != "ownership.py"
        and re.search(r"intent\.label or\b.*\bidentity\b", path.read_text(encoding="utf-8"))
    ]
    assert found == []
