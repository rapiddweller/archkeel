# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A versioned native rule evaluates bounded modulo operand proofs."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from test_analyzer import _component
from test_architecture_demo import _prepare_repo

from archkeel.check.evaluation.rules import profile_failures
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report, run_saved_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import (
    canonical_report_bytes,
    contract_bytes,
    decode_canonical_model,
    parse_contract,
    parse_observation,
)
from archkeel.ir.codec_observation import observation_payload
from archkeel.ir.decisions import rule_assessments, unknown_positions_by_rule
from archkeel.ir.facts import RecordData
from archkeel.ir.model import SCHEMA_VERSION
from archkeel.ir.profiles import DART, TYPESCRIPT
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]

RULE = {
    "kind": "bounded_numeric_operand",
    "source": "sample.core",
    "form": "both",
    "terminal_suffix": "nonce",
    "minimum_value": 4_294_967_296,
}


@pytest.mark.parametrize("profile", [DART, TYPESCRIPT])
def test_non_python_profiles_reject_python_numeric_operand_rule(profile):
    contract = parse_contract(
        {
            "schema_version": "3.8.0",
            "components": [_component("core")],
            "rules": [
                {
                    "id": "RULE",
                    "rationale": "Probe.",
                    "provenance": ["docs/architecture/sample.md"],
                    "decided_by": "architect",
                    **RULE,
                }
            ],
        }
    )
    failures = profile_failures(contract, profile, ())
    assert len(failures) == 1
    assert failures[0]["rule_ids"] == ["RULE"]
    assert "bounded_numeric_operand" in failures[0]["title"]


def _write_probe(
    tmp_path, *, source="sample.core", form="both", suffix="nonce", minimum=4, mounted=False
):
    contract = {
        "schema_version": "3.8.0",
        "components": [_component("core"), _component("cli")],
        "rules": [
            {
                "id": "RULE",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
                "kind": "bounded_numeric_operand",
                "source": source,
                "form": form,
                "terminal_suffix": suffix,
                "minimum_value": minimum,
            }
        ],
    }
    if mounted:
        (tmp_path / "inside.json").write_text(json.dumps(contract))
        contract = {
            "schema_version": "3.8.0",
            "components": [
                _component("core") | {"inside": "inside.json"},
                _component("cli"),
            ],
            "rules": [],
        }
        child = json.loads((tmp_path / "inside.json").read_bytes())
        child["components"] = [_component("core")]
        (tmp_path / "inside.json").write_text(json.dumps(child))
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample").mkdir(exist_ok=True)
    return tmp_path


def test_numeric_source_participates_in_reference_validation_and_rename(tmp_path):
    from archkeel.ir.model import module_references
    from archkeel.ir.renames import renamed_contract

    _write_probe(tmp_path)
    contract = parse_contract(json.loads((tmp_path / "contract.json").read_bytes()))
    reference = next(
        item for item in module_references(contract) if item.pointer == "/rules/0/source"
    )
    assert reference.value == "sample.core" and reference.held
    changed = renamed_contract(contract, {"sample.core": "sample.engine"})
    assert json.loads(contract_bytes(changed))["rules"][0]["source"] == "sample.engine"


@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize("exact", [False, True])
def test_mounted_numeric_receipt_replays_only_parent_physical_domain(tmp_path, columnar, exact):
    from test_exact_module_ownership import _observe_tree

    _write_probe(tmp_path, source="sample", mounted=True)
    contract = json.loads((tmp_path / "contract.json").read_bytes())
    if exact:
        contract["components"][0]["packages"] = []
        contract["components"][0]["exact_modules"] = ["sample.core"]
        child = json.loads((tmp_path / "inside.json").read_bytes())
        child["components"][0]["packages"] = []
        child["components"][0]["exact_modules"] = ["sample.core"]
        (tmp_path / "inside.json").write_text(json.dumps(child))
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": "def choose(job_nonce): return job_nonce % 4\n",
            "sample/cli.py": "def choose(job_nonce): return job_nonce % 1\n",
        },
        contract,
    )
    assert not result.diagnostics and result.observation is not None
    model = result.observation
    rows = rule_assessments(model, undecided_by_rule=unknown_positions_by_rule(model))
    assert len(rows) == 1 and rows[0].status == "PASS"
    receipt = next(
        item for item in model.records("scope_observations") if item.data.get("operation_binding")
    )
    assert receipt.subjects == ("sample.core",)
    saved = tmp_path / "mounted-positive.json"
    saved.write_bytes(
        canonical_report_bytes(model)
        if columnar
        else json.dumps(observation_payload(model)).encode()
    )
    replay = run_saved_report(saved)
    assert not replay.diagnostics and replay.rule_assessments == rows


def test_numeric_component_package_selector_evaluates_every_owned_package(tmp_path):
    from test_exact_module_ownership import _observe_tree

    _write_probe(tmp_path)
    contract = json.loads((tmp_path / "contract.json").read_bytes())
    contract["components"][0]["packages"] = ["sample.core", "sample.extra"]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": "def choose(job_nonce): return job_nonce % 4\n",
            "sample/extra.py": "def choose(job_nonce): return job_nonce % 1\n",
        },
        contract,
    )
    assert not result.diagnostics and result.observation is not None
    model = result.observation
    rows = rule_assessments(model, undecided_by_rule=unknown_positions_by_rule(model))
    assert len(rows) == 1 and rows[0].status == "FAIL" and rows[0].evaluation_proven
    assert len(trace_valid_violations(model)) == 1
    for content in (
        canonical_report_bytes(model),
        json.dumps(observation_payload(model)).encode(),
    ):
        saved = tmp_path / "multiple-packages.json"
        saved.write_bytes(content)
        replay = run_saved_report(saved)
        assert not replay.diagnostics and replay.rule_assessments == rows


def test_numeric_rule_subjects_use_expanded_component_package_domain(tmp_path):
    from test_exact_module_ownership import _observe_tree

    _write_probe(tmp_path)
    contract = json.loads((tmp_path / "contract.json").read_bytes())
    contract["components"][0]["packages"] = ["sample.core", "sample.extra"]
    result = _observe_tree(
        tmp_path,
        {"sample/extra.py": "def unrelated(value): return value\n"},
        contract,
    )
    assert not result.diagnostics and result.observation is not None
    assert not any(
        row.kind == "rule-without-subjects" and "RULE" in row.rule_ids
        for row in result.observation.records("unknowns")
    )


@pytest.mark.parametrize("known_failure", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_mounted_numeric_unknowns_remain_undecided_on_replay(tmp_path, known_failure, columnar):
    from test_exact_module_ownership import _observe_tree

    _write_probe(tmp_path, mounted=True)
    contract = json.loads((tmp_path / "contract.json").read_bytes())
    body = "    small = job_nonce % 1\n" if known_failure else ""
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": (
                "def choose(job_nonce, dynamic):\n" + body + "    return job_nonce % dynamic\n"
            ),
        },
        contract,
    )
    assert not result.diagnostics and result.observation is not None
    model = result.observation
    rows = rule_assessments(model, undecided_by_rule=unknown_positions_by_rule(model))
    assert len(rows) == 1
    assert rows[0].status == ("FAIL" if known_failure else "UNKNOWN")
    assert rows[0].undecided == 1
    assert any(item.kind == "numeric_operand_unknown" for item in model.records("unknowns"))
    assert not any(
        item.kind == "numeric_operand_unknown" for item in model.records("typing_signals")
    )
    saved = tmp_path / "mounted.json"
    saved.write_bytes(
        canonical_report_bytes(model)
        if columnar
        else json.dumps(observation_payload(model)).encode()
    )
    replay = run_saved_report(saved)
    assert not replay.diagnostics
    assert replay.rule_assessments == rows


@pytest.mark.parametrize(
    ("operand", "expected"),
    [("3", "FAIL"), ("4", "PASS"), ("2**8", "PASS"), ("dynamic", "UNKNOWN")],
)
def test_complete_numeric_report_replays_with_one_receipt(tmp_path, operand, expected):
    from test_exact_module_ownership import _observe_tree

    _write_probe(tmp_path)
    contract = json.loads((tmp_path / "contract.json").read_bytes())
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": f"def choose(job_nonce, dynamic): return job_nonce % {operand}\n",
        },
        contract,
    )
    assert not result.diagnostics and result.observation is not None
    model = result.observation
    rows = rule_assessments(model, undecided_by_rule=unknown_positions_by_rule(model))
    assert len(rows) == 1 and rows[0].status == expected
    receipts = [
        record
        for record in model.records("scope_observations")
        if record.kind == "rule_evaluation" and record.rule_ids == ("RULE",)
    ]
    assert len(receipts) == 1
    for content in (
        canonical_report_bytes(model),
        json.dumps(observation_payload(model)).encode(),
    ):
        saved = tmp_path / "numeric.json"
        saved.write_bytes(content)
        replayed = run_saved_report(saved)
        assert not replayed.diagnostics
        assert replayed.rule_assessments == rows


def test_numeric_contract_roundtrips_only_under_its_versioned_schema():
    contract = {
        "schema_version": "3.8.0",
        "components": [],
        "rules": [
            {
                "id": "RULE",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
                **RULE,
            }
        ],
    }
    schema = json.loads((ROOT / "schema/architecture-contract-3.8.schema.json").read_bytes())
    Draft202012Validator(schema).validate(contract)
    parsed = parse_contract(contract)
    assert parse_contract(json.loads(contract_bytes(parsed))) == parsed
    legacy = {**contract, "schema_version": "3.7.0"}
    with pytest.raises(ValueError, match="3.8.0"):
        parse_contract(legacy)


def test_saved_numeric_receipt_rejects_changed_operand_proof(tmp_path):
    contract = {
        "schema_version": "3.8.0",
        "components": [_component("core"), _component("cli")],
        "rules": [
            {
                "id": "RULE",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
                **RULE,
            }
        ],
    }
    fixture = tmp_path / "base"
    fixture.mkdir()
    root = _prepare_repo(
        tmp_path,
        {
            "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
            "contract.json": json.dumps(contract),
            "sample/core.py": (
                "WIDTH = 2**64\ndef choose(job_nonce):\n    return job_nonce % WIDTH\n"
            ),
        },
        fixture=fixture,
    )
    config = ScanConfig((".",), "sample", "contract.json", "0" * 64)
    live, packet = run_report(root, config=config, analyzer=observe, only_architecture=True)
    assert packet is not None and live.declared_rules == "PASS"
    saved = tmp_path / "saved.json"
    observation = parse_observation(decode_canonical_model(json.loads(packet)))
    payload = observation_payload(observation)
    schemas = Path(__file__).parents[1] / "schema"
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema))
        for schema in (json.loads(path.read_bytes()) for path in schemas.glob("*.json"))
        if "$id" in schema
    )
    unknown_field = json.loads(json.dumps(payload))
    unknown_field["constructs"][0]["data"]["unsupported_numeric_proof"] = True
    for profile in ("python-decoded", "decoded"):
        current_validator = Draft202012Validator(
            {"$ref": f"urn:archkeel:architecture-ir:{profile}:{SCHEMA_VERSION}"},
            registry=registry,
        )
        assert current_validator.is_valid(payload), [
            (error.json_path, error.message) for error in current_validator.iter_errors(payload)
        ]
        assert not current_validator.is_valid(unknown_field)
    assert not Draft202012Validator(
        {"$ref": "urn:archkeel:architecture-ir:python-decoded:2.1.0"}, registry=registry
    ).is_valid(payload)
    old_version = {k: v for k, v in payload.items() if k != "producer_kind"}
    old_version["schema_version"] = "2.1.0"
    with pytest.raises(ValueError, match="numeric_operand constructs require.*2.2.0"):
        parse_observation(old_version)
    with pytest.raises(ValueError, match="numeric_operand constructs require.*2.2.0"):
        observation_payload(replace(observation, schema_version="2.1.0", producer_kind=None))
    (tmp_path / "accepted-report.json").write_bytes(canonical_report_bytes(observation))
    for mutation in (
        "operand",
        "derivation",
        "threshold",
        "transplant",
        "source_digest",
        "contract_digest",
        "scope",
        "schema_relabel",
        "ownership",
    ):
        sections = []
        for section in observation.sections:
            records = []
            for record in section.records:
                if section.name == "constructs" and record.kind == "numeric_operand":
                    entries = list(record.data.entries)
                    if mutation == "operand":
                        entries = [(key, 17 if key == "value" else value) for key, value in entries]
                    elif mutation == "derivation":
                        entries = [
                            (
                                key,
                                tuple(
                                    RecordData(
                                        tuple(
                                            (name, "17" if name == "expression" else field)
                                            for name, field in origin.entries
                                        )
                                    )
                                    if isinstance(origin, RecordData)
                                    else origin
                                    for origin in value
                                )
                                if key == "derivation"
                                else value,
                            )
                            for key, value in entries
                        ]
                    record = replace(record, data=RecordData(tuple(entries)))
                elif mutation == "ownership" and record.kind == "component_responsibility":
                    record = replace(record, title="changed-owner")
                elif section.name == "scope_observations" and record.kind == "rule_evaluation":
                    entries = tuple(
                        (key, 0 if mutation == "threshold" and key == "threshold" else value)
                        for key, value in record.data.entries
                    )
                    subjects = (
                        ("sample.other",)
                        if mutation == "transplant" and record.rule_ids
                        else record.subjects
                    )
                    record = replace(record, data=RecordData(entries), subjects=subjects)
                records.append(record)
            sections.append(replace(section, records=tuple(records)))
        tampered = replace(observation, sections=tuple(sections))
        if mutation == "source_digest":
            tampered = replace(tampered, source=replace(tampered.source, source_digest="0" * 64))
        elif mutation == "contract_digest":
            tampered = replace(tampered, contract=replace(tampered.contract, digest="0" * 64))
        elif mutation in {"scope", "schema_relabel"}:
            altered = []
            for section in tampered.sections:
                records = []
                for record in section.records:
                    proof = record.data.get("numeric_scope_proof")
                    if record.kind == "rule_evaluation" and isinstance(proof, RecordData):
                        entries = tuple(
                            (
                                key,
                                "other-mount"
                                if mutation == "scope" and key == "scope"
                                else "1.2.0"
                                if mutation == "schema_relabel"
                                and key == "observation_schema_version"
                                else value,
                            )
                            for key, value in proof.entries
                        )
                        record = replace(
                            record,
                            data=RecordData(
                                tuple(
                                    (
                                        key,
                                        RecordData(entries)
                                        if key == "numeric_scope_proof"
                                        else value,
                                    )
                                    for key, value in record.data.entries
                                )
                            ),
                        )
                    records.append(record)
                altered.append(replace(section, records=tuple(records)))
            tampered = replace(tampered, sections=tuple(altered))
        saved.write_bytes(canonical_report_bytes(tampered))
        replay = run_saved_report(saved, only_architecture=True)
        assert replay.declared_rules == "UNKNOWN", (mutation, replay.rule_assessments)
