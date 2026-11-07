# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Characterization of the duplicated identity and membership logic in the IR (#880, step S2).

Each test calls one copy through its module with the same shared cases and records what it
returns today. A test names the copy and the case. Step S2 of #880 may merge the copies
only if these tests stay true or an AD changes them.
"""

from dataclasses import replace
from typing import Any

import pytest
from test_delta import _evidence, _model
from test_levels import _declaration
from test_module_explore import _sample

from archkeel.check.evaluation.rules import (
    _inside_ownership_blockers,
    _inside_rule_scope_is_complete,
)
from archkeel.check.validation.observation import _inside_pointers
from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    ComponentIntent,
    ComponentRole,
    Entity,
    EntityKind,
    OriginKind,
)
from archkeel.ir.codec import parse_observation
from archkeel.ir.interfaces import component_owners, owner_of
from archkeel.ir.levels import inside_levels
from archkeel.ir.model import (
    ArchitectureContract,
    CompleteRequiresRule,
    ContractComponent,
    Observation,
)
from archkeel.ir.module_explore import _scope_owners as explore_scope_owners
from archkeel.ir.module_explore import module_exploration
from archkeel.ir.profiles import profile_for
from archkeel.ir.report_graph import _memberships
from archkeel.ir.report_projection import _deepest_owners, _scope_names
from archkeel.ir.report_projection import _scope_owners as projection_scope_owners
from archkeel.ir.source_graph import observed_graph
from archkeel.ir.view_spec import _view_graph

_ANALYZER = "archkeel-python-analyzer"

# D2 shared cases: component -> (packages, exact modules). The set has an overlap and an exact
# module. `shared` lies inside `core`, so a module under `sample.core.shared` has two owners.
OWNERSHIP: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "core": (("sample.core",), ()),
    "shared": (("sample.core.shared",), ()),
    "exact": ((), ("sample.exact",)),
    "peer": (("sample.peer",), ()),
}

# module -> who claims it (sorted). One claimant is an owner. Two or none give no owner.
CLAIMS: dict[str, tuple[str, ...]] = {
    "sample.core.a": ("core",),
    "sample.core.shared.x": ("core", "shared"),
    "sample.exact": ("exact",),
    "sample.exact.child": (),
    "sample.nowhere": (),
    "sample.peer.p": ("peer",),
}


def _unique(claims: tuple[str, ...]) -> str | None:
    return claims[0] if len(claims) == 1 else None


UNIQUE_OWNER = {module: _unique(claims) for module, claims in CLAIMS.items()}


def _ownership_declarations() -> list[dict[str, Any]]:
    return [
        _declaration(
            f"COMP-{label}",
            "component_responsibility",
            label,
            list(packages),
            exact_modules=list(exact),
        )
        for label, (packages, exact) in OWNERSHIP.items()
    ]


def _module_records(names: list[str]) -> list[dict[str, Any]]:
    records = [
        _declaration(
            f"MOD-{name}",
            "module",
            name,
            [],
            qualified_name=name,
            file=name.replace(".", "/") + ".py",
        )
        for name in names
    ]
    for record in records:
        record["evidence_ids"] = [record["id"].replace("MOD-", "EVD-")]
    return records


def _ownership_model(
    declarations: list[dict[str, Any]] | None = None, modules: list[str] | None = None
) -> Observation:
    names = list(CLAIMS) if modules is None else modules
    return parse_observation(
        _model(
            git_head="a" * 40,
            declarations=declarations if declarations is not None else _ownership_declarations(),
            modules=_module_records(names),
            evidence=[_evidence(f"EVD-{name}", 1) for name in names],
        )
    )


def _components(model: Observation | None = None):
    return component_owners(model or _ownership_model())


def _contract() -> ArchitectureContract:
    return ArchitectureContract(
        "2.1.0",
        tuple(
            ContractComponent(
                label, label, ComponentRole.COMPONENT, packages, (), (), (), exact_modules=exact
            )
            for label, (packages, exact) in OWNERSHIP.items()
        ),
        (),
    )


def _intent(identity: str, label: str | None, parent: str | None = None, **owned: Any):
    return ComponentIntent(
        identity, ComponentRole.COMPONENT, label=label, parent_id=parent, **owned
    )


def _target(*intents: ComponentIntent) -> ArchitectureGraph:
    entities = tuple(
        Entity(item.component_id, EntityKind.COMPONENT, f"qualified.{item.component_id}", "python")
        for item in intents
    )
    return ArchitectureGraph(OriginKind.DECLARED, entities, component_intents=intents)


def _ownership_target() -> ArchitectureGraph:
    return _target(
        *(
            _intent(label, label, packages=packages, exact_modules=exact)
            for label, (packages, exact) in OWNERSHIP.items()
        )
    )


# D1 shared cases: a root, a labelled child, a child without a label, a root without a label,
# and a grandchild. The label None case is reachable only from a constructed graph, because the
# Target reader always writes the record title as the label.
def _label_target(root_name: str = "qualified.COMP-LOOSE") -> ArchitectureGraph:
    intents = (
        _intent("COMP-CORE", "core", packages=("sample.core",)),
        _intent("COMP-A", "a", "COMP-CORE", packages=("sample.core.a",)),
        _intent("COMP-X", None, "COMP-CORE", packages=("sample.core.x",)),
        _intent("COMP-LOOSE", None, packages=("sample.loose",)),
        _intent("COMP-DEEP", "deep", "COMP-A", packages=("sample.core.a.deep",)),
    )
    graph = _target(*intents)
    entities = tuple(
        replace(item, qualified_name=root_name) if item.id == "COMP-LOOSE" else item
        for item in graph.entities
    )
    return replace(graph, entities=entities)


def _inside_declarations() -> list[dict[str, Any]]:
    return [
        _declaration("COMP-CORE", "component_responsibility", "core", ["sample.core"]),
        _declaration(
            "core:COMP-A",
            "inside_component_responsibility",
            "a",
            ["sample.core.a"],
            parent_id="core",
            inside="a-inside.json",
        ),
        _declaration(
            "core:COMP-X",
            "inside_component_responsibility",
            "x",
            ["sample.core.x"],
            parent_id="core",
        ),
        _declaration(
            "core:a:COMP-DEEP",
            "inside_component_responsibility",
            "deep",
            ["sample.core.a.deep"],
            parent_id="core:a",
        ),
    ]


def _inside_model() -> Observation:
    return _ownership_model(
        _inside_declarations(),
        ["sample.core.a.m", "sample.core.a.deep.m", "sample.core.x.m", "sample.core.c"],
    )


# ---------------------------------------------------------------------------------------------
# D1: the Target scope label "parent:label".
# ---------------------------------------------------------------------------------------------


def test_report_projection_scope_names_falls_back_to_component_id_for_a_missing_label() -> None:
    """Characterization: records current behaviour of report_projection._scope_names.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it."""
    assert _scope_names(_label_target()) == {
        "COMP-CORE": "core",
        "COMP-A": "core:a",
        "COMP-X": "core:COMP-X",
        "COMP-LOOSE": "COMP-LOOSE",
        "COMP-DEEP": "core:a:deep",
    }


def test_module_explore_scope_owners_falls_back_to_component_id_for_a_missing_label() -> None:
    """Characterization: records current behaviour of module_explore._scope_owners.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it."""
    target = _label_target()
    scope_ids, owners = explore_scope_owners(
        _inside_model(), {item.component_id: item for item in target.component_intents}
    )
    assert scope_ids == {
        "core": "COMP-CORE",
        "core:a": "COMP-A",
        "core:COMP-X": "COMP-X",
        "COMP-LOOSE": "COMP-LOOSE",
        "core:a:deep": "COMP-DEEP",
    }
    assert owners[None] == (("core", ("sample.core",), ()),)
    assert owners["COMP-CORE"] == (
        ("core:a", ("sample.core.a",), ()),
        ("core:x", ("sample.core.x",), ()),
    )
    assert owners["COMP-A"] == (("core:a:deep", ("sample.core.a.deep",), ()),)


def test_module_explore_scope_owners_raises_for_an_inside_level_without_an_intent() -> None:
    """Characterization: records current behaviour of module_explore._scope_owners.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it."""
    declarations = [
        *_inside_declarations(),
        _declaration(
            "ghost:COMP-G", "inside_component_responsibility", "g", ["sample.g"], parent_id="ghost"
        ),
    ]
    target = _label_target()
    with pytest.raises(KeyError):
        explore_scope_owners(
            _ownership_model(declarations, []),
            {item.component_id: item for item in target.component_intents},
        )


def _memberships_by_id(model: Observation, target: ArchitectureGraph) -> dict[str, tuple[str, ...]]:
    result = _memberships(model, observed_graph(model), target)
    names = {item.id: item.qualified_name for item in observed_graph(model).entities}
    return {item.component_id: tuple(names[x] for x in item.module_ids) for item in result}


def test_report_graph_memberships_scope_key_uses_the_label_and_the_nested_parent() -> None:
    """Characterization: records current behaviour of report_graph._memberships.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it."""
    members = _memberships_by_id(_inside_model(), _label_target())
    assert set(members["COMP-CORE"]) == {
        "sample.core.a.deep.m",
        "sample.core.a.m",
        "sample.core.c",
        "sample.core.x.m",
    }
    assert set(members["COMP-A"]) == {"sample.core.a.m", "sample.core.a.deep.m"}
    assert set(members["COMP-DEEP"]) == {"sample.core.a.deep.m"}
    assert members["COMP-X"] == ()


def test_report_graph_memberships_falls_back_to_the_entity_name_for_a_missing_label() -> None:
    """Characterization: records current behaviour of report_graph._memberships.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it.

    The other copies fall back to the component id here. The component record is titled with
    the entity name, so only the entity name finds its owner."""
    declarations = [
        _declaration("COMP-LOOSE", "component_responsibility", "qualified.loose", ["sample.loose"])
    ]
    model = _ownership_model(declarations, ["sample.loose.m"])
    named = _memberships_by_id(model, _label_target("qualified.loose"))
    by_id = _memberships_by_id(model, _label_target("COMP-LOOSE"))
    assert named["COMP-LOOSE"] == ("sample.loose.m",)
    assert by_id["COMP-LOOSE"] == ()


def test_levels_inside_levels_keys_a_nested_scope_by_parent_and_title() -> None:
    """Characterization: records current behaviour of levels.inside_levels.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it."""
    levels = {item.parent: item for item in inside_levels(_inside_model())}
    assert set(levels) == {"core", "core:a"}
    deep = levels["core:a"]
    assert [(item.label, item.packages, item.modules) for item in deep.components] == [
        ("deep", ("sample.core.a.deep",), ("sample.core.a.deep.m",))
    ]
    assert deep.unassigned == ("sample.core.a.m",)


def test_observation_diagnostics_inside_pointers_walks_the_parent_title_chain() -> None:
    """Characterization: records current behaviour of observation._inside_pointers.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it."""
    contract = ArchitectureContract(
        "2.1.0",
        (
            ContractComponent("p", "peer", ComponentRole.COMPONENT, ("sample.peer",), (), (), ()),
            ContractComponent(
                "c", "core", ComponentRole.COMPONENT, ("sample.core",), (), (), (), inside="i.json"
            ),
        ),
        (),
    )
    pointers = _inside_pointers(contract, _inside_model())
    assert pointers == {
        "core:COMP-A": "/components/1/inside",
        "core:COMP-X": "/components/1/inside",
        "core:a:COMP-DEEP": "/components/1/inside",
    }


# ---------------------------------------------------------------------------------------------
# D2: the one owner of a module, and the membership of a level.
# ---------------------------------------------------------------------------------------------


def test_interfaces_owner_of_returns_none_for_zero_or_many_owners() -> None:
    """Characterization: records current behaviour of interfaces.owner_of.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it."""
    components = _components()
    assert {name: owner_of(name, components) for name in CLAIMS} == UNIQUE_OWNER


def test_model_component_for_returns_none_for_zero_or_many_owners() -> None:
    """Characterization: records current behaviour of ArchitectureContract.component_for.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it."""
    contract = _contract()
    found = {name: contract.component_for(name) for name in CLAIMS}
    assert {name: item.label if item else None for name, item in found.items()} == UNIQUE_OWNER


def test_report_projection_deepest_owners_returns_every_claimant_for_zero_or_many() -> None:
    """Characterization: records current behaviour of report_projection._deepest_owners.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it.

    Unlike the other copies it returns the claimants, so the caller decides."""
    target = _ownership_target()
    assert {name: _deepest_owners(target, name) for name in CLAIMS} == CLAIMS


def test_report_projection_deepest_owners_descends_one_unique_owner_per_level() -> None:
    """Characterization: records current behaviour of report_projection._deepest_owners.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it."""
    target = _label_target()
    assert _deepest_owners(target, "sample.core.a.deep.m") == ("COMP-DEEP",)
    assert _deepest_owners(target, "sample.core.a.m") == ("COMP-A",)
    assert _deepest_owners(target, "sample.core.c") == ("COMP-CORE",)
    assert _deepest_owners(target, "sample.nowhere") == ()


def test_report_projection_scope_owners_is_empty_below_an_ambiguous_parent() -> None:
    """Characterization: records current behaviour of report_projection._scope_owners.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it."""
    both = _target(
        _intent("one", "one", packages=("sample.core",)),
        _intent("two", "two", packages=("sample.core",)),
        _intent("child", "child", "one", packages=("sample.core.a",)),
    )
    assert projection_scope_owners(both, "sample.core.a", None) == ("one", "two")
    assert projection_scope_owners(both, "sample.core.a", "one") == ()
    assert _deepest_owners(both, "sample.core.a") == ("one", "two")


def _blocker_owners(modules: list[tuple[str, str]], profile_name: str = _ANALYZER):
    records = [
        {"id": f"M-{name}", "evidence_ids": [], "data": {"qualified_name": name, "file": file}}
        for name, file in modules
    ]
    rule = CompleteRequiresRule("RULE", "complete_requires", "why", (), "architect")
    blank = frozenset(name for name, file in modules if file.endswith("__init__.py"))
    result = _inside_ownership_blockers(
        rule, "scope", _contract(), records, profile_for(profile_name), blank
    )
    return {item["data"]["module"]: tuple(item["data"]["owners"]) for item in result}


def test_rules_inside_ownership_blockers_blocks_zero_and_many_owners_only() -> None:
    """Characterization: records current behaviour of rules._inside_ownership_blockers.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it."""
    modules = [(name, name.replace(".", "/") + ".py") for name in CLAIMS]
    assert _blocker_owners(modules) == {
        name: claims for name, claims in CLAIMS.items() if len(claims) != 1
    }


def test_rules_inside_ownership_blockers_skips_an_unowned_blank_python_initializer() -> None:
    """Characterization: records current behaviour of rules._inside_ownership_blockers.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it.

    No other copy has this exception."""
    modules = [
        ("sample.nowhere", "sample/nowhere/__init__.py"),
        ("sample.other", "sample/other.py"),
    ]
    assert _blocker_owners(modules) == {"sample.other": ()}
    assert set(_blocker_owners(modules, "archkeel-typescript-imports")) == {
        "sample.nowhere",
        "sample.other",
    }


def _scope_complete(modules: list[tuple[str, str]], profile_name: str = _ANALYZER) -> bool:
    records = [
        {"id": f"M-{name}", "evidence_ids": [], "data": {"qualified_name": name, "file": file}}
        for name, file in [("sample.peer.p", "sample/peer/p.py"), *modules]
    ]
    blank = frozenset(name for name, file in modules if file.endswith("__init__.py"))
    return _inside_rule_scope_is_complete(
        _contract(), records, profile_for(profile_name), blank, True
    )


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        ("sample.core.a", True),
        ("sample.core.shared.x", False),
        ("sample.exact", True),
        ("sample.exact.child", False),
        ("sample.nowhere", False),
    ],
)
def test_rules_inside_rule_scope_is_complete_needs_exactly_one_owner_for_each_module(
    module: str, expected: bool
) -> None:
    """Characterization: records current behaviour of rules._inside_rule_scope_is_complete.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it."""
    assert _scope_complete([(module, module.replace(".", "/") + ".py")]) is expected


def test_rules_inside_rule_scope_is_complete_accepts_an_unowned_blank_python_initializer() -> None:
    """Characterization: records current behaviour of rules._inside_rule_scope_is_complete.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it."""
    modules = [("sample.nowhere", "sample/nowhere/__init__.py")]
    assert _scope_complete(modules) is True
    assert _scope_complete(modules, "archkeel-typescript-imports") is False


def test_report_graph_memberships_assigns_only_unique_owners_at_the_root() -> None:
    """Characterization: records current behaviour of report_graph._memberships.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it."""
    model = _ownership_model()
    members = _memberships_by_id(model, _ownership_target())
    assert {label: set(names) for label, names in members.items()} == {
        "core": {"sample.core.a"},
        "shared": set(),
        "exact": {"sample.exact"},
        "peer": {"sample.peer.p"},
    }


def test_report_graph_memberships_gives_two_inside_claimants_no_module() -> None:
    """Characterization: records current behaviour of report_graph._memberships.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it.

    The inside level adds a module only to its one owner, as owner_of does. The parent keeps
    the module."""
    declarations = [
        _declaration("COMP-CORE", "component_responsibility", "core", ["sample.core"]),
        *(
            _declaration(
                f"core:COMP-{label}",
                "inside_component_responsibility",
                label,
                ["sample.core.a"],
                parent_id="core",
            )
            for label in ("one", "two")
        ),
    ]
    target = _target(
        _intent("COMP-CORE", "core", packages=("sample.core",)),
        _intent("COMP-one", "one", "COMP-CORE", packages=("sample.core.a",)),
        _intent("COMP-two", "two", "COMP-CORE", packages=("sample.core.a",)),
    )
    members = _memberships_by_id(_ownership_model(declarations, ["sample.core.a.m"]), target)
    assert members == {
        "COMP-CORE": ("sample.core.a.m",),
        "COMP-one": (),
        "COMP-two": (),
    }


def test_levels_inside_levels_leaves_overlapping_and_unclaimed_modules_unassigned() -> None:
    """Characterization: records current behaviour of levels.inside_levels.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it."""
    declarations = [
        _declaration("COMP-CORE", "component_responsibility", "core", ["sample.core"]),
        *(
            _declaration(
                f"core:COMP-{label}",
                "inside_component_responsibility",
                label,
                [package],
                parent_id="core",
            )
            for label, package in (
                ("a", "sample.core.a"),
                ("b", "sample.core.b"),
                ("ab", "sample.core.a"),
            )
        ),
    ]
    modules = ["sample.core.a.m", "sample.core.b.m", "sample.core.c", "sample.peer.p"]
    (level,) = inside_levels(_ownership_model(declarations, modules))
    assert {item.label: item.modules for item in level.components} == {
        "a": (),
        "ab": (),
        "b": ("sample.core.b.m",),
    }
    assert level.unassigned == ("sample.core.a.m", "sample.core.c")


def test_module_explore_scope_owners_hands_the_root_claims_on_without_choosing() -> None:
    """Characterization: records current behaviour of module_explore._scope_owners.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it.

    The root level keeps every claim. A later owner_of call picks the one owner."""
    intents = {item.component_id: item for item in _ownership_target().component_intents}
    model = _ownership_model()
    _, owners = explore_scope_owners(model, intents)
    assert owners == {None: _components(model)}
    assert {name: owner_of(name, owners[None]) for name in CLAIMS} == UNIQUE_OWNER


def test_view_spec_view_graph_members_lists_only_unique_root_owners() -> None:
    """Characterization: records current behaviour of view_spec._view_graph.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it."""
    graph = _view_graph(_ownership_model(), story=False)
    assert {identity: set(names) for identity, names in graph.members.items()} == {
        "COMP-core": {"sample.core.a"},
        "COMP-shared": set(),
        "COMP-exact": {"sample.exact"},
        "COMP-peer": {"sample.peer.p"},
    }


@pytest.fixture(scope="module")
def ambiguous_sample(tmp_path_factory: pytest.TempPathFactory) -> Observation:
    return _sample(tmp_path_factory.mktemp("ambiguous"), ambiguous=True)


def test_module_explore_statistics_keep_an_overlapping_module_as_candidates_not_owner(
    ambiguous_sample: Observation,
) -> None:
    """Characterization: records current behaviour of module_explore.module_exploration.
    Step S2 of #880 may merge the copies only if this stays true or an AD changes it."""
    level = next(item for item in module_exploration(ambiguous_sample) if item.parent_id is None)
    found = {item.name: (item.component_id, item.candidate_ids) for item in level.modules}
    assert found["sample.core"] == (None, ("core", "overlap"))
    assert found["sample.peer"] == ("peer", ("peer",))
    assert found["sample.unowned"] == (None, ())
