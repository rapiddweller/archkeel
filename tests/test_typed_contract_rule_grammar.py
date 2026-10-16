# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Contract parsing constructs nominal rule APIs without changing the wire grammar."""

import json
from pathlib import Path
from typing import Literal, get_type_hints

import pytest

from archkeel.ir.architecture_graph import ArchitectureRuleKind, DecisionMaker
from archkeel.ir.codec import contract_bytes, parse_contract
from archkeel.ir import model

ROOT = Path(__file__).parents[1]
RULES = {
    "forbidden_dependency": ("ForbiddenDependencyRule", {"source": "sample.core", "target": "json", "include_type_checking": True}),
    "allowed_dependency": ("AllowedDependencyRule", {"source": "core", "target": "core"}),
    "forbidden_construct": ("ForbiddenConstructRule", {"source": "sample", "constructs": ["eval"]}),
    "external_dependency_scope": ("ExternalDependencyScopeRule", {"dependency": "json", "allowed_sources": ["sample"]}),
    "complete_assignment": ("CompleteAssignmentRule", {"source": "sample"}),
    "root_layout": ("RootLayoutRule", {"root": "sample", "allowed_children": ["sample.core"]}),
    "complete_external_scope": ("CompleteExternalScopeRule", {"source": "sample"}),
    "complete_requires": ("CompleteRequiresRule", {}),
    "layer_order": ("LayerOrderRule", {"layers": ["outer", "inner"]}),
    "no_component_cycles": ("NoComponentCyclesRule", {}),
    "interface_boundary": ("InterfaceBoundaryRule", {}),
    "sibling_isolation": ("SiblingIsolationRule", {"members": ["sample.core", "sample.other"]}),
    "symbol_placement": ("SymbolPlacementRule", {"source": "sample", "class_kinds": ["enum"], "allowed_sources": ["sample"]}),
    "boundary_types": ("BoundaryTypesRule", {"source": "sample"}),
}


def _raw():
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    raw["schema_version"] = "3.6.0"
    raw["rules"] = []
    return raw


@pytest.mark.parametrize("kind", RULES)
def test_every_rule_variant_decodes_the_shared_kind_and_attribution(kind):
    name, fields = RULES[kind]
    raw = _raw()
    raw["rules"] = [{"id": "rule", "kind": kind, "rationale": "One owner.", "provenance": ["docs/architecture/sample.md"], "decided_by": "architect", **fields}]
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


@pytest.mark.parametrize("value", ["permanent", "migration"])
def test_compatibility_lifetime_is_a_real_nominal_value_with_identical_wire(value):
    raw = _raw()
    raw["declarations"] = {"compat": [{"module": "old.module", "target": "new.module", "lifetime": value}]}
    contract = parse_contract(raw)
    assert contract.declarations.compat[0].lifetime is model.CompatibilityLifetime(value)
    assert json.loads(contract_bytes(contract))["declarations"]["compat"][0]["lifetime"] == value


@pytest.mark.parametrize("level", ["component", "module"])
def test_cycle_level_preserves_default_omission_and_returns_nominal_module(level):
    raw = _raw()
    raw["rules"] = [{"id": "cycles", "kind": "no_component_cycles", "rationale": "One owner.", "provenance": ["docs/architecture/sample.md"], "decided_by": "agent", "level": level}]
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
        _parse_compat({"module": "old.module", "target": "new.module", "lifetime": value}, "compat[0]")

def test_component_and_requires_decisions_use_the_same_owner():
    raw = _raw()
    raw["components"][0]["decided_by"] = "architect"
    raw["components"][0]["requires"] = [{"component": "core", "rationale": "Explicit permission.", "decided_by": "agent"}]
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

    with pytest.raises(ValueError, match=r"^modules\[0\]\.path must be a repository-relative source path$"):
        _parse_module_target({"path": "../outside.py", "responsibility": ""}, "modules[0]")
