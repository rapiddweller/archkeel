# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The dependency API retains owned types and one selection interpretation."""

from dataclasses import FrozenInstanceError, replace
from enum import StrEnum

import pytest
from test_dependency_selectors import _contract, _ownership

from archkeel.check.declarations import project_rule_declaration
from archkeel.ir import codec
from archkeel.ir.model import EvidenceClass, Record, RecordData, dependency_owners, forbidden_dependency_scopes


def _record(raw):
    return Record(
        id=raw["id"],
        evidence_class=EvidenceClass(raw["evidence_class"]),
        area=raw["area"],
        kind=raw["kind"],
        title=raw["title"],
        subjects=tuple(raw["subjects"]),
        evidence_ids=tuple(raw["evidence_ids"]),
        rule_ids=tuple(raw["rule_ids"]),
        fact_ids=tuple(raw["fact_ids"]),
        provenance=tuple(raw["provenance"]),
        data=RecordData(tuple(raw["data"].items())),
    )


def test_parsed_modes_are_owned_enum_values():
    raw = _contract(source_match="exact", target_match="prefix", target_kind="import_namespace")
    raw["schema_version"] = "3.5.0"
    [rule] = codec.parse_contract(raw).rules
    assert isinstance(rule.source_match, StrEnum)
    assert isinstance(rule.target_match, StrEnum)
    assert isinstance(rule.target_kind, StrEnum)
    assert type(rule.source_match) is type(rule.target_match)
    assert type(rule.source_match).__name__ == "SelectorMatch"
    assert type(rule.target_kind).__name__ == "DependencyTargetKind"
    assert rule.source_match.value == "exact"
    assert rule.target_kind.value == "import_namespace"


def test_selection_names_immutable_source_and_target_scopes():
    contract = codec.parse_contract(_contract())
    selection = forbidden_dependency_scopes(contract.rules[0], _ownership(contract))
    assert hasattr(selection, "source")
    assert selection.source.packages == ("sample.caller", "sample.caller_extra")
    assert selection.target.matches("sample.errors_extra.child")
    assert not selection.target.matches("sample.errors_other")
    assert tuple(selection) == (selection.source, selection.target)
    with pytest.raises(AttributeError):
        selection.target = selection.source


def test_typed_selector_is_immutable_and_rejects_untyped_modes():
    [rule] = codec.parse_contract(_contract()).rules
    assert hasattr(rule, "selector")
    selector = rule.selector
    with pytest.raises(FrozenInstanceError):
        selector.source = "other"
    for field, value in (
        ("source_match", "exact"),
        ("target_match", "prefix"),
        ("target_kind", "module"),
    ):
        with pytest.raises(ValueError):
            replace(selector, **{field: value})


def test_record_boundary_decodes_selector_once_without_fake_metadata():
    contract = codec.parse_contract(_contract(source_match="exact"))
    record = _record(project_rule_declaration(contract.rules[0]))
    assert hasattr(codec, "parse_dependency_selector")
    selector = codec.parse_dependency_selector(record)
    assert selector == contract.rules[0].selector
    assert selector.select(dependency_owners(_ownership(contract))) == forbidden_dependency_scopes(
        contract.rules[0], _ownership(contract)
    )
    assert selector.component_pair(dependency_owners(_ownership(contract))) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_match", "typo"),
        ("target_match", None),
        ("target_kind", "package"),
        ("source_match", True),
        ("source", 7),
        ("target", ""),
    ],
)
def test_record_boundary_rejects_invalid_selector_values(field, value):
    [rule] = codec.parse_contract(_contract()).rules
    raw = project_rule_declaration(rule)
    raw["data"][field] = value
    assert hasattr(codec, "parse_dependency_selector")
    with pytest.raises(ValueError):
        codec.parse_dependency_selector(_record(raw))


def test_legacy_records_receive_typed_defaults_and_keep_default_bytes():
    [rule] = codec.parse_contract(_contract()).rules
    assert hasattr(codec, "parse_dependency_selector")
    raw = project_rule_declaration(rule)
    assert not {"source_match", "target_match", "target_kind"} & raw["data"].keys()
    selector = codec.parse_dependency_selector(_record(raw))
    assert isinstance(selector.source_match, StrEnum)
    assert selector == rule.selector
    encoded = codec.decode_json(codec.contract_bytes(codec.parse_contract(_contract())))
    assert not {"source_match", "target_match", "target_kind"} & encoded["rules"][0].keys()


def test_ambiguous_ownership_does_not_expand_selection():
    contract = codec.parse_contract(_contract())
    [rule] = contract.rules
    assert hasattr(rule, "selector")
    ownership = (*_ownership(contract), ("ambiguous", ("sample.caller",), ()))
    assert rule.selector.component_pair(dependency_owners(ownership)) is None
    selection = rule.selector.select(dependency_owners(ownership))
    assert selection.source.matches("sample.caller.child")
    assert not selection.source.matches("sample.caller_extra.child")


def test_exact_owned_modules_expand_only_legacy_component_pairs():
    raw = _contract()
    raw["components"][0]["exact_modules"] = ["sample.runner"]
    raw["components"][1]["exact_modules"] = ["sample.failure"]
    contract = codec.parse_contract(raw)
    [rule] = contract.rules
    assert hasattr(rule, "selector")
    selection = rule.selector.select(dependency_owners(_ownership(contract)))
    assert selection.source.matches("sample.runner")
    assert selection.target.matches("sample.failure")
    assert not selection.target.matches("sample.failure.child")
    namespace = replace(rule.selector, target_kind=type(rule.target_kind).IMPORT_NAMESPACE)
    assert not namespace.select(dependency_owners(_ownership(contract))).source.matches("sample.runner")
    assert not namespace.select(dependency_owners(_ownership(contract))).target.matches("sample.failure")


def test_named_ownership_adapter_preserves_legacy_shapes_order_and_duplicates():
    from archkeel.ir import dependency, model
    from archkeel.ir.model import dependency_owners

    legacy = (
        ("label", ("sample.primary",), ("sample.entry",)),
        ("label", ("sample.extra",), ()),
    )
    owners = dependency_owners(legacy)
    assert tuple(owner.identity for owner in owners) == ("label", "label")
    assert tuple(owner.modules.packages for owner in owners) == (
        ("sample.primary",), ("sample.extra",),
    )
    assert owners[0].modules.exact_modules == ("sample.entry",)
    assert isinstance(owners[0], dependency.DependencyOwner)
    assert model.ComponentOwnership is dependency.ComponentOwnership
    assert model.ComponentOwnership == tuple[str, tuple[str, ...], tuple[str, ...]]
    assert model.PackageComponentOwnership == tuple[str, tuple[str, ...]]
    assert model.ComponentOwnershipInput == model.ComponentOwnership | model.PackageComponentOwnership
    with pytest.raises(FrozenInstanceError):
        owners[0].identity = "changed"


def test_typed_policy_consumes_named_ownership_and_reuses_immutable_modules():
    from archkeel.ir.model import dependency_owners

    contract = codec.parse_contract(_contract())
    owners = dependency_owners(_ownership(contract))
    selection = contract.rules[0].selector.select(owners)
    assert selection.source is owners[0].modules
    assert selection.target is owners[1].modules
    assert contract.rules[0].selector.component_pair(owners) == ("caller", "errors")
