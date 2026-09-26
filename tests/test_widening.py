# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-61 (#11): contract-widening classification, its amendment record, and --against."""

from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from test_architecture_demo import CONFIG as SHOP_CONFIG
from test_architecture_demo import _prepare_repo

from archkeel.analyzer import observe
from archkeel.check.validation import run_validate
from archkeel.ir.baseline import KnownViolation, ViolationFingerprint
from archkeel.ir.codec import amendment_bytes, baseline_bytes, contract_digest, parse_amendment
from archkeel.ir.model import (
    RULE_KINDS,
    AllowedDependencyRule,
    ArchitectureContract,
    ArchitectureRule,
    BoundaryTypeAllowance,
    BoundaryTypesRule,
    CompleteAssignmentRule,
    CompleteExternalScopeRule,
    CompleteRequiresRule,
    ComponentRole,
    ContractComponent,
    ExternalDependencyScopeRule,
    ForbiddenConstructRule,
    ForbiddenDependencyRule,
    InterfaceBoundaryRule,
    NoComponentCyclesRule,
    RequiredComponent,
    RootLayoutRule,
    SiblingIsolationRule,
    SymbolPlacementRule,
)
from archkeel.ir.widening import (
    _PERMISSION_RULE_KINDS,
    _RESTRICTION_RULE_KINDS,
    Amendment,
    baseline_widenings,
    contract_widenings,
    verify_amendment,
)
from fixtures.demo_catalog_support import FIXTURE_DIR, apply_overlay, contract_rule_field

_PROVENANCE = ("docs/architecture/shop.md",)


def _forbidden_dependency(**overrides: object) -> ForbiddenDependencyRule:
    base = ForbiddenDependencyRule(
        "R", "forbidden_dependency", "pkg.a", "pkg.b", True, "because", _PROVENANCE, "architect"
    )
    return replace(base, **overrides)


def _allowed_dependency(**overrides: object) -> AllowedDependencyRule:
    base = AllowedDependencyRule(
        "R", "allowed_dependency", "pkg.a", "pkg.b", "because", _PROVENANCE, "architect"
    )
    return replace(base, **overrides)


def _forbidden_construct(**overrides: object) -> ForbiddenConstructRule:
    base = ForbiddenConstructRule(
        "R", "forbidden_construct", "pkg.a", ("eval",), "because", _PROVENANCE, "architect"
    )
    return replace(base, **overrides)


def _external_dependency_scope(**overrides: object) -> ExternalDependencyScopeRule:
    base = ExternalDependencyScopeRule(
        "R",
        "external_dependency_scope",
        "requests",
        ("pkg.a",),
        "because",
        _PROVENANCE,
        "architect",
    )
    return replace(base, **overrides)


def _complete_requires(**overrides: object) -> CompleteRequiresRule:
    base = CompleteRequiresRule("R", "complete_requires", "because", _PROVENANCE, "architect")
    return replace(base, **overrides)


def _interface_boundary(**overrides: object) -> InterfaceBoundaryRule:
    base = InterfaceBoundaryRule("R", "interface_boundary", "because", _PROVENANCE, "architect")
    return replace(base, **overrides)


def _sibling_isolation(**overrides: object) -> SiblingIsolationRule:
    base = SiblingIsolationRule(
        "R", "sibling_isolation", ("pkg.a", "pkg.b"), "because", _PROVENANCE, "architect"
    )
    return replace(base, **overrides)


def _complete_assignment(**overrides: object) -> CompleteAssignmentRule:
    base = CompleteAssignmentRule(
        "R", "complete_assignment", "pkg.a", "because", _PROVENANCE, "architect"
    )
    return replace(base, **overrides)


def _root_layout(**overrides: object) -> RootLayoutRule:
    base = RootLayoutRule(
        "R", "root_layout", "pkg", ("pkg.a", "pkg.b"), "because", _PROVENANCE, "architect"
    )
    return replace(base, **overrides)


def _complete_external_scope(**overrides: object) -> CompleteExternalScopeRule:
    base = CompleteExternalScopeRule(
        "R", "complete_external_scope", "pkg.a", "because", _PROVENANCE, "architect"
    )
    return replace(base, **overrides)


def _no_component_cycles(**overrides: object) -> NoComponentCyclesRule:
    base = NoComponentCyclesRule("R", "no_component_cycles", "because", _PROVENANCE, "architect")
    return replace(base, **overrides)


def _symbol_placement(**overrides: object) -> SymbolPlacementRule:
    base = SymbolPlacementRule(
        "R", "symbol_placement", "pkg", ("class",), "because", _PROVENANCE, "architect"
    )
    return replace(base, **overrides)


def _boundary_types(**overrides: object) -> BoundaryTypesRule:
    base = BoundaryTypesRule("R", "boundary_types", "pkg", "because", _PROVENANCE, "architect")
    return replace(base, **overrides)


def _component(**overrides: object) -> ContractComponent:
    base = ContractComponent("C", "comp", ComponentRole.COMPONENT, ("pkg",), (), (), _PROVENANCE)
    return replace(base, **overrides)


def _contract(
    components: tuple[ContractComponent, ...] = (), rules: tuple[ArchitectureRule, ...] = ()
) -> ArchitectureContract:
    return ArchitectureContract("2.1.0", components, rules)


def _rule_diff(before: ArchitectureRule | None, after: ArchitectureRule | None) -> tuple[str, ...]:
    return contract_widenings(
        _contract(rules=() if before is None else (before,)),
        _contract(rules=() if after is None else (after,)),
    )


def test_boundary_allowance_addition_widens_and_removal_narrows() -> None:
    allowance = BoundaryTypeAllowance("pkg.api.run", "return", "payload", "dict[str, JsonValue]")

    added = _rule_diff(_boundary_types(), _boundary_types(allowed_positions=(allowance,)))
    assert len(added) == 1
    assert "allowed_positions gained" in added[0]
    assert "dict[str, JsonValue]" in added[0]
    assert _rule_diff(_boundary_types(allowed_positions=(allowance,)), _boundary_types()) == ()


def _component_diff(
    before: ContractComponent | None, after: ContractComponent | None
) -> tuple[str, ...]:
    return contract_widenings(
        _contract(components=() if before is None else (before,)),
        _contract(components=() if after is None else (after,)),
    )


# --- Table-driven: one row per rule-kind widening/narrowing this module enumerates (#11). ---
_RULE_CASES: tuple[tuple[str, ArchitectureRule | None, ArchitectureRule | None, bool], ...] = (
    ("forbidden_dependency added", None, _forbidden_dependency(), False),
    ("forbidden_dependency removed", _forbidden_dependency(), None, True),
    (
        "forbidden_dependency.allowed_sources gained",
        _forbidden_dependency(),
        _forbidden_dependency(allowed_sources=("pkg.a.sub",)),
        True,
    ),
    (
        "forbidden_dependency.allowed_sources lost",
        _forbidden_dependency(allowed_sources=("pkg.a.sub",)),
        _forbidden_dependency(),
        False,
    ),
    (
        "forbidden_dependency.include_type_checking relaxed",
        _forbidden_dependency(include_type_checking=True),
        _forbidden_dependency(include_type_checking=False),
        True,
    ),
    (
        "forbidden_dependency.include_type_checking tightened",
        _forbidden_dependency(include_type_checking=False),
        _forbidden_dependency(include_type_checking=True),
        False,
    ),
    ("allowed_dependency added", None, _allowed_dependency(), True),
    ("allowed_dependency removed", _allowed_dependency(), None, False),
    ("forbidden_construct added", None, _forbidden_construct(), False),
    ("forbidden_construct removed", _forbidden_construct(), None, True),
    (
        "forbidden_construct.constructs lost an entry",
        _forbidden_construct(constructs=("eval", "exec")),
        _forbidden_construct(constructs=("eval",)),
        True,
    ),
    (
        "forbidden_construct.constructs gained an entry",
        _forbidden_construct(constructs=("eval",)),
        _forbidden_construct(constructs=("eval", "exec")),
        False,
    ),
    (
        "forbidden_construct.allowed_sources gained",
        _forbidden_construct(),
        _forbidden_construct(allowed_sources=("pkg.a.sub",)),
        True,
    ),
    (
        "forbidden_construct.exact_sources gained",
        _forbidden_construct(),
        _forbidden_construct(exact_sources=("pkg.a",)),
        True,
    ),
    ("external_dependency_scope added", None, _external_dependency_scope(), False),
    ("external_dependency_scope removed", _external_dependency_scope(), None, True),
    (
        "external_dependency_scope.allowed_sources gained",
        _external_dependency_scope(),
        _external_dependency_scope(allowed_sources=("pkg.a", "pkg.b")),
        True,
    ),
    (
        "external_dependency_scope.exact_sources gained",
        _external_dependency_scope(),
        _external_dependency_scope(exact_sources=("pkg.a",)),
        True,
    ),
    ("complete_requires added", None, _complete_requires(), False),
    ("complete_requires removed", _complete_requires(), None, True),
    (
        "complete_requires.include_type_checking relaxed",
        _complete_requires(include_type_checking=True),
        _complete_requires(include_type_checking=False),
        True,
    ),
    ("interface_boundary added", None, _interface_boundary(), False),
    ("interface_boundary removed", _interface_boundary(), None, True),
    (
        "interface_boundary.include_type_checking relaxed",
        _interface_boundary(include_type_checking=True),
        _interface_boundary(include_type_checking=False),
        True,
    ),
    ("sibling_isolation added", None, _sibling_isolation(), False),
    ("sibling_isolation removed", _sibling_isolation(), None, True),
    (
        "sibling_isolation.members lost a member",
        _sibling_isolation(members=("pkg.a", "pkg.b", "pkg.c")),
        _sibling_isolation(members=("pkg.a", "pkg.b")),
        True,
    ),
    (
        "sibling_isolation.members gained a member",
        _sibling_isolation(members=("pkg.a", "pkg.b")),
        _sibling_isolation(members=("pkg.a", "pkg.b", "pkg.c")),
        False,
    ),
    ("complete_assignment added", None, _complete_assignment(), False),
    ("complete_assignment removed", _complete_assignment(), None, True),
    ("root_layout added", None, _root_layout(), False),
    ("root_layout removed", _root_layout(), None, True),
    (
        "root_layout.allowed_children gained",
        _root_layout(),
        _root_layout(allowed_children=("pkg.a", "pkg.b", "pkg.c")),
        True,
    ),
    (
        "root_layout.allowed_children lost",
        _root_layout(allowed_children=("pkg.a", "pkg.b", "pkg.c")),
        _root_layout(),
        False,
    ),
    ("complete_external_scope added", None, _complete_external_scope(), False),
    ("complete_external_scope removed", _complete_external_scope(), None, True),
    ("no_component_cycles added", None, _no_component_cycles(), False),
    ("no_component_cycles removed", _no_component_cycles(), None, True),
    ("module-level cycle rule added", None, _no_component_cycles(level="module"), False),
    ("module-level cycle rule removed", _no_component_cycles(level="module"), None, True),
    # Neither level implies the other (AD-98), so a level change either way is a widening.
    (
        "cycle level component to module",
        _no_component_cycles(),
        _no_component_cycles(level="module"),
        True,
    ),
    (
        "cycle level module to component",
        _no_component_cycles(level="module"),
        _no_component_cycles(),
        True,
    ),
    (
        "cycle scope introduced",
        _no_component_cycles(),
        _no_component_cycles(components=("a",)),
        True,
    ),
    ("cycle scope removed", _no_component_cycles(components=("a",)), _no_component_cycles(), False),
    (
        "cycle scope lost a component",
        _no_component_cycles(components=("a", "b")),
        _no_component_cycles(components=("a",)),
        True,
    ),
    (
        "cycle scope gained a component",
        _no_component_cycles(components=("a",)),
        _no_component_cycles(components=("a", "b")),
        False,
    ),
    ("symbol_placement added", None, _symbol_placement(), False),
    ("symbol_placement removed", _symbol_placement(), None, True),
    ("boundary_types added", None, _boundary_types(), False),
    ("boundary_types removed", _boundary_types(), None, True),
)


@pytest.mark.parametrize(
    "label,before,after,widens", _RULE_CASES, ids=[case[0] for case in _RULE_CASES]
)
def test_rule_kind_widening_table(
    label: str, before: ArchitectureRule | None, after: ArchitectureRule | None, widens: bool
) -> None:
    findings = _rule_diff(before, after)
    assert bool(findings) == widens, (label, findings)


def test_every_typed_rule_kind_has_one_widening_classification() -> None:
    """The typed ArchitectureRule union is the source of truth for this partition."""
    assert _PERMISSION_RULE_KINDS.isdisjoint(_RESTRICTION_RULE_KINDS)
    assert _PERMISSION_RULE_KINDS | _RESTRICTION_RULE_KINDS == RULE_KINDS


# --- Table-driven: one row per component-field widening/narrowing this module enumerates. ---
_COMPONENT_CASES: tuple[
    tuple[str, ContractComponent | None, ContractComponent | None, bool], ...
] = (
    (
        "public gained an entry",
        _component(public=("pkg:A",)),
        _component(public=("pkg:A", "pkg:B")),
        True,
    ),
    (
        "public lost an entry",
        _component(public=("pkg:A", "pkg:B")),
        _component(public=("pkg:A",)),
        False,
    ),
    (
        "planned entry promoted to public",
        _component(planned=("pkg:A",)),
        _component(public=("pkg:A",)),
        False,
    ),
    (
        "planned entry removed",
        _component(planned=("pkg:A",)),
        _component(),
        True,
    ),
    (
        "public addition beside promotion",
        _component(planned=("pkg:A",)),
        _component(public=("pkg:A", "pkg:B")),
        True,
    ),
    (
        "requires gained an edge",
        _component(requires=()),
        _component(requires=(RequiredComponent("other", "because"),)),
        True,
    ),
    (
        "requires lost an edge",
        _component(requires=(RequiredComponent("other", "because"),)),
        _component(requires=()),
        False,
    ),
    ("component added", None, _component(), True),
    ("component removed", _component(), None, True),
    (
        "packages changed",
        _component(packages=("pkg",)),
        _component(packages=("pkg", "pkg.sub")),
        True,
    ),
    (
        "role changed",
        _component(role=ComponentRole.COMPONENT),
        _component(role=ComponentRole.INTERFACE),
        True,
    ),
    (
        "namespace added",
        _component(namespace=None),
        _component(namespace="pkg"),
        False,
    ),
    (
        "namespace removed",
        _component(namespace="pkg"),
        _component(namespace=None),
        True,
    ),
    (
        "namespace changed",
        _component(namespace="pkg"),
        _component(namespace="pkg.other"),
        True,
    ),
)


@pytest.mark.parametrize(
    "label,before,after,widens", _COMPONENT_CASES, ids=[case[0] for case in _COMPONENT_CASES]
)
def test_component_field_widening_table(
    label: str, before: ContractComponent | None, after: ContractComponent | None, widens: bool
) -> None:
    findings = _component_diff(before, after)
    assert bool(findings) == widens, (label, findings)


def test_rationale_and_provenance_are_neutral() -> None:
    before = _forbidden_dependency(rationale="one reason", provenance=("docs/a.md",))
    after = _forbidden_dependency(
        rationale="a different reason entirely", provenance=("docs/b.md",)
    )
    assert _rule_diff(before, after) == ()


def test_component_provenance_is_neutral() -> None:
    before = _component(provenance=("docs/a.md",))
    after = _component(provenance=("docs/b.md",))
    assert _component_diff(before, after) == ()


def test_a_public_gain_names_the_lost_entry_it_may_replace() -> None:
    """#151: where no rename is recognised, a gain still shows what the same change lost."""
    before = _component(packages=("a.api",), public=("a.api.generated.planning_api",))
    after = _component(packages=("b.api",), public=("b.api.generated.planning_api",))

    assert (
        "component 'comp'.public gained 'b.api.generated.planning_api' "
        "in place of 'a.api.generated.planning_api'"
    ) in _component_diff(before, after)


def test_a_public_gain_with_two_lost_candidates_names_neither() -> None:
    before = _component(public=("pkg.x:run", "pkg.y:run"))
    after = _component(public=("pkg.z:run",))

    assert _component_diff(before, after) == ("component 'comp'.public gained 'pkg.z:run'",)


def test_two_public_gains_alike_one_lost_entry_name_it_for_neither() -> None:
    before = _component(public=("pkg.a:run",))
    after = _component(public=("pkg.b:run", "pkg.c:run"))

    assert _component_diff(before, after) == (
        "component 'comp'.public gained 'pkg.b:run'",
        "component 'comp'.public gained 'pkg.c:run'",
    )


def test_a_public_symbol_gain_is_not_named_in_place_of_a_module_entry() -> None:
    before = _component(public=("pkg.api",))
    after = _component(public=("pkg.x:api",))

    assert _component_diff(before, after) == ("component 'comp'.public gained 'pkg.x:api'",)


def test_narrowing_never_needs_an_amendment() -> None:
    """Every narrowing row above already asserts `findings == ()`; this restates the rule."""
    before = _forbidden_construct(constructs=("eval",))
    after = _forbidden_construct(constructs=("eval", "exec"))
    assert contract_widenings(_contract(rules=(before,)), _contract(rules=(after,))) == ()


def test_an_unenumerated_difference_is_treated_as_widening() -> None:
    """Fail closed (#11): a field no classifier names still gets reported, in either direction.

    `target_symbol` narrowing from "the whole target" to one symbol reads, intuitively, like a
    narrowing - but this module has no classifier for it, so both directions must be reported.
    """
    unset_to_set = _rule_diff(
        _forbidden_dependency(target_symbol=None), _forbidden_dependency(target_symbol="Foo")
    )
    set_to_unset = _rule_diff(
        _forbidden_dependency(target_symbol="Foo"), _forbidden_dependency(target_symbol=None)
    )
    assert unset_to_set != () and set_to_unset != ()


def test_declarations_and_schema_are_unenumerated_and_widen() -> None:
    before = _contract()
    after = replace(before, schema="urn:archkeel:contract:2")
    assert contract_widenings(before, after) != ()


def test_baseline_widening_reports_a_padded_or_new_entry() -> None:
    fingerprint = ViolationFingerprint(("R",), ("a",))
    before = (KnownViolation(fingerprint, 1),)
    padded = (KnownViolation(fingerprint, 2),)
    new_entry = (*before, KnownViolation(ViolationFingerprint(("R",), ("b",)), 1))

    assert baseline_widenings(before, padded, cycle_rules=frozenset()) == (
        "baseline entry widened: R | a (2 now, 1 before)",
    )
    assert baseline_widenings(before, new_entry, cycle_rules=frozenset()) == (
        "baseline entry widened: R | b (1 now, 0 before)",
    )


def test_baseline_role_change_is_protected_semantic_evidence() -> None:
    fingerprint = ViolationFingerprint(("R",), ("a", "b"))
    before = (KnownViolation(fingerprint, 1, (("a", "b"),)),)
    after = (KnownViolation(fingerprint, 1, (("a", "c"),)),)

    assert baseline_widenings(before, after, cycle_rules=frozenset()) == (
        "baseline entry roles changed: R | a b (a -> b before; a -> c now)",
    )


def test_baseline_shrinking_is_narrowing() -> None:
    fingerprint = ViolationFingerprint(("R",), ("a",))
    before = (KnownViolation(fingerprint, 2, (("a", "b"), ("c", "b"))),)
    shrunk = (KnownViolation(fingerprint, 1, (("a", "b"),)),)
    removed: tuple[KnownViolation, ...] = ()
    assert baseline_widenings(before, shrunk, cycle_rules=frozenset()) == ()
    assert baseline_widenings(before, removed, cycle_rules=frozenset()) == ()


def test_verify_amendment_binds_the_exact_digest_pair() -> None:
    amendment = Amendment("b" * 64, "a" * 64, "architect", "because")
    assert verify_amendment(amendment, before_digest="b" * 64, after_digest="a" * 64)
    assert not verify_amendment(amendment, before_digest="b" * 64, after_digest="c" * 64)
    assert not verify_amendment(amendment, before_digest="d" * 64, after_digest="a" * 64)


def test_amendment_round_trips_through_codec() -> None:
    amendment = Amendment(
        contract_digest(_contract()),
        contract_digest(_contract(rules=(_forbidden_dependency(),))),
        "architect",
        "because",
    )
    assert (
        parse_amendment(
            {
                "schema_version": "1.0.0",
                "before_digest": amendment.before_digest,
                "after_digest": amendment.after_digest,
                "decided_by": amendment.decided_by,
                "rationale": amendment.rationale,
            }
        )
        == amendment
    )
    assert json.loads(amendment_bytes(amendment))["before_digest"] == amendment.before_digest


# --- End-to-end: a real Git repository, through run_validate directly. ---


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "commit.gpgsign=false", *args], cwd=root, stderr=subprocess.PIPE, text=True
    ).strip()


def _repo_at_two_revisions(tmp_path: Path, base_files: dict[str, str | None]) -> tuple[Path, str]:
    """Commit the shop sample with `base_files` overlaid, returning the root and that revision."""
    root = _prepare_repo(tmp_path, base_files)
    return root, _git(root, "rev-parse", "HEAD")


_WIDEN_ALLOWED_SOURCES = {
    "architecture-contract.json": contract_rule_field(
        "DEP-APP-NO-STORE-SQLITE", allowed_sources=["shop.app.maintenance", "shop.app.orders"]
    )
}


def test_validate_without_against_is_unchanged(tmp_path: Path) -> None:
    """AD-61 (#11): passing no --against must not change a single existing behaviour."""
    root, _base = _repo_at_two_revisions(tmp_path, {})
    with_default, files_with_default = run_validate(root, SHOP_CONFIG, observe)
    explicit_none, files_explicit_none = run_validate(root, SHOP_CONFIG, observe, against=None)
    assert with_default == explicit_none
    assert files_with_default == files_explicit_none == {}


def test_a_widening_fails_and_names_the_field(tmp_path: Path) -> None:
    root, base = _repo_at_two_revisions(tmp_path, {})
    apply_overlay(root, dict(_WIDEN_ALLOWED_SOURCES))

    result, _ = run_validate(root, SHOP_CONFIG, observe, against=base)

    assert result.exit_code == 1, result.diagnostics
    assert result.diagnostics == ()
    assert result.failures == (
        "rule DEP-APP-NO-STORE-SQLITE.allowed_sources gained 'shop.app.orders'",
    )


def test_adding_an_exact_boundary_allowance_widens_against(tmp_path: Path) -> None:
    root, base = _repo_at_two_revisions(tmp_path, {})
    allowance = {
        "qualified_name": "shop.app.orders.place_order",
        "position": "return",
        "field_path": "payload",
        "annotation": "dict[str, JsonValue]",
    }
    entities_path = root / "shop/model/entities.py"
    entities = entities_path.read_text()
    entities = entities.replace(
        "class Order:\n    order_id: str",
        "class Order:\n    payload: dict[str, JsonValue]\n    order_id: str",
    )
    apply_overlay(
        root,
        {
            "architecture-contract.json": contract_rule_field(
                "APP-TYPES-NOT-DICT", allowed_positions=[allowance]
            ),
            "shop/model/entities.py": entities,
        },
    )

    result, _ = run_validate(root, SHOP_CONFIG, observe, against=base)

    assert result.exit_code == 1, result.diagnostics
    assert any(
        "APP-TYPES-NOT-DICT.allowed_positions gained" in failure for failure in result.failures
    )


def test_a_widening_with_a_valid_amendment_passes(tmp_path: Path) -> None:
    root, base = _repo_at_two_revisions(tmp_path, {})
    apply_overlay(root, dict(_WIDEN_ALLOWED_SOURCES))
    amendment_path = root / "widening-amendment.json"

    write_result, write_files = run_validate(
        root,
        SHOP_CONFIG,
        observe,
        against=base,
        amendment=amendment_path,
        write_amendment=True,
        decided_by="Jordan (architect)",
        rationale="Orders needs the sqlite exemption during the migration.",
    )
    assert write_result.exit_code == 0
    amendment_path.write_bytes(write_files[str(amendment_path)])

    result, _ = run_validate(root, SHOP_CONFIG, observe, against=base, amendment=amendment_path)
    assert (result.exit_code, result.failures) == (0, ())


def test_the_same_amendment_against_a_different_change_fails(tmp_path: Path) -> None:
    root, base = _repo_at_two_revisions(tmp_path, {})
    apply_overlay(root, dict(_WIDEN_ALLOWED_SOURCES))
    amendment_path = root / "widening-amendment.json"
    _, write_files = run_validate(
        root,
        SHOP_CONFIG,
        observe,
        against=base,
        amendment=amendment_path,
        write_amendment=True,
        decided_by="Jordan (architect)",
        rationale="Orders needs the sqlite exemption during the migration.",
    )
    amendment_path.write_bytes(write_files[str(amendment_path)])

    # A second, larger widening: the amendment was written for the smaller change above.
    apply_overlay(
        root,
        {
            "architecture-contract.json": contract_rule_field(
                "DEP-APP-NO-STORE-SQLITE",
                allowed_sources=["shop.app.maintenance", "shop.app.orders", "shop.model.entities"],
            )
        },
    )

    result, _ = run_validate(root, SHOP_CONFIG, observe, against=base, amendment=amendment_path)

    assert result.exit_code == 1
    assert result.failures == (
        "rule DEP-APP-NO-STORE-SQLITE.allowed_sources gained 'shop.app.orders'",
        "rule DEP-APP-NO-STORE-SQLITE.allowed_sources gained 'shop.model.entities'",
    )


def test_an_unresolvable_against_revision_is_exit_two(tmp_path: Path) -> None:
    root, _base = _repo_at_two_revisions(tmp_path, {})

    result, _ = run_validate(root, SHOP_CONFIG, observe, against="not-a-real-revision")

    assert result.exit_code == 2
    assert [item.code for item in result.diagnostics] == ["against.invalid"]


def test_a_missing_amendment_file_is_exit_two(tmp_path: Path) -> None:
    root, base = _repo_at_two_revisions(tmp_path, {})

    result, _ = run_validate(
        root, SHOP_CONFIG, observe, against=base, amendment=root / "does-not-exist.json"
    )

    assert result.exit_code == 2
    assert [item.code for item in result.diagnostics] == ["amendment.invalid"]


def test_a_malformed_amendment_file_is_exit_two(tmp_path: Path) -> None:
    root, base = _repo_at_two_revisions(tmp_path, {})
    amendment_path = root / "widening-amendment.json"
    amendment_path.write_text('{"schema_version": "1.0.0"}')

    result, _ = run_validate(root, SHOP_CONFIG, observe, against=base, amendment=amendment_path)

    assert result.exit_code == 2
    assert [item.code for item in result.diagnostics] == ["amendment.invalid"]


def test_a_padded_baseline_entry_widens_the_contract(tmp_path: Path) -> None:
    """AD-61 (#11): the baseline is part of the contract's surface, checked the same way."""
    root, _base = _repo_at_two_revisions(tmp_path, {})
    baseline_path = root / "known-violations.json"
    baseline_path.write_bytes(baseline_bytes(()))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "empty baseline")
    base_with_baseline = _git(root, "rev-parse", "HEAD")

    fingerprint = ViolationFingerprint(("CONSTRUCT-NO-DYNAMIC",), ("shop.model.probe.read",))
    baseline_path.write_bytes(baseline_bytes((KnownViolation(fingerprint, 1),)))

    result, _ = run_validate(
        root, SHOP_CONFIG, observe, against=base_with_baseline, baseline=baseline_path
    )

    assert result.exit_code == 1
    assert "baseline entry widened: CONSTRUCT-NO-DYNAMIC | shop.model.probe.read" in " ".join(
        result.failures
    )


def test_role_only_baseline_drift_fails_against_with_the_same_fingerprint_and_count(
    tmp_path: Path,
) -> None:
    fingerprint = ViolationFingerprint(
        ("DEP-IMPORT",), ("shop.app.orders.summarize", "shop.cli.main")
    )
    root, _base = _repo_at_two_revisions(tmp_path, {})
    baseline_path = root / "known-violations.json"
    baseline_path.write_bytes(
        baseline_bytes((KnownViolation(fingerprint, 1, (("shop.cli.main", "shop.app.orders"),)),))
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "baseline role")
    base_with_baseline = _git(root, "rev-parse", "HEAD")
    baseline_path.write_bytes(
        baseline_bytes(
            (KnownViolation(fingerprint, 1, (("shop.cli.main", "shop.app.orders.extra"),)),)
        )
    )

    result, _ = run_validate(
        root, SHOP_CONFIG, observe, against=base_with_baseline, baseline=baseline_path
    )

    assert result.exit_code == 1
    assert (
        "baseline entry roles changed: DEP-IMPORT | "
        "shop.app.orders.summarize shop.cli.main "
        "(shop.cli.main -> shop.app.orders before; "
        "shop.cli.main -> shop.app.orders.extra now)" in result.failures
    )


def test_a_shrunk_baseline_entry_is_narrowing_and_passes(tmp_path: Path) -> None:
    fingerprint = ViolationFingerprint(("CONSTRUCT-NO-DYNAMIC",), ("shop.model.probe.read",))
    root, _base = _repo_at_two_revisions(tmp_path, {})
    baseline_path = root / "known-violations.json"
    baseline_path.write_bytes(baseline_bytes((KnownViolation(fingerprint, 1),)))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "padded baseline")
    base_with_baseline = _git(root, "rev-parse", "HEAD")

    baseline_path.write_bytes(baseline_bytes(()))

    result, _ = run_validate(
        root, SHOP_CONFIG, observe, against=base_with_baseline, baseline=baseline_path
    )

    assert (result.exit_code, result.failures) == (0, ())


_BOUNDARY_ALLOWANCE = {
    "qualified_name": "shop.app.orders.summarize",
    "position": "return",
    "field_path": "items.payload",
    "annotation": "dict[str, str]",
}


def _boundary_allowance_contract(allowed_positions: list[dict[str, str]]) -> str:
    raw = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    rule = next(item for item in raw["rules"] if item["id"] == "APP-TYPES-NOT-DICT")
    if allowed_positions:
        rule["allowed_positions"] = allowed_positions
    else:
        rule.pop("allowed_positions", None)
    return json.dumps(raw, indent=2) + "\n"


def test_boundary_type_allowance_addition_needs_amendment(tmp_path: Path) -> None:
    root, base = _repo_at_two_revisions(tmp_path, {})
    apply_overlay(
        root, {"architecture-contract.json": _boundary_allowance_contract([_BOUNDARY_ALLOWANCE])}
    )

    result, _ = run_validate(root, SHOP_CONFIG, observe, against=base)

    assert result.exit_code == 1
    assert result.failures


def test_boundary_type_allowance_broadening_needs_amendment(tmp_path: Path) -> None:
    broader = {**_BOUNDARY_ALLOWANCE, "annotation": "dict[str, Any]"}
    root, base = _repo_at_two_revisions(
        tmp_path,
        {"architecture-contract.json": _boundary_allowance_contract([_BOUNDARY_ALLOWANCE])},
    )
    apply_overlay(
        root,
        {
            "architecture-contract.json": _boundary_allowance_contract(
                [_BOUNDARY_ALLOWANCE, broader]
            )
        },
    )

    result, _ = run_validate(root, SHOP_CONFIG, observe, against=base)

    assert result.exit_code == 1
    assert result.failures


def test_boundary_type_allowance_removal_is_narrowing(tmp_path: Path) -> None:
    root, base = _repo_at_two_revisions(
        tmp_path,
        {"architecture-contract.json": _boundary_allowance_contract([_BOUNDARY_ALLOWANCE])},
    )
    apply_overlay(root, {"architecture-contract.json": _boundary_allowance_contract([])})

    result, _ = run_validate(root, SHOP_CONFIG, observe, against=base)

    assert (result.exit_code, result.failures) == (0, ())
