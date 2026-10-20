# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Construct selectors stay tied to a proven nominal receiver and one operand role."""

import ast
import copy
import json
import subprocess
from pathlib import Path

import pytest
from test_analyzer import _parsed_module

from archkeel.analyzer.python.constructs import collect_constructs
from archkeel.analyzer.python.resolve import build_symbol_index
from archkeel.analyzer.python.symbols import collect_symbols
from archkeel.check.evaluation.rules import _construct_violations
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report, run_saved_report
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import ArchitectureRuleKind, DecisionMaker
from archkeel.ir.codec import (
    canonical_json_bytes,
    decode_canonical_model,
    encode_canonical_model,
    observation_payload,
    parse_observation,
)
from archkeel.ir.codec_contract import parse_contract
from archkeel.ir.facts import Evidence, Record, call_binding
from archkeel.ir.facts_codec import parse_evidence, parse_record
from archkeel.ir.facts_validation import (
    _selector_evidence_excerpt,
    _selector_receiver_site_matches,
)
from archkeel.ir.model import ConstructSelector, ConstructSelectorRole, ForbiddenConstructRule
from archkeel.ir.trace import trace_valid_violations


def test_selector_grammar_is_closed_and_requires_role_specific_fields():
    raw = {
        "schema_version": "3.11.0",
        "components": [],
        "rules": [
            {
                "id": "SELECT",
                "kind": "forbidden_construct",
                "source": "sample",
                "constructs": ["string_literal_compare"],
                "selector": {
                    "receiver": "sample.Connection",
                    "member": "backend",
                    "role": "equality",
                    "literal": "flat",
                },
                "rationale": "Route through the declared port.",
                "provenance": ["contract.json"],
                "decided_by": "architect",
            }
        ],
    }
    rule = parse_contract(raw).rules[0]
    assert isinstance(rule, ForbiddenConstructRule)
    assert rule.selector == ConstructSelector(
        "sample.Connection", "backend", ConstructSelectorRole.EQUALITY, "flat"
    )
    raw["schema_version"] = "3.10.0"
    try:
        parse_contract(raw)
    except ValueError as error:
        assert "3.11.0" in str(error)
    else:
        raise AssertionError("older contract version accepted a construct selector")


def test_selected_scope_without_applicable_facts_is_unknown():
    rule = ForbiddenConstructRule(
        "SELECT",
        ArchitectureRuleKind.FORBIDDEN_CONSTRUCT,
        "sample.core",
        (),
        "Keep the selected port protected.",
        ("test",),
        DecisionMaker.ARCHITECT,
        selector=ConstructSelector(
            "sample.core.Connection", "password", ConstructSelectorRole.READ
        ),
    )
    findings = _construct_violations([], [rule])
    assert len(findings) == 1
    assert findings[0]["evidence_class"] == "UNKNOWN"
    assert findings[0]["kind"] == "rule-without-selector-subject"


def test_bounded_selector_excerpt_supports_match_headers():
    evidence = Evidence("EVD-test", "sample/core.py", 4, 4, 4, "    match conn.backend:")
    parsed = _selector_evidence_excerpt(evidence, "match")
    assert parsed is not None
    roots, offset = parsed
    matches = [node for root in roots for node in ast.walk(root) if isinstance(node, ast.Match)]
    assert len(matches) == 1
    assert matches[0].subject.attr == "backend"
    assert offset == 1


@pytest.mark.parametrize(
    ("source", "role", "literal"),
    [
        (
            "class Connection: pass\nclass Label: pass\n"
            'def route(conn: Connection):\n    conn = Label()\n    conn.backend == "flat"\n',
            ConstructSelectorRole.EQUALITY,
            "flat",
        ),
        (
            "class Connection:\n    backend: str\n"
            "def route(conn: Connection):\n    match conn.backend:\n"
            "        case ['flat']:\n            pass\n",
            ConstructSelectorRole.MATCH,
            "flat",
        ),
    ],
)
def test_mutated_receivers_and_nested_match_patterns_stay_unknown(
    source: str, role: ConstructSelectorRole, literal: str
):
    signals = collect_constructs([_parsed_module(source, module="sample.core")], {})
    [selector] = [
        row
        for row in signals
        if row["kind"] == "construct_selector" and row["data"]["selector_role"] == role.value
    ]
    assert selector["data"]["status"] == "unknown"
    if role is ConstructSelectorRole.EQUALITY:
        assert selector["data"]["receiver_type"] is None
    else:
        assert selector["data"]["receiver_type"] == "sample.core.Connection"
    rule = ForbiddenConstructRule(
        "SELECT",
        ArchitectureRuleKind.FORBIDDEN_CONSTRUCT,
        "sample.core",
        (),
        "Keep the selected receiver proven.",
        ("test",),
        DecisionMaker.ARCHITECT,
        selector=ConstructSelector("sample.core.Connection", "backend", role, literal),
    )
    findings = _construct_violations(signals, [rule])
    assert not any(row["evidence_class"] == "VIOLATION" for row in findings)
    assert any(row["evidence_class"] == "UNKNOWN" for row in findings)


def test_ambiguous_string_predicate_does_not_disappear_beside_safe_literal():
    source = (
        'FLAT = "flat"\nclass Connection:\n    backend: str\n'
        "def route(conn: Connection, maybe):\n"
        '    conn.backend.startswith("wide")\n'
        "    maybe.backend.startswith(FLAT)\n"
    )
    signals = collect_constructs([_parsed_module(source, module="sample.core")], {})
    selected = [
        row
        for row in signals
        if row["kind"] == "construct_selector" and row["data"]["selector_role"] == "startswith"
    ]
    assert {row["data"]["literal"] for row in selected} == {"wide", "flat"}
    assert any(row["data"]["status"] == "unknown" for row in selected)
    rule = ForbiddenConstructRule(
        "SELECT",
        ArchitectureRuleKind.FORBIDDEN_CONSTRUCT,
        "sample.core",
        (),
        "Keep the selected receiver proven.",
        ("test",),
        DecisionMaker.ARCHITECT,
        selector=ConstructSelector(
            "sample.core.Connection", "backend", ConstructSelectorRole.STARTSWITH, "flat"
        ),
    )
    findings = _construct_violations(signals, [rule])
    assert not any(row["evidence_class"] == "VIOLATION" for row in findings)
    assert any(row["evidence_class"] == "UNKNOWN" for row in findings)


def test_collector_and_evaluator_select_member_and_literal_not_spellings():
    source = """
class Connection:
    password: str
    backend: str
class Label:
    password: str
    backend: str
def route(conn: Connection, label: Label, key: str, ambiguous):
    hasattr(conn, "password")
    getattr(label, "password")
    conn.password
    conn.backend == "flat"
    "flat" == conn.backend
    label.backend == "flat"
    getattr(conn, key)
    ambiguous.backend == "flat"
"""
    module = _parsed_module(source, module="sample.core")
    signals = collect_constructs([module], {})
    selector = ConstructSelector(
        "sample.core.Connection", "backend", ConstructSelectorRole.EQUALITY, "flat"
    )
    rule = ForbiddenConstructRule(
        "SELECT",
        ArchitectureRuleKind.FORBIDDEN_CONSTRUCT,
        "sample.core",
        (),
        "selected routing operand",
        ("test",),
        DecisionMaker.ARCHITECT,
        selector=selector,
    )
    findings = _construct_violations(signals, [rule])
    assert len([row for row in findings if row["evidence_class"] == "VIOLATION"]) == 2
    assert not any(row["data"].get("member") == "password" for row in findings)
    assert any(row["evidence_class"] == "UNKNOWN" for row in findings)
    safe_literal_signals = collect_constructs(
        [
            _parsed_module(
                "class Connection:\n    backend: str\n"
                'def f(conn: Connection):\n    conn.backend == "wide"\n',
                module="sample.core",
            )
        ],
        {},
    )
    assert _construct_violations(safe_literal_signals, [rule]) == []
    rows = [row for row in signals if row["kind"] == "construct_selector"]
    assert any(row["data"]["selector_role"] == "reflect" for row in rows)
    read_rule = ForbiddenConstructRule(
        "READ",
        ArchitectureRuleKind.FORBIDDEN_CONSTRUCT,
        "sample.core",
        (),
        "selected credential read",
        ("test",),
        DecisionMaker.ARCHITECT,
        selector=ConstructSelector(
            "sample.core.Connection", "password", ConstructSelectorRole.READ
        ),
    )
    read_findings = _construct_violations(signals, [read_rule])
    assert len([row for row in read_findings if row["evidence_class"] == "VIOLATION"]) == 1
    reflect_rule = ForbiddenConstructRule(
        "REFLECT",
        ArchitectureRuleKind.FORBIDDEN_CONSTRUCT,
        "sample.core",
        (),
        "selected credential probe",
        ("test",),
        DecisionMaker.ARCHITECT,
        selector=ConstructSelector(
            "sample.core.Connection", "password", ConstructSelectorRole.REFLECT
        ),
    )
    reflect_findings = _construct_violations(signals, [reflect_rule])
    assert len([row for row in reflect_findings if row["evidence_class"] == "VIOLATION"]) == 1
    assert any(row["evidence_class"] == "UNKNOWN" for row in reflect_findings)
    assert any(
        row["data"]["operation"] == "write"
        for row in collect_constructs(
            [
                _parsed_module(
                    "class Connection: pass\ndef f(conn: Connection):\n    conn.backend = 'x'\n",
                    module="sample.core",
                )
            ],
            {},
        )
    )


def test_selected_constructor_and_type_probe_are_separate_roles():
    module = _parsed_module(
        "class Connection: pass\n"
        "def build(value):\n"
        "    Connection()\n"
        "    isinstance(value, Connection)\n"
        "    issubclass(type(value), Connection)\n",
        module="sample.core",
    )
    facts = collect_constructs([module], {})
    assert sorted(
        row["data"]["selector_role"] for row in facts if row["kind"] == "construct_selector"
    ) == ["constructor", "type_probe", "type_probe"]


def test_direct_class_selector_binding_cannot_be_retargeted_to_another_class():
    module = _parsed_module(
        "class Connection: pass\nclass Label: pass\ndef build():\n    Connection()\n    Label()\n",
        module="sample.core",
    )
    raw_evidence = {}
    symbols, _, _ = collect_symbols([module], raw_evidence)
    rows = collect_constructs([module], raw_evidence, symbol_index=build_symbol_index(symbols))
    selectors = [row for row in rows if row["kind"] == "construct_selector"]
    connection = next(
        row
        for row in selectors
        if row["data"]["selector_role"] == "constructor"
        and row["data"]["receiver_type"] == "sample.core.Connection"
    )
    label = next(
        row
        for row in selectors
        if row["data"]["selector_role"] == "constructor"
        and row["data"]["receiver_type"] == "sample.core.Label"
    )
    evidence = {key: parse_evidence(value) for key, value in raw_evidence.items()}
    original = parse_record(connection)
    original_binding = call_binding(original.data.get("receiver_binding"))
    assert original_binding is not None
    assert _selector_receiver_site_matches(original, original_binding, None, {}, evidence)

    transplanted = copy.deepcopy(connection)
    transplanted["data"]["receiver_type"] = "sample.core.Label"
    transplanted["data"]["receiver_binding"] = copy.deepcopy(label["data"]["receiver_binding"])
    transplanted["evidence_ids"] = sorted(
        set(transplanted["evidence_ids"]) | set(label["data"]["receiver_binding"]["evidence_ids"])
    )
    changed = parse_record(transplanted)
    changed_binding = call_binding(changed.data.get("receiver_binding"))
    assert changed_binding is not None
    assert not _selector_receiver_site_matches(changed, changed_binding, None, {}, evidence)


def test_selected_membership_match_predicates_aliases_and_roles():
    module = _parsed_module(
        'FLAT = "flat"\n'
        'BACKENDS = ("flat", "wide")\n'
        "class Connection:\n    backend: str\n"
        "class Label:\n    backend: str\n"
        "def route(conn: Connection, label: Label):\n"
        "    conn.backend in BACKENDS\n"
        '    conn.backend in ("flat", "wide")\n'
        "    match conn.backend:\n"
        '        case "flat": pass\n'
        "    conn.backend.startswith(FLAT)\n"
        '    label.backend.endswith("flat")\n'
        "    conn.backend = FLAT\n"
        "    conn.backend()\n"
        "    def getattr(value, name): return None\n"
        '    getattr(conn, "backend")\n'
        '    hasattr(obj=conn, name="backend")\n',
        module="sample.core",
    )
    facts = collect_constructs([module], {})
    selectors = [row["data"] for row in facts if row["kind"] == "construct_selector"]
    pairs = {(row["selector_role"], row["literal"]) for row in selectors}
    assert ("membership", "flat") in pairs
    assert ("membership", "wide") in pairs
    assert ("match", "flat") in pairs
    assert ("startswith", "flat") in pairs
    assert ("endswith", "flat") in pairs
    assert ("write", None) in pairs
    assert ("call", None) in pairs
    # A shadowed builtin and unsupported keyword-only spellings are not asserted to be valid
    # reflection calls; the keyword call remains scoped unresolved evidence.
    reflects = [row for row in selectors if row["selector_role"] == "reflect"]
    assert len(reflects) == 1
    assert reflects[0]["status"] == "unknown"


def test_selector_receiver_collection_reuses_stored_field_proof():
    module = _parsed_module(
        "class Connection:\n    backend: str\n"
        "class Label:\n    backend: str\n"
        "class Holder:\n"
        "    def __init__(self, conn: Connection, label: Label):\n"
        "        self.conn = conn\n        self.label = label\n"
        '    def route(self):\n        self.conn.backend == "flat"\n'
        '        self.label.backend == "flat"\n',
        module="sample.core",
    )
    evidence = {}
    symbols, _, _ = collect_symbols([module], evidence)
    facts = collect_constructs([module], evidence, symbol_index=build_symbol_index(symbols))
    selectors = [row for row in facts if row["kind"] == "construct_selector"]
    selector = next(
        row for row in selectors if row["data"]["receiver_type"] == "sample.core.Connection"
    )
    donor = next(row for row in selectors if row["data"]["receiver_type"] == "sample.core.Label")
    assert selector["data"]["status"] == "decided"
    assert selector["data"]["receiver_type"] == "sample.core.Connection"
    binding = selector["data"]["receiver_binding"]
    assert binding["origin"] == "stored_receiver"
    assert binding["proof"]["kind"] == "stored_field"
    assert binding["proof"]["field"] == "conn"
    records = [parse_record(row) for row in symbols]
    declarations: dict[str, list[Record]] = {}
    for record in records:
        name = record.data.get("qualified_name")
        if isinstance(name, str):
            declarations.setdefault(name, []).append(record)
    evidence_records = {key: parse_evidence(value) for key, value in evidence.items()}
    typed_selector = parse_record(selector)
    typed_binding = call_binding(typed_selector.data.get("receiver_binding"))
    assert typed_binding is not None
    assert _selector_receiver_site_matches(
        typed_selector, typed_binding, None, declarations, evidence_records
    )
    retargeted = copy.deepcopy(selector)
    retargeted["data"]["receiver_type"] = "sample.core.Label"
    retargeted["data"]["receiver_binding"] = copy.deepcopy(donor["data"]["receiver_binding"])
    retargeted["evidence_ids"] = sorted(
        set(retargeted["evidence_ids"]) | set(donor["data"]["receiver_binding"]["evidence_ids"])
    )
    changed = parse_record(retargeted)
    changed_binding = call_binding(changed.data.get("receiver_binding"))
    assert changed_binding is not None
    assert not _selector_receiver_site_matches(
        changed, changed_binding, None, declarations, evidence_records
    )


def test_constructed_selector_assignment_cannot_be_retargeted_to_another_type():
    module = _parsed_module(
        "class Connection: pass\nclass Label: pass\n"
        "def route():\n    built = Connection()\n    built_label = Label()\n"
        '    built.backend == "flat"\n    built_label.backend == "flat"\n',
        module="sample.core",
    )
    evidence = {}
    symbols, _, _ = collect_symbols([module], evidence)
    rows = collect_constructs([module], evidence, symbol_index=build_symbol_index(symbols))
    selectors = [row for row in rows if row["kind"] == "construct_selector"]
    connection = next(
        row
        for row in selectors
        if row["data"]["selector_role"] == "equality"
        and row["data"]["receiver_type"] == "sample.core.Connection"
    )
    label = next(
        row
        for row in selectors
        if row["data"]["selector_role"] == "equality"
        and row["data"]["receiver_type"] == "sample.core.Label"
    )
    evidence_records = {key: parse_evidence(value) for key, value in evidence.items()}
    original = parse_record(connection)
    binding = call_binding(original.data.get("receiver_binding"))
    assert binding is not None
    assert binding.origin.value == "constructed_receiver"
    assert _selector_receiver_site_matches(original, binding, None, {}, evidence_records)

    retargeted = copy.deepcopy(connection)
    retargeted["data"]["receiver_type"] = "sample.core.Label"
    retargeted["data"]["receiver_binding"] = copy.deepcopy(label["data"]["receiver_binding"])
    retargeted["evidence_ids"] = sorted(
        set(retargeted["evidence_ids"]) | set(label["data"]["receiver_binding"]["evidence_ids"])
    )
    changed = parse_record(retargeted)
    changed_binding = call_binding(changed.data.get("receiver_binding"))
    assert changed_binding is not None
    assert not _selector_receiver_site_matches(changed, changed_binding, None, {}, evidence_records)


def test_native_saved_report_keeps_fail_and_unknown_for_selected_scope(tmp_path: Path):
    root = tmp_path / "repo"
    (root / "sample").mkdir(parents=True)
    (root / "sample/core.py").write_text(
        "class Connection:\n    backend: str\n"
        "class Label:\n    backend: str\n"
        "def route(conn: Connection, label: Label, unclear):\n"
        '    conn.backend == "flat"\n'
        '    "flat" == conn.backend\n'
        '    label.backend == "flat"\n'
        '    unclear.backend == "flat"\n'
    )
    contract = {
        "schema_version": "3.11.0",
        "components": [],
        "rules": [
            {
                "id": "SELECT",
                "kind": "forbidden_construct",
                "source": "sample.core",
                "constructs": ["string_literal_compare"],
                "selector": {
                    "receiver": "sample.core.Connection",
                    "member": "backend",
                    "role": "equality",
                    "literal": "flat",
                },
                "rationale": "Keep route selection on the declared port.",
                "provenance": ["contract.json"],
                "decided_by": "architect",
            }
        ],
    }
    (root / "contract.json").write_text(json.dumps(contract))
    for command in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "test@example.invalid"],
        ["git", "config", "user.name", "Test"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"],
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)
    result, encoded = run_report(
        root,
        config=ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        analyzer=observe,
    )
    assert encoded is not None, result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert model.schema_version == "2.6.0"
    assert any(row.kind == "construct_selector" for row in model.records("constructs"))
    assert len(trace_valid_violations(model)) == 2
    assert any(row.kind == "construct_selector_unknown" for row in model.records("violations"))
    [receipt] = [
        row
        for row in model.records("scope_observations")
        if row.kind == "rule_evaluation" and row.rule_ids == ("SELECT",)
    ]
    assert receipt.data.get("claim") == "construct_selector"
    selector_data = receipt.data.get("selector")
    assert selector_data.get("receiver") == "sample.core.Connection"
    assert selector_data.get("member") == "backend"
    assert selector_data.get("role") == "equality"
    assert selector_data.get("literal") == "flat"
    assert receipt.data.get("inventory_fact_ids")
    relabeled = decode_canonical_model(json.loads(encoded))
    relabeled["schema_version"] = "2.5.0"
    with pytest.raises(ValueError, match="selector facts require observation schema 2.6.0"):
        parse_observation(relabeled)

    ordinary = observation_payload(model)
    columnar = decode_canonical_model(json.loads(encoded))
    for payload in (ordinary, columnar):
        selectors = [
            item
            for item in payload["constructs"]
            if item["kind"] == "construct_selector"
            and item["data"]["selector_role"] == "equality"
            and item["data"]["receiver_type"] == "sample.core.Connection"
        ]
        assert selectors
        selectors[0]["data"]["receiver_type"] = "sample.core.Label"
        selectors[0]["data"]["receiver_binding"]["target"] = "sample.core.Label"

    ordinary_path = tmp_path / "tampered-ordinary.json"
    ordinary_path.write_bytes(canonical_json_bytes(ordinary))
    columnar_path = tmp_path / "tampered-columnar.json"
    columnar_path.write_bytes(canonical_json_bytes(encode_canonical_model(columnar)))
    for saved in (ordinary_path, columnar_path):
        replay = run_saved_report(saved)
        assert replay.rule_assessments is None
        assert replay.diagnostics

    # Couple the changed receiver claim to a genuine Label proof from the same source.
    # The source expression remains conn.
    for index, payload in enumerate(
        (observation_payload(model), decode_canonical_model(json.loads(encoded)))
    ):
        _transplant_label_selector(payload)
        coupled_path = tmp_path / f"tampered-coupled-{index}.json"
        coupled_path.write_bytes(canonical_json_bytes(encode_canonical_model(payload)))
        replay = run_saved_report(coupled_path)
        assert replay.rule_assessments is None
        assert replay.diagnostics


def _transplant_label_selector(payload: dict[str, object]) -> None:
    selectors = [
        row
        for row in payload["constructs"]
        if row["kind"] == "construct_selector"
        and row["data"]["selector_role"] == "equality"
        and row["data"]["literal"] == "flat"
    ]
    target = next(
        row
        for row in selectors
        if row["data"]["receiver_parameter"] == "conn"
        and row["data"]["owner"] == "sample.core.route"
    )
    donor = next(
        row
        for row in selectors
        if row["data"]["receiver_parameter"] == "label"
        and row["data"]["owner"] == "sample.core.route"
    )
    target_data = target["data"]
    donor_data = donor["data"]
    target_data["receiver_type"] = donor_data["receiver_type"]
    target_data["receiver_parameter"] = donor_data["receiver_parameter"]
    target_data["receiver_binding"] = donor_data["receiver_binding"]
    target["evidence_ids"] = sorted(
        set(target["evidence_ids"]) | set(donor_data["receiver_binding"]["evidence_ids"])
    )
