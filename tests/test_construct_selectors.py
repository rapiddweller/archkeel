# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Construct selectors stay tied to a proven nominal receiver and one operand role."""

import json
import subprocess
from pathlib import Path

import pytest
from test_analyzer import _parsed_module

from archkeel.analyzer.python.constructs import collect_constructs
from archkeel.check.evaluation.rules import _construct_violations
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import ArchitectureRuleKind, DecisionMaker
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.codec_contract import parse_contract
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
        [_parsed_module('class Connection:\n    backend: str\ndef f(conn: Connection):\n    conn.backend == "wide"\n', module="sample.core")],
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
