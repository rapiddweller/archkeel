# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""An explicit import-name prohibition needs source evidence, not a recreated target."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_dependency_selectors import _contract, _import, _module, _ownership

from archkeel.check.declarations import project_rule_declaration
from archkeel.check.evaluation.rule_support import _forbidden_dependency_verdicts
from archkeel.check.evaluation.rules import rule_evaluation_facts, rule_subject_failures
from archkeel.ir.codec import contract_bytes, parse_contract
from archkeel.ir.model import DependencyTargetKind, module_references
from archkeel.ir.profiles import PYTHON
from archkeel.ir.widening import contract_widening_changes

ROOT = Path(__file__).parents[1]


def _namespace_contract(**fields):
    raw = _contract(target_kind="import_namespace", **fields)
    raw["schema_version"] = "3.5.0"
    raw["rules"][0]["target"] = "sample.retired"
    return raw


def test_namespace_policy_requires_only_real_source_subjects():
    contract = parse_contract(_namespace_contract())
    assert not rule_subject_failures(contract.rules, {"sample.caller"}, type_shapes={})
    [target] = [
        reference
        for reference in module_references(contract)
        if reference.pointer == "/rules/0/target"
    ]
    assert target.value == "sample.retired" and not target.held
    [receipt] = rule_evaluation_facts(
        contract,
        profile=PYTHON,
        scope="root",
        modules=[_module("sample.caller")],
        source_modules=None,
        blank_modules=frozenset(),
        receipt_scope_complete=True,
    )
    assert receipt["subjects"] == ["sample.caller"]


def test_namespace_policy_does_not_certify_absent_exact_source():
    contract = parse_contract(_namespace_contract(source_match="exact"))
    [failure] = rule_subject_failures(contract.rules, {"sample.caller.child"}, type_shapes={})
    assert failure["data"]["missing"] == ["source"]
    assert not rule_evaluation_facts(
        contract,
        profile=PYTHON,
        scope="root",
        modules=[_module("sample.caller.child")],
        source_modules=None,
        blank_modules=frozenset(),
        receipt_scope_complete=True,
    )


def test_import_name_selection_does_not_expand_component_ownership():
    raw = _namespace_contract()
    raw["rules"][0]["target"] = "sample.errors"
    contract = parse_contract(raw)
    imports = [
        _import("sample.caller", "sample.errors"),
        _import("sample.caller.child", "sample.errors.child"),
        _import("sample.caller_extra", "sample.errors"),
        _import("sample.caller", "sample.errors_extra"),
    ]
    assert (
        len(list(_forbidden_dependency_verdicts(imports, contract.rules, _ownership(contract))))
        == 2
    )


def test_new_intent_roundtrips_and_is_visible_in_declarations():
    contract = parse_contract(_namespace_contract())
    encoded = json.loads(contract_bytes(contract))
    assert encoded["rules"][0]["target_kind"] == "import_namespace"
    assert parse_contract(encoded) == contract
    schema = json.loads((ROOT / "schema/architecture-contract-3.5.schema.json").read_bytes())
    assert Draft202012Validator(schema).is_valid(encoded)
    assert project_rule_declaration(contract.rules[0])["data"]["target_kind"] == "import_namespace"
    ordinary = replace(
        contract, rules=(replace(contract.rules[0], target_kind=DependencyTargetKind.MODULE),)
    )
    assert "target_kind" not in json.loads(contract_bytes(ordinary))["rules"][0]
    assert any(
        change.field == "target_kind" for change in contract_widening_changes(ordinary, contract)
    )
    assert contract_widening_changes(contract, ordinary) == ()


@pytest.mark.parametrize("value", (None, False, "absent", "", 1))
def test_target_kind_grammar_is_strict(value):
    raw = _namespace_contract()
    raw["rules"][0]["target_kind"] = value
    with pytest.raises(ValueError):
        parse_contract(raw)


@pytest.mark.parametrize(
    "version", ("2.1.0", "2.2.0", "2.3.0", "3.0.0", "3.1.0", "3.2.0", "3.3.0", "3.4.0")
)
def test_older_contracts_reject_the_new_intent(version):
    raw = _namespace_contract()
    raw["schema_version"] = version
    with pytest.raises(ValueError, match="3.5.0"):
        parse_contract(raw)


def _observe_namespace(root, body, *, mounted=False, ordinary=False, **selectors):
    from test_exact_module_ownership import _observe_tree

    contract = _namespace_contract(**selectors)
    if ordinary:
        del contract["rules"][0]["target_kind"]
    for component in contract["components"]:
        component["packages"] = component["packages"][:1]
    files = {
        "sample/__init__.py": "",
        "sample/caller/__init__.py": body,
        "sample/caller/child.py": "",
        "sample/errors/__init__.py": "",
        "sample/errors/base.py": "",
    }
    if mounted:
        files["inside.json"] = json.dumps(contract)
        outer = _namespace_contract()
        outer["components"] = [
            {
                **outer["components"][0],
                "id": "all",
                "label": "all",
                "packages": ["sample"],
                "inside": "inside.json",
            }
        ]
        outer["rules"] = []
        contract = outer
    return _observe_tree(root, files, contract)


@pytest.mark.parametrize("mounted", (False, True))
@pytest.mark.parametrize(
    "body,status",
    [
        ("", "PASS"),
        ("import sample.retired.tasks\n", "FAIL"),
        ("from ..retired import tasks\n", "FAIL"),
    ],
)
def test_native_absent_namespace_has_proven_verdicts(tmp_path, mounted, body, status):
    from archkeel.ir.decisions import rule_assessments

    result = _observe_namespace(tmp_path, body, mounted=mounted)
    assert result.observation is not None, result.diagnostics
    observation = result.observation
    assert observation.coverage.status == "PASS", observation.coverage.failures
    identity = "all:NO-AGGREGATE" if mounted else "NO-AGGREGATE"
    [row] = [
        row for row in rule_assessments(observation, undecided_by_rule={}) if row.id == identity
    ]
    assert row.status == status and row.evaluation_proven
    assert not (tmp_path / "sample/retired").exists()


def test_native_ordinary_missing_target_remains_unknown(tmp_path):
    from archkeel.ir.decisions import rule_assessments

    result = _observe_namespace(tmp_path, "", ordinary=True)
    assert result.observation is not None, result.diagnostics
    [row] = rule_assessments(result.observation, undecided_by_rule={})
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    assert any(item.kind == "rule_without_subjects" for item in result.diagnostics)


def test_native_source_parse_gap_cannot_pass_namespace_policy(tmp_path):
    from archkeel.ir.decisions import rule_assessments

    result = _observe_namespace(tmp_path, "def broken(:\n")
    assert result.observation is not None, result.diagnostics
    [row] = rule_assessments(result.observation, undecided_by_rule={})
    assert row.status == "UNKNOWN" and not row.evaluation_proven


@pytest.mark.parametrize("match,status", [("prefix", "FAIL"), ("exact", "PASS")])
def test_native_absent_namespace_respects_exact_target_selection(tmp_path, match, status):
    from archkeel.ir.decisions import rule_assessments

    result = _observe_namespace(tmp_path, "import sample.retired.tasks\n", target_match=match)
    assert result.observation is not None, result.diagnostics
    [row] = rule_assessments(result.observation, undecided_by_rule={})
    assert row.status == status and row.evaluation_proven
