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
from test_analyzer import _component, _observe
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


def test_numeric_rule_keeps_known_violation_and_unknown_operand(tmp_path):
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
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(
        "def choose(job_nonce, dynamic):\n    small = job_nonce % 16\n"
        "    odd = job_nonce % dynamic\n    return small, odd\n"
    )
    result = _observe(tmp_path)
    assert result.diagnostics == () and result.observation is not None
    assert [(row.kind, row.rule_ids) for row in trace_valid_violations(result.observation)] == [
        ("bounded_numeric_operand", ("RULE",))
    ]
    assert [
        row.kind for row in result.observation.records("unknowns") if "RULE" in row.rule_ids
    ] == ["numeric_operand_unknown"]
    assessment = result.observation.records("scope_observations")
    numeric_receipt = next(item for item in assessment if item.data.get("operation_binding"))
    assert numeric_receipt.data.get("threshold") == 4_294_967_296
    assert numeric_receipt.data.get("terminal_suffix") == "nonce"
    assert len(numeric_receipt.fact_ids) == 2
    proof = numeric_receipt.data.get("numeric_scope_proof")
    assert isinstance(proof, RecordData)
    assert proof.get("source_digest") == result.observation.source.source_digest
    assert proof.get("source_scope") == result.observation.source.scope
    assert proof.get("contract_digest") == result.observation.contract.digest
    assert proof.get("observation_schema_version") == result.observation.schema_version
    assert proof.get("scope") == numeric_receipt.data.get("scope")
    assert proof.get("selected_files") == ("sample/core.py",)
    assert set(proof.get("operation_ids")) == set(numeric_receipt.fact_ids)
    rows = rule_assessments(
        result.observation,
        undecided_by_rule=unknown_positions_by_rule(result.observation),
    )
    assert rows[0].status == "FAIL" and rows[0].undecided == 1 and rows[0].evaluation_proven


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


def _rule_rows(tmp_path):
    result = _observe(tmp_path)
    assert result.diagnostics == () and result.observation is not None
    return result.observation, rule_assessments(
        result.observation,
        undecided_by_rule=unknown_positions_by_rule(result.observation),
    )


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


@pytest.mark.parametrize(
    "other",
    [
        "assert True\n",
        "try:\n    value = 1\nexcept Exception:\n    value = 2\n",
        "def placeholder(): pass\n",
        "def label(value): return value == 'fixed'\n",
    ],
)
def test_numeric_rule_skips_other_construct_kinds(tmp_path, other):
    _write_probe(tmp_path)
    (tmp_path / "sample/core.py").write_text(
        other + "def choose(job_nonce): return job_nonce % 4\n"
    )
    _, rows = _rule_rows(tmp_path)
    assert rows[0].status == "PASS"


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


@pytest.mark.parametrize("version", ["1.3.0", "2.0.0", "2.1.0"])
def test_legacy_reader_rejects_numeric_kind_without_derivation(tmp_path, version):
    _write_probe(tmp_path)
    (tmp_path / "sample/core.py").write_text("def choose(job_nonce): return job_nonce % 4\n")
    model, _ = _rule_rows(tmp_path)
    raw = observation_payload(model)
    raw["schema_version"] = version
    for item in raw["constructs"]:
        if item["kind"] == "numeric_operand":
            item["data"].pop("derivation", None)
    with pytest.raises(ValueError, match="numeric_operand constructs require"):
        parse_observation(raw)


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


@pytest.mark.parametrize(
    ("value", "status"),
    [(4_294_967_295, "FAIL"), (4_294_967_296, "PASS"), (4_294_967_297, "PASS")],
)
def test_minimum_threshold_boundary(tmp_path, value, status):
    _write_probe(tmp_path, minimum=4_294_967_296)
    (tmp_path / "sample/core.py").write_text(f"def choose(job_nonce): return job_nonce % {value}\n")
    _, rows = _rule_rows(tmp_path)
    assert rows[0].status == status


def test_selector_matches_both_forms_terminal_name_and_case(tmp_path):
    _write_probe(tmp_path, form="augmented")
    (tmp_path / "sample/core.py").write_text(
        "def choose(job_nonce, JOB_NONCE, state):\n"
        "    a = job_nonce % 1\n"
        "    b = state.job_nonce % 1\n"
        "    JOB_NONCE %= 1\n"
        "    job_nonce %= 1\n"
        "    return a, b\n"
    )
    observation, rows = _rule_rows(tmp_path)
    assert rows[0].status == "FAIL"
    assert len(trace_valid_violations(observation)) == 1
    assert len(trace_valid_violations(observation)[0].fact_ids) == 1


def test_selector_suffix_is_contract_owned_case_sensitive_and_matches_attributes(tmp_path):
    _write_probe(tmp_path, form="both", suffix="count", minimum=2)
    (tmp_path / "sample/core.py").write_text(
        "def choose(job_count, job_Count, state):\n"
        "    a = job_count % 1\n"
        "    b = state.job_count % 1\n"
        "    c = job_Count % 1\n"
        "    return a, b, c\n"
    )
    observation, rows = _rule_rows(tmp_path)
    assert rows[0].status == "FAIL"
    violations = trace_valid_violations(observation)
    assert len(violations) == 2
    operations = {
        item.id: item
        for item in observation.records("constructs")
        if item.kind == "numeric_operand"
    }
    assert {
        operations[fact_id].data.get("subject") for item in violations for fact_id in item.fact_ids
    } == {"job_count"}


def test_boolean_unary_power_and_chained_alias_proofs(tmp_path):
    _write_probe(tmp_path, minimum=2)
    (tmp_path / "sample/core.py").write_text(
        "BASE = 2\nCHAIN = BASE ** 4\n"
        "def choose(job_nonce):\n"
        "    local = 4\n"
        "    local_value = job_nonce % local\n"
        "    a = job_nonce % False\n"
        "    zero = job_nonce % 0\n"
        "    b = job_nonce % +1\n"
        "    c = job_nonce % -1\n"
        "    d = job_nonce % CHAIN\n"
        "    e = job_nonce % BASE ** 2\n"
        "    true_value = job_nonce % True\n"
        "    return local_value, a, zero, b, c, d, e, true_value\n"
    )
    observation, rows = _rule_rows(tmp_path)
    ops = observation.records("constructs")
    numeric = sorted(
        (item for item in ops if item.kind == "numeric_operand"),
        key=lambda item: (item.data.get("line"), item.data.get("column")),
    )
    assert [item.data.get("value") for item in numeric] == [4, 0, 0, 1, -1, 16, 4, 1]
    assert [item.data.get("proof") for item in numeric] == ["known"] * 8
    assert numeric[0].data.get("derivation")[0].get("name") == "local"
    assert [item.get("name") for item in numeric[5].data.get("derivation")] == ["CHAIN", "BASE"]
    assert rows[0].status == "FAIL" and rows[0].undecided == 0


def test_cycle_and_late_alias_remain_unknown(tmp_path):
    _write_probe(tmp_path, minimum=1)
    (tmp_path / "sample/core.py").write_text(
        "def choose(job_nonce):\n"
        "    a = job_nonce % LATE\n"
        "    b = job_nonce % LEFT\n"
        "    return a, b\n"
        "LATE = 4\nLEFT = RIGHT\nRIGHT = LEFT\n"
    )
    observation, rows = _rule_rows(tmp_path)
    assert rows[0].status == "UNKNOWN"
    assert len([row for row in observation.records("unknowns") if row.rule_ids == ("RULE",)]) == 2


def test_empty_selected_source_never_passes(tmp_path):
    _write_probe(tmp_path)
    (tmp_path / "sample/core.py").write_text("")
    _, rows = _rule_rows(tmp_path)
    assert rows[0].status == "UNKNOWN"


@pytest.mark.parametrize("signal", ["declaration", "receipt"])
def test_legacy_observation_version_rejects_numeric_vocabulary_without_operations(tmp_path, signal):
    _write_probe(tmp_path)
    (tmp_path / "sample/core.py").write_text("")
    model, _ = _rule_rows(tmp_path)
    sections = tuple(
        replace(section, records=())
        if section.name == "constructs"
        else replace(
            section,
            records=tuple(
                record
                for record in section.records
                if not (
                    signal == "declaration"
                    and section.name == "scope_observations"
                    and record.data.get("numeric_scope_proof") is not None
                )
            ),
        )
        for section in model.sections
    )
    if signal == "receipt":
        sections = tuple(
            replace(section, records=()) if section.name == "declarations" else section
            for section in sections
        )
    downgraded = replace(model, schema_version="2.1.0", sections=sections)
    with pytest.raises(ValueError, match="numeric_operand.*2.2.0"):
        observation_payload(downgraded)
    raw = observation_payload(model)
    raw["schema_version"] = "2.1.0"
    raw["constructs"] = []
    if signal == "declaration":
        raw["scope_observations"] = [
            item for item in raw["scope_observations"] if "numeric_scope_proof" not in item["data"]
        ]
    else:
        raw["declarations"] = []
    with pytest.raises(ValueError, match="numeric_operand.*2.2.0"):
        parse_observation(raw)


def test_missing_selected_source_is_diagnosed_as_incomplete(tmp_path):
    _write_probe(tmp_path)
    result = _observe(tmp_path)
    assert result.observation is not None
    assert result.diagnostics
    assert any(
        "subject" in item.unknown_claim.lower() or "scope" in item.unknown_claim.lower()
        for item in result.diagnostics
    )


def test_source_selector_and_mount_limit_the_actual_operation_domain(tmp_path):
    _write_probe(tmp_path, source="sample.core", minimum=4, mounted=True)
    (tmp_path / "sample/core.py").write_text("def choose(job_nonce): return job_nonce % 1\n")
    (tmp_path / "sample/other.py").write_text("def choose(job_nonce): return job_nonce % 1\n")
    observation, rows = _rule_rows(tmp_path)
    assert rows[0].status == "FAIL"
    receipt = next(
        item
        for item in observation.records("scope_observations")
        if item.rule_ids
        and item.rule_ids[0].endswith(":RULE")
        and item.data.get("operation_binding") is not None
    )
    assert receipt.subjects == ("sample.core",)
    assert receipt.fact_ids == tuple(
        item.id
        for item in observation.records("constructs")
        if item.kind == "numeric_operand" and item.data.get("module") == "sample.core"
    )


def test_nested_modulo_facts_keep_distinct_complete_spans(tmp_path):
    _write_probe(tmp_path, minimum=2)
    (tmp_path / "sample/core.py").write_text(
        "def choose(job_nonce): return job_nonce % (other_nonce % 1)\n"
    )
    observation, _ = _rule_rows(tmp_path)
    operations = sorted(
        (item for item in observation.records("constructs") if item.kind == "numeric_operand"),
        key=lambda item: item.data.get("column"),
    )
    assert len(operations) == 2
    assert len({item.id for item in operations}) == 2
    assert [item.data.get("column") for item in operations] == [30, 43]
    assert all(item.data.get("end_column") > item.data.get("column") for item in operations)


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
    current_validator = Draft202012Validator(
        {"$ref": f"urn:archkeel:architecture-ir:python-decoded:{SCHEMA_VERSION}"},
        registry=registry,
    )
    assert current_validator.is_valid(payload), [
        (error.json_path, error.message) for error in current_validator.iter_errors(payload)
    ]
    assert not Draft202012Validator(
        {"$ref": "urn:archkeel:architecture-ir:python-decoded:2.1.0"}, registry=registry
    ).is_valid(payload)
    old_version = dict(payload)
    old_version["schema_version"] = "2.1.0"
    with pytest.raises(ValueError, match="numeric_operand constructs require.*2.2.0"):
        parse_observation(old_version)
    with pytest.raises(ValueError, match="numeric_operand constructs require.*2.2.0"):
        observation_payload(replace(observation, schema_version="2.1.0"))
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
