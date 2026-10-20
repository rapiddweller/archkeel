# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Contract parsing constructs nominal rule APIs without changing the wire grammar."""

import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Literal, get_type_hints

import pytest

from archkeel.check.declarations import project_rule_declaration
from archkeel.ir import model
from archkeel.ir.architecture_graph import ArchitectureRuleKind, DecisionMaker
from archkeel.ir.codec import contract_bytes, parse_contract

ROOT = Path(__file__).parents[1]
RULES = {
    "call_owner": ("CallOwnerRule", {"source": "sample", "target": "sample.store.page"}),
    "forbidden_call_argument": (
        "ForbiddenCallArgumentRule",
        {"source": "sample", "target": "sample.store.page", "parameter": "query"},
    ),
    "forbidden_dependency": (
        "ForbiddenDependencyRule",
        {"source": "sample.core", "target": "json", "include_type_checking": True},
    ),
    "allowed_dependency": ("AllowedDependencyRule", {"source": "core", "target": "core"}),
    "forbidden_construct": ("ForbiddenConstructRule", {"source": "sample", "constructs": ["eval"]}),
    "external_dependency_scope": (
        "ExternalDependencyScopeRule",
        {"dependency": "json", "allowed_sources": ["sample"]},
    ),
    "complete_assignment": ("CompleteAssignmentRule", {"source": "sample"}),
    "root_layout": ("RootLayoutRule", {"root": "sample", "allowed_children": ["sample.core"]}),
    "complete_external_scope": ("CompleteExternalScopeRule", {"source": "sample"}),
    "complete_requires": ("CompleteRequiresRule", {}),
    "layer_order": ("LayerOrderRule", {"layers": ["outer", "inner"]}),
    "no_component_cycles": ("NoComponentCyclesRule", {}),
    "interface_boundary": ("InterfaceBoundaryRule", {}),
    "sibling_isolation": ("SiblingIsolationRule", {"members": ["sample.core", "sample.other"]}),
    "symbol_placement": (
        "SymbolPlacementRule",
        {"source": "sample", "class_kinds": ["enum"], "allowed_sources": ["sample"]},
    ),
    "boundary_types": ("BoundaryTypesRule", {"source": "sample"}),
    "protocol_declarations": (
        "ProtocolDeclarationsRule",
        {
            "source": "sample",
            "protocol": "sample.Reader",
            "selectors": [{"role": "parameter", "name": "reader", "visibility": "public"}],
        },
    ),
    "bounded_numeric_operand": (
        "BoundedNumericOperandRule",
        {
            "source": "sample",
            "form": "both",
            "terminal_suffix": "nonce",
            "minimum_value": 4_294_967_296,
        },
    ),
    "source_ownership": (
        "SourceOwnershipRule",
        {
            "source": "sample",
            "mode": "retired",
            "symbols": ["sample.old"],
            "roles": ["read"],
        },
    ),
}
RULE_SCHEMA_VERSIONS = {
    "forbidden_construct": "3.11.0",
    "forbidden_call_argument": "3.10.0",
    "protocol_declarations": "3.9.0",
    "bounded_numeric_operand": "3.8.0",
    "source_ownership": "3.12.0",
}


def _raw():
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    raw["schema_version"] = "3.10.0"
    raw["rules"] = []
    return raw


@pytest.mark.parametrize("kind", RULES)
def test_every_rule_variant_decodes_the_shared_kind_and_attribution(kind):
    name, fields = RULES[kind]
    raw = _raw()
    raw["schema_version"] = RULE_SCHEMA_VERSIONS.get(kind, "3.7.0")
    raw["rules"] = [
        {
            "id": "rule",
            "kind": kind,
            "rationale": "One owner.",
            "provenance": ["docs/architecture/sample.md"],
            "decided_by": "architect",
            **fields,
        }
    ]
    contract = parse_contract(raw)
    rule = contract.rules[0]
    assert rule.kind is ArchitectureRuleKind(kind)
    assert rule.decided_by is DecisionMaker.ARCHITECT
    hints = get_type_hints(getattr(model, name))
    assert hints["kind"] == Literal[ArchitectureRuleKind(kind)]
    assert hints["decided_by"] is DecisionMaker
    assert parse_contract(json.loads(contract_bytes(contract))) == contract
    encoded = json.loads(contract_bytes(contract))["rules"][0]
    assert encoded["kind"] == kind and encoded["decided_by"] == "architect"


def test_forbidden_construct_selector_is_part_of_the_same_closed_rule_variant():
    raw = _raw()
    raw["schema_version"] = "3.11.0"
    raw["rules"] = [
        {
            "id": "SELECTOR",
            "kind": "forbidden_construct",
            "source": "sample",
            "constructs": ["string_literal_compare"],
            "selector": {
                "receiver": "sample.Connection",
                "member": "backend",
                "role": "equality",
                "literal": "flat",
            },
            "rationale": "Use the named backend port.",
            "provenance": ["docs/architecture/sample.md"],
            "decided_by": "architect",
        }
    ]
    rule = parse_contract(raw).rules[0]
    assert rule.selector is not None
    assert rule.selector.receiver == "sample.Connection"
    assert rule.selector.role.value == "equality"


@pytest.mark.parametrize("value", ["permanent", "migration"])
def test_compatibility_lifetime_is_a_real_nominal_value_with_identical_wire(value):
    raw = _raw()
    raw["declarations"] = {
        "compat": [{"module": "old.module", "target": "new.module", "lifetime": value}]
    }
    contract = parse_contract(raw)
    assert contract.declarations.compat[0].lifetime is model.CompatibilityLifetime(value)
    assert json.loads(contract_bytes(contract))["declarations"]["compat"][0]["lifetime"] == value


@pytest.mark.parametrize("level", ["component", "module"])
def test_cycle_level_preserves_default_omission_and_returns_nominal_module(level):
    raw = _raw()
    raw["rules"] = [
        {
            "id": "cycles",
            "kind": "no_component_cycles",
            "rationale": "One owner.",
            "provenance": ["docs/architecture/sample.md"],
            "decided_by": "agent",
            "level": level,
        }
    ]
    contract = parse_contract(raw)
    expected = None if level == "component" else model.CycleLevel.MODULE
    assert contract.rules[0].level is expected
    encoded = json.loads(contract_bytes(contract))["rules"][0]
    assert encoded.get("level") == (None if level == "component" else "module")


@pytest.mark.parametrize("value", [None, True, 1, [], {}, "", "future"])
def test_unknown_rule_kind_keeps_the_public_diagnostic(value):
    from archkeel.ir.codec_contract import _rule_kind

    with pytest.raises(ValueError, match=r"^rules\[0\]\.kind is unsupported$"):
        _rule_kind({"kind": value}, "rules[0]")


@pytest.mark.parametrize("value", [None, True, 1, [], {}, "", "future"])
def test_invalid_compatibility_lifetime_keeps_the_public_diagnostic(value):
    from archkeel.ir.codec_contract import _parse_compat

    with pytest.raises(ValueError, match=r"^compat\[0\]\.lifetime must be permanent or migration$"):
        _parse_compat(
            {"module": "old.module", "target": "new.module", "lifetime": value}, "compat[0]"
        )


def test_component_and_requires_decisions_use_the_same_owner():
    raw = _raw()
    raw["components"][0]["decided_by"] = "architect"
    raw["components"][0]["requires"] = [
        {"component": "core", "rationale": "Explicit permission.", "decided_by": "agent"}
    ]
    contract = parse_contract(raw)
    component = contract.components[0]
    assert component.decided_by is DecisionMaker.ARCHITECT
    assert component.requires[0].decided_by is DecisionMaker.AGENT
    assert parse_contract(json.loads(contract_bytes(contract))) == contract


def test_rule_dispatch_covers_the_single_owned_kind_vocabulary():
    from archkeel.ir.codec_contract import _RULE_PARSERS

    assert set(_RULE_PARSERS) == set(ArchitectureRuleKind)
    assert set(RULES) == set(ArchitectureRuleKind)


def test_module_path_error_precedes_other_invalid_fields():
    from archkeel.ir.codec_contract import _parse_module_target

    with pytest.raises(
        ValueError, match=r"^modules\[0\]\.path must be a repository-relative source path$"
    ):
        _parse_module_target({"path": "../outside.py", "responsibility": ""}, "modules[0]")


def _legacy_rules():
    """Use the public positional constructors directly, independently of JSON decoding."""
    provenance = ("docs/architecture/sample.md",)
    return [
        model.ForbiddenDependencyRule(
            "r",
            "forbidden_dependency",
            "sample",
            "json",
            True,
            "Why.",
            provenance,
            "architect",
        ),
        model.AllowedDependencyRule(
            "r",
            "allowed_dependency",
            "core",
            "core",
            "Why.",
            provenance,
            "architect",
        ),
        model.ForbiddenConstructRule(
            "r",
            "forbidden_construct",
            "sample",
            (model.ForbiddenConstructKind.EVAL,),
            "Why.",
            provenance,
            "architect",
        ),
        model.ExternalDependencyScopeRule(
            "r",
            "external_dependency_scope",
            "json",
            ("sample",),
            "Why.",
            provenance,
            "architect",
        ),
        model.CompleteAssignmentRule(
            "r",
            "complete_assignment",
            "sample",
            "Why.",
            provenance,
            "architect",
        ),
        model.RootLayoutRule(
            "r",
            "root_layout",
            "sample",
            ("sample.core",),
            "Why.",
            provenance,
            "architect",
        ),
        model.CompleteExternalScopeRule(
            "r",
            "complete_external_scope",
            "sample",
            "Why.",
            provenance,
            "architect",
        ),
        model.CompleteRequiresRule("r", "complete_requires", "Why.", provenance, "architect"),
        model.LayerOrderRule(
            "r",
            "layer_order",
            ("outer", "inner"),
            "Why.",
            provenance,
            "architect",
        ),
        model.NoComponentCyclesRule("r", "no_component_cycles", "Why.", provenance, "architect"),
        model.InterfaceBoundaryRule("r", "interface_boundary", "Why.", provenance, "architect"),
        model.SiblingIsolationRule(
            "r",
            "sibling_isolation",
            ("sample.core", "sample.other"),
            "Why.",
            provenance,
            "architect",
        ),
        model.SymbolPlacementRule(
            "r",
            "symbol_placement",
            "sample",
            (model.SymbolClassKind.ENUM,),
            "Why.",
            provenance,
            "architect",
        ),
        model.BoundaryTypesRule("r", "boundary_types", "sample", "Why.", provenance, "architect"),
    ]


@pytest.mark.parametrize("rule", _legacy_rules(), ids=lambda rule: str(rule.kind))
def test_every_legacy_positional_constructor_has_nominal_frozen_slotted_identity(rule):
    expected = ArchitectureRuleKind(rule.kind)
    assert rule.id == "r" and rule.rationale == "Why."
    assert rule.kind is expected
    assert rule.decided_by is DecisionMaker.ARCHITECT
    assert not hasattr(rule, "__dict__")
    with pytest.raises(FrozenInstanceError):
        rule.kind = expected
    same = replace(rule, kind=expected, decided_by=DecisionMaker.AGENT)
    assert same.kind is expected and same.decided_by is DecisionMaker.AGENT
    legacy = replace(same, kind=expected.value, decided_by="architect")
    assert legacy.kind is expected and legacy.decided_by is DecisionMaker.ARCHITECT


def test_direct_legacy_component_shim_and_cycle_values_are_normalized():
    component = model.ContractComponent(
        "c", "core", "component", ("sample",), ("Own.",), (), (), decided_by="architect"
    )
    required = model.RequiredComponent("core", "Why.", decided_by="agent")
    assert component.decided_by is DecisionMaker.ARCHITECT
    assert required.decided_by is DecisionMaker.AGENT
    assert replace(component, decided_by=None).decided_by is None
    assert replace(required, decided_by=None).decided_by is None
    shim = model.CompatibilityShim("old.module", "new.module", "migration")
    assert shim.lifetime is model.CompatibilityLifetime.MIGRATION
    assert (
        replace(shim, lifetime=model.CompatibilityLifetime.PERMANENT).lifetime
        is model.CompatibilityLifetime.PERMANENT
    )
    cycles = _legacy_rules()[9]
    assert replace(cycles, level="module").level is model.CycleLevel.MODULE
    assert replace(cycles, level=model.CycleLevel.COMPONENT).level is None


@pytest.mark.parametrize("form", ["binary", "augmented", "both"])
def test_direct_numeric_rule_normalizes_form_and_shared_tags(form):
    rule = model.BoundedNumericOperandRule(
        "r",
        "bounded_numeric_operand",
        "sample",
        form,
        "nonce",
        4,
        "Why.",
        ("design.md",),
        "architect",
    )
    assert rule.form is model.NumericOperandForm(form)
    assert rule.kind is ArchitectureRuleKind.BOUNDED_NUMERIC_OPERAND
    assert rule.decided_by is DecisionMaker.ARCHITECT
    assert project_rule_declaration(rule)["data"]["form"] == form
    assert replace(rule, form=rule.form).form is rule.form
    with pytest.raises(ValueError):
        replace(rule, form="unsupported")
