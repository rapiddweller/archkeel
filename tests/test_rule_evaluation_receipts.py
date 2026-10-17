# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Actual receipt facets, future-open wire behavior and fixed native intent."""

import ast
import copy
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_uml_evaluation import _model, _repository

from archkeel.check.evaluation.rule_support import _rule_evaluation_receipt
from archkeel.check.ports import ScanConfig
from archkeel.check.uml_evaluation import _validate_receipt_identity
from archkeel.ir import model
from archkeel.ir.codec import parse_contract
from archkeel.ir.decisions import _rule_receipt_complete, rule_assessments
from archkeel.ir.facts import Record
from archkeel.ir.facts_codec import parse_record, record_payload
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
GUARD = "RULE-EVALUATION-RECEIPT-CONTROL"


def _reader():
    read = getattr(model, "rule_evaluation_receipt", None)
    assert callable(read), "The shared evaluator receipt reader is absent"
    return read


def _raw(kind="rule_evaluation", data=None):
    return {
        "id": "RECEIPT",
        "evidence_class": "FACT",
        "area": "rules",
        "kind": kind,
        "title": "Opaque future-compatible record",
        "subjects": ["sample.core"],
        "evidence_ids": [],
        "rule_ids": ["RULE"],
        "fact_ids": [],
        "provenance": [],
        "data": {} if data is None else data,
    }


@pytest.mark.parametrize("frozen", [False, True])
def test_omitted_completion_flags_keep_the_distinct_legacy_defaults(frozen):
    read = _reader()
    raw = _raw()
    record = parse_record(raw) if frozen else raw
    view = read(record)
    assert view is not None
    assert type(view) is model.RuleEvaluationReceipt
    assert view.assessment_complete is True
    assert view.cycle_scope_complete is False
    with pytest.raises(FrozenInstanceError):
        view.assessment_complete = False
    assert record_payload(record) == raw if frozen else record == raw


@pytest.mark.parametrize("value", [True, False, None, 0, 1, "true", [], {}])
@pytest.mark.parametrize("frozen", [False, True])
def test_present_flags_require_actual_true_and_do_not_rewrite_payload(value, frozen):
    read = _reader()
    raw = _raw(data={"assessment_complete": value, "cycle_scope_complete": value})
    record = parse_record(raw) if frozen else raw
    view = read(record)
    assert view is not None
    assert view.assessment_complete is (value is True)
    assert view.cycle_scope_complete is (value is True)
    assert record_payload(record) == raw if frozen else record == raw


@pytest.mark.parametrize("kind", ["future_kind", "rule_evaluation_v2", "RULE_EVALUATION"])
def test_future_kinds_remain_open_and_are_not_evaluator_receipts(kind):
    read = _reader()
    raw = _raw(kind, {"assessment_complete": True, "future": {"kind": "unknown", "flag": 1}})
    record = parse_record(raw)
    assert isinstance(record, Record) and record.kind == kind
    assert read(record) is None and read(raw) is None
    assert record_payload(record) == raw


def test_actual_rule_producer_emits_the_shared_plain_wire_tag():
    read = _reader()
    rule = model.CompleteRequiresRule(
        "RULE", model.ArchitectureRuleKind.COMPLETE_REQUIRES, "Keep named imports", (), model.DecisionMaker.ARCHITECT
    )
    raw = _rule_evaluation_receipt(rule, "root", ())
    assert type(raw["kind"]) is str
    assert raw["kind"] == model.RULE_EVALUATION_KIND == "rule_evaluation"
    assert read(raw) == read(parse_record(raw))
    assert read(raw).assessment_complete is True


@pytest.mark.parametrize("cycle", [False, True])
def test_existing_completeness_projection_uses_the_preserved_receipt_defaults(cycle):
    _reader()
    declaration = parse_record(_raw("no_component_cycles" if cycle else "complete_requires"))
    receipt = parse_record(_raw())
    assert _rule_receipt_complete(declaration, receipt) is (not cycle)


@pytest.mark.parametrize("mutation", ["kind", "rule_ids", "id"])
def test_uml_receipt_wrong_kind_or_identity_still_fails_hard(tmp_path, mutation):
    read = _reader()
    root, config = _repository(tmp_path)
    observation = _model(root, config)
    declaration = next(row for row in observation.records("declarations") if row.kind == "uml_target")
    receipt = next(row for row in observation.records("scope_observations") if row.data.get("comparison") is not None)
    assert type(receipt.kind) is str and receipt.kind == model.RULE_EVALUATION_KIND
    assert read(receipt) is not None
    assert architecture_report(observation).comparison is not None
    if mutation == "kind":
        forged = replace(receipt, kind="future_kind")
        assert read(forged) is None
    elif mutation == "rule_ids":
        forged = replace(receipt, rule_ids=(declaration.id, "OTHER"))
    else:
        forged = replace(receipt, id="FORGED")
    with pytest.raises(ValueError, match="identity conflicts"):
        _validate_receipt_identity(declaration, (forged,))


def _target(include_guard=True):
    target = copy.deepcopy(json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text()))
    target.pop("$schema", None)
    entities = target["declarations"]["uml"]["entities"]
    module = next(row for row in entities if row["qualified_name"] == "archkeel.ir.model")
    target["declarations"]["uml"]["entities"] = [
        row for row in entities if row["id"].startswith("IR-RULE-RECEIPT-") or row["id"] == module["id"]
    ]
    assert len(target["declarations"]["uml"]["entities"]) == 6
    target["declarations"]["uml"]["relationships"] = []
    target["declarations"]["uml"]["scopes"] = []
    target["declarations"]["modules"] = []
    target["rules"] = [row for row in target["rules"] if include_guard and row["id"] == GUARD]
    assert len(target["rules"]) == int(include_guard)
    return target


def _native_repository(tmp_path, include_guard=True):
    target = _target(include_guard)
    files = {
        "archkeel/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "contract.json": json.dumps(target),
    }
    for row in [*target["components"], *target["rules"], *target["declarations"]["uml"]["entities"]]:
        for path in row["provenance"]:
            files[path] = (ROOT / path).read_text()
    for path in ("ir/model.py", "ir/facts.py", "ir/source_records.py"):
        files["archkeel/" + path] = (ROOT / "src/archkeel" / path).read_text()
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def test_actual_native_receipt_ports_and_exact_reader_guard_match_authored_intent(tmp_path):
    root, config = _native_repository(tmp_path)
    observation = _model(root, config)
    rows = rule_assessments(observation, undecided_by_rule={})
    guard = next(row for row in rows if row.id == GUARD)
    assert guard.status == "PASS" and guard.evaluation_proven
    comparison = architecture_report(observation).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    assert not trace_valid_violations(observation)


@pytest.mark.parametrize(
    "old,new",
    [
        ("assessment_complete: bool", "assessment_complete: str"),
        ("cycle_scope_complete: bool", "cycle_scope_complete: str"),
        ("record: Record | RawRecord", "record: object"),
        ("-> RuleEvaluationReceipt | None:", "-> bool:"),
    ],
    ids=["assessment-field", "cycle-field", "reader-parameter", "reader-return"],
)
def test_actual_native_type_weakening_fails_unchanged_target(tmp_path, old, new):
    root, config = _native_repository(tmp_path, include_guard=False)
    path = root / "archkeel/ir/model.py"
    source = path.read_text()
    assert source.count(old) == 1
    authored = (root / "contract.json").read_bytes()
    path.write_text(source.replace(old, new, 1))
    comparison = architecture_report(_model(root, config)).comparison
    assert comparison is not None and any(
        row.status == "FAIL" and row.aspect in {"annotation", "signature"}
        for row in comparison.assessments
    ), comparison
    assert (root / "contract.json").read_bytes() == authored


def test_actual_reader_raw_control_mutation_is_rejected_by_the_same_native_guard(tmp_path):
    root, config = _native_repository(tmp_path)
    path = root / "archkeel/ir/model.py"
    source = path.read_text()
    node = next(row for row in ast.parse(source).body if isinstance(row, ast.FunctionDef) and row.name == "rule_evaluation_receipt")
    insertion = node.body[1].lineno - 1 if isinstance(node.body[0], ast.Expr) else node.body[0].lineno - 1
    lines = source.splitlines(keepends=True)
    lines[insertion:insertion] = ['    if isinstance(record, Record) and record.kind == "rule_evaluation":\n        return None\n']
    authored = (root / "contract.json").read_bytes()
    path.write_text("".join(lines))
    observation = _model(root, config)
    guard = next(row for row in rule_assessments(observation, undecided_by_rule={}) if row.id == GUARD)
    assert guard.status == "FAIL" and guard.evaluation_proven
    assert any(GUARD in row.rule_ids for row in trace_valid_violations(observation))
    assert (root / "contract.json").read_bytes() == authored


def test_actual_marker_owner_relocation_fails_the_fixed_native_target(tmp_path):
    root, config = _native_repository(tmp_path, include_guard=False)
    owner = root / "archkeel/ir/model.py"
    source = owner.read_text()
    marker = next(row for row in ast.parse(source).body if isinstance(row, ast.ClassDef) and row.name == "_RuleEvaluationTag")
    lines = source.splitlines(keepends=True)
    marker_source = "".join(lines[marker.lineno - 1 : marker.end_lineno])
    lines[marker.lineno - 1 : marker.end_lineno] = []
    lines.insert(5, "from .facts import _RuleEvaluationTag\n")
    owner.write_text("".join(lines))
    wrong_owner = root / "archkeel/ir/facts.py"
    wrong_owner.write_text(wrong_owner.read_text() + "\n" + marker_source + "\n")
    authored = (root / "contract.json").read_bytes()
    comparison = architecture_report(_model(root, config)).comparison
    assert comparison is not None and any(
        row.status == "FAIL" and row.subject_id == "IR-RULE-RECEIPT-tag"
        for row in comparison.assessments
    ), comparison
    assert (root / "contract.json").read_bytes() == authored


def test_authored_ports_use_the_existing_model_owner_and_selected_regression_gate():
    target = _target()
    parse_contract(target)
    reader = next(row for row in target["declarations"]["uml"]["entities"] if row["id"] == "IR-RULE-RECEIPT-read")
    assert reader["signature"] == {
        "parameters": [{"name": "record", "kind": "positional", "default_known": True, "annotation": "Record | RawRecord"}],
        "returns": "RuleEvaluationReceipt | None",
    }
