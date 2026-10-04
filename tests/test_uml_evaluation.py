# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Core UML findings use the existing rule/fact/source evidence chain."""

import json
from dataclasses import asdict, replace

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.check.uml import assemble_uml
from archkeel.check.uml_evaluation import evaluate_uml
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation, parse_record, value_bytes
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.model import EvidenceClass
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations, validate_evidence_classes


def _contract():
    context = {"presence": "planned", "language": "python", "provenance": ["docs/target.md"]}
    return {
        "schema_version": "2.2.0",
        "components": [
            {
                "id": "core",
                "label": "core",
                "role": "component",
                "packages": ["sample.core"],
                "namespace": "sample.core",
                "responsibilities": ["Own operations."],
                "forbidden_responsibilities": [],
                "provenance": ["docs/target.md"],
            }
        ],
        "rules": [],
        "declarations": {
            "uml": {
                "schema_version": "1.0.0",
                "entities": [
                    {
                        **context,
                        "id": "module",
                        "kind": "module",
                        "qualified_name": "sample.core",
                        "parent_id": "core",
                        "responsibilities": ["Own the module."],
                    },
                    {
                        **context,
                        "id": "run",
                        "kind": "function",
                        "qualified_name": "sample.core.run",
                        "parent_id": "module",
                        "responsibilities": ["Delegate a request."],
                        "visibility": {"kind": "public", "basis": "declared"},
                        "signature": {
                            "parameters": [
                                {"name": "value", "kind": "positional", "default_known": True}
                            ]
                        },
                    },
                    {
                        **context,
                        "id": "helper",
                        "kind": "function",
                        "qualified_name": "sample.core.helper",
                        "parent_id": "module",
                        "responsibilities": ["Return a value."],
                    },
                ],
                "relationships": [
                    {
                        "id": "call",
                        "kind": "calls",
                        "source_id": "run",
                        "target_id": "helper",
                        "provenance": ["docs/target.md"],
                    }
                ],
            }
        },
    }


def _repository(tmp_path, *, contract=None, source=None):
    root = _prepare_repo(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": source
            or (
                "def helper(value):\n    return value\n"
                "\ndef run(value):\n    return helper(value)\n"
            ),
            "contract.json": json.dumps(contract or _contract()),
            "docs/target.md": "Own the module and delegate run to helper.\n",
        },
    )
    return root, ScanConfig(("sample",), "sample", "contract.json", "0" * 64)


def _model(root, config):
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert result.exit_code == 0 and encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    validate_evidence_classes(model)
    return model


def _uml_rule(model):
    return next(
        row for row in rule_assessments(model, undecided_by_rule={}) if row.kind == "uml_target"
    )


def test_core_report_evaluates_known_intent_and_retains_typed_assessments(tmp_path):
    root, config = _repository(tmp_path)
    model = _model(root, config)
    rule = _uml_rule(model)
    assert rule.status == "PASS" and rule.evaluation_proven
    receipt = next(
        item for item in model.records("scope_observations") if item.rule_ids == (rule.id,)
    )
    assert receipt.kind == "rule_evaluation" and receipt.data.get("assessment_complete") is True
    assert receipt.data.get("comparison") is not None
    assert receipt.fact_ids and receipt.evidence_ids
    assert not any(item.kind == "uml_assessment_unavailable" for item in model.records("unknowns"))


@pytest.mark.parametrize("change", ["visibility", "signature", "call"])
def test_known_intent_conflicts_are_trace_valid_violations_and_report_filterable(tmp_path, change):
    contract = _contract()
    run = contract["declarations"]["uml"]["entities"][1]
    source = None
    if change == "visibility":
        run["visibility"]["kind"] = "private"
    elif change == "signature":
        run["signature"]["parameters"][0]["name"] = "request"
    else:
        source = "def helper(value):\n    return value\n\ndef run(value):\n    return value\n"
    root, config = _repository(tmp_path, contract=contract, source=source)
    model = _model(root, config)
    rule = _uml_rule(model)
    assert rule.status == "FAIL"
    violations = [item for item in trace_valid_violations(model) if item.rule_ids == (rule.id,)]
    assert violations and {item.evidence_class for item in violations} == {EvidenceClass.VIOLATION}
    filtered, _ = run_report(
        root,
        config=config,
        analyzer=observe,
        only_violations=True,
        rule=rule.id,
    )
    assert filtered.exit_code == 0 and filtered.filtered_violations


def test_unresolved_calls_leave_rule_assessment_unknown_without_fake_pass(tmp_path):
    root, config = _repository(
        tmp_path,
        source=(
            "def helper(value):\n    return value\n\ndef run(value):\n    return unknown(value)\n"
        ),
    )
    model = _model(root, config)
    rule = _uml_rule(model)
    assert rule.status == "UNKNOWN" and not rule.evaluation_proven
    assert any(
        item.kind == "uml_conformance" and item.rule_ids == (rule.id,)
        for item in model.records("unknowns")
    )
    assert not any(item.rule_ids == (rule.id,) for item in model.records("violations"))


def test_core_evaluation_and_authenticated_reassembly_are_idempotent(tmp_path):
    root, config = _repository(tmp_path)
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    evaluated = evaluate_uml(assemble_uml(original, root, config.contract))
    assert evaluate_uml(assemble_uml(evaluated, root, config.contract)) == evaluated


def test_core_refuses_conflicting_receipt_from_adapter_output(tmp_path):
    root, config = _repository(tmp_path)
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    evaluated = evaluate_uml(assemble_uml(original, root, config.contract))
    model = evaluated.observation
    assert model is not None
    sections = tuple(
        replace(
            section,
            records=tuple(
                replace(record, title="Forged")
                if record.data.get("comparison") is not None
                else record
                for record in section.records
            ),
        )
        for section in model.sections
    )
    forged = replace(evaluated, observation=replace(model, sections=sections))
    result = evaluate_uml(forged)
    assert result.diagnostics and "conflicts" in result.diagnostics[0].unknown_claim


@pytest.mark.parametrize("version", ["2.1.0", "2.2.0"])
def test_adapter_cannot_invent_uml_intent_absent_from_the_authenticated_contract(tmp_path, version):
    root, config = _repository(tmp_path)
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assembled = assemble_uml(original, root, config.contract)
    intent = next(
        record
        for record in assembled.observation.records("declarations")
        if record.kind == "uml_target"
    )
    contract = _contract()
    del contract["declarations"]["uml"]
    contract["schema_version"] = version
    (root / config.contract).write_text(json.dumps(contract))
    fresh = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    model = fresh.observation
    sections = tuple(
        replace(section, records=(*section.records, intent))
        if section.name == "declarations"
        else section
        for section in model.sections
    )
    injected = replace(fresh, observation=replace(model, sections=sections))
    result = assemble_uml(injected, root, config.contract)
    assert result.diagnostics and "authenticated" in result.diagnostics[0].unknown_claim


def test_adapter_cannot_add_a_second_uml_target_beside_the_authenticated_one(tmp_path):
    root, config = _repository(tmp_path)
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assembled = assemble_uml(original, root, config.contract)
    model = assembled.observation
    intent = next(record for record in model.records("declarations") if record.kind == "uml_target")
    sections = tuple(
        replace(section, records=(*section.records, replace(intent, id="invented")))
        if section.name == "declarations"
        else section
        for section in model.sections
    )
    injected = replace(assembled, observation=replace(model, sections=sections))
    result = assemble_uml(injected, root, config.contract)
    assert result.diagnostics and "authenticated" in result.diagnostics[0].unknown_claim


def test_dart_directive_profile_does_not_claim_python_uml_capabilities(tmp_path):
    contract = _contract()
    for entity in contract["declarations"]["uml"]["entities"]:
        entity["language"] = "dart"
    root = _prepare_repo(
        tmp_path,
        {
            "lib/core.dart": (
                "int helper(int value) => value;\nint run(int value) => helper(value);\n"
            ),
            "contract.json": json.dumps(contract),
            "docs/target.md": "The directive profile cannot observe operations.\n",
        },
    )
    config = ScanConfig(("lib",), "sample", "contract.json", "0" * 64, language="dart")
    model = _model(root, config)
    rule = _uml_rule(model)
    assert rule.status == "UNKNOWN" and not rule.evaluation_proven
    assert any(record.rule_ids == (rule.id,) for record in model.records("unknowns"))
    assert not any(record.rule_ids == (rule.id,) for record in model.records("violations"))


def test_empty_explicit_target_records_unknown_instead_of_a_pass_receipt(tmp_path):
    contract = _contract()
    contract["declarations"]["uml"] = {"schema_version": "1.0.0"}
    root, config = _repository(tmp_path, contract=contract)
    rule = _uml_rule(_model(root, config))
    assert rule.status == "UNKNOWN" and not rule.evaluation_proven


@pytest.mark.parametrize("keep_canonical", [True, False])
def test_alternate_uml_receipt_cannot_replace_the_core_comparison(tmp_path, keep_canonical):
    root, config = _repository(tmp_path)
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    evaluated = evaluate_uml(assemble_uml(original, root, config.contract))
    model = evaluated.observation
    assert model is not None and not evaluated.diagnostics
    expected = architecture_report(model).comparison
    assert expected is not None and expected.status == "PASS"
    receipt = next(
        record
        for record in model.records("scope_observations")
        if record.data.get("comparison") is not None
    )
    forged_data = json.loads(value_bytes(receipt.data))
    forged_data["comparison"]["status"] = "FAIL"
    forged_data["comparison"]["assessments"][0]["status"] = "FAIL"
    forged_data["comparison"]["assessments"][0]["reason"] = "Injected alternate receipt"
    forged_wire = json.loads(json.dumps(asdict(receipt)))
    forged_wire.update(id="FORGED-OTHER-UML-RECEIPT", data=forged_data)
    forged = parse_record(forged_wire)
    sections = tuple(
        replace(
            section,
            records=(
                forged,
                *(
                    record
                    for record in section.records
                    if keep_canonical or record.id != receipt.id
                ),
            ),
        )
        if section.name == "scope_observations"
        else section
        for section in model.sections
    )
    tampered = replace(model, sections=sections)
    validate_evidence_classes(tampered)
    report = architecture_report(tampered)
    assert report.comparison == (expected if keep_canonical else None)
    rejected = evaluate_uml(replace(evaluated, observation=tampered))
    assert rejected.diagnostics and "conflicts" in rejected.diagnostics[0].unknown_claim
