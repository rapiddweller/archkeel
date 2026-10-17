# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source resolution stays nominal across producers without closing open record data."""

import copy
import json
from enum import StrEnum
from pathlib import Path
from typing import get_args, get_type_hints

import pytest
from test_analyzer import _parsed_module
from test_architecture_demo import _prepare_repo
from test_lexical_resolution import _facts
from test_uml_evaluation import _model

from archkeel.analyzer.python.resolve import resolve_name
from archkeel.analyzer.python.symbols import collect_symbols
from archkeel.check.ports import ScanConfig
from archkeel.ir import facts
from archkeel.ir.architecture_graph import ResolutionKind
from archkeel.ir.codec import parse_contract
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.facts_codec import parse_record, record_payload
from archkeel.ir.model import CallRow
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.source_graph import _source_resolution
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
GUARD = "SOURCE-RESOLUTION-CONTROL"


def test_actual_python_call_and_base_producers_return_nominal_source_resolution():
    _, _, calls, _ = _facts(
        "def target(): pass\ntarget()\nmissing()\nobj.target()\nclass Base: pass\nBase()\n"
    )
    status = calls[0]["data"]["status"]
    assert isinstance(status, StrEnum), type(status)
    resolution = facts.SourceResolution
    statuses = {item["data"]["expression"]: item["data"]["status"] for item in calls}
    assert statuses["target"] is resolution.RESOLVED
    assert statuses["missing"] is resolution.UNRESOLVED
    assert statuses["obj.target"] is resolution.PARTIALLY_RESOLVED
    assert statuses["Base"] is resolution.RESOLVED
    construction = next(
        item["data"]["construction"] for item in calls if item["data"]["expression"] == "Base"
    )
    assert construction["status"] is resolution.RESOLVED
    module = _parsed_module("class Base: pass\nclass Child(Base): pass\n", module="sample.core")
    symbols, _, _ = collect_symbols([module], {})
    child = next(item for item in symbols if item["data"]["qualified_name"] == "sample.core.Child")
    assert child["data"]["base_declarations"][0]["status"] is resolution.RESOLVED
    assert get_args(get_type_hints(resolve_name)["return"])[0] is resolution


@pytest.mark.parametrize("raw", ["resolved", "partially_resolved", "unresolved", "future", None, 1])
def test_resolution_boundary_preserves_open_wire_metadata(raw):
    record = {
        "id": "future-record",
        "evidence_class": "FACT",
        "area": "source",
        "kind": "future-kind",
        "title": "future record",
        "subjects": [],
        "evidence_ids": [],
        "rule_ids": [],
        "fact_ids": [],
        "provenance": [],
        "data": {"status": raw, "metadata": {"status": "future-nested"}},
    }
    parsed = parse_record(record)
    assert record_payload(parsed) == record
    recognized = facts.parse_source_resolution(parsed.data.get("status"))
    if raw in ("resolved", "partially_resolved", "unresolved"):
        assert recognized is facts.SourceResolution(raw)
    else:
        assert recognized is None
    assert record_payload(parsed) == record


def test_graph_and_dart_resolver_keep_separate_resolution_domains():
    from archkeel.analyzer.dart.resolve import ResolutionStatus

    assert _source_resolution("partially_resolved", "bad") is ResolutionKind.PARTIAL
    assert _source_resolution("resolved", "bad") is ResolutionKind.RESOLVED
    assert _source_resolution("unresolved", "bad") is ResolutionKind.UNRESOLVED
    assert facts.parse_source_resolution(ResolutionStatus.UNKNOWN) is None
    with pytest.raises(ValueError, match="bad"):
        _source_resolution("unknown", "bad")


def test_call_rows_normalize_only_the_unresolved_source_subset():
    row = CallRow("unresolved", "caller", "call", "reason", None, "source.py", 1)
    assert isinstance(row.status, StrEnum), type(row.status)
    assert row.status is facts.SourceResolution.UNRESOLVED
    assert set(get_args(get_type_hints(CallRow)["status"])) == {
        facts.SourceResolution.UNRESOLVED,
        facts.SourceResolution.PARTIALLY_RESOLVED,
    }
    for invalid in ("resolved", "future", None):
        with pytest.raises(ValueError, match="call row"):
            CallRow(invalid, "caller", "call", "reason", None, "source.py", 1)


def _authored_target(*, include_guard=True):
    ir = json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text())
    python = json.loads((ROOT / "docs/architecture/contracts/python.json").read_text())
    target = copy.deepcopy(ir)
    target.pop("$schema", None)
    target["components"].extend(python["components"])
    target["declarations"]["modules"] = []
    uml = target["declarations"]["uml"]
    wanted = {
        "archkeel.ir.facts",
        "IR-DEPENDENCY-model",
        "IR-SOURCE-RESOLUTION-enum",
        "IR-SOURCE-RESOLUTION-parse",
        "IR-SOURCE-RESOLUTION-CallStatus",
        "IR-SOURCE-RESOLUTION-CallRow",
        "IR-SOURCE-RESOLUTION-CallRow.status",
        "PYTHON-SOURCE-RESOLUTION-module",
        "PYTHON-SOURCE-RESOLUTION-producer",
    }
    entities = [*uml["entities"], *python["declarations"]["uml"]["entities"]]
    uml["entities"] = [entity for entity in entities if entity["id"] in wanted]
    assert {entity["id"] for entity in uml["entities"]} == wanted
    uml["relationships"] = []
    uml["scopes"] = []
    target["rules"] = [rule for rule in python["rules"] if include_guard and rule["id"] == GUARD]
    assert len(target["rules"]) == int(include_guard)
    return target


def _native_repository(tmp_path, *, raw_control=False, widen_field=False, include_guard=True):
    sources = (
        "ir/facts.py",
        "ir/model.py",
        "analyzer/python/resolve.py",
        "analyzer/python/calls.py",
    )
    target = _authored_target(include_guard=include_guard)
    files = {
        "archkeel/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "archkeel/analyzer/__init__.py": "",
        "archkeel/analyzer/python/__init__.py": "",
        "contract.json": json.dumps(target),
    }
    for item in [
        *target["components"],
        *target["rules"],
        *target["declarations"]["uml"]["entities"],
    ]:
        for path in item["provenance"]:
            files[path] = (ROOT / path).read_text()
    for path in sources:
        text = (ROOT / "src/archkeel" / path).read_text()
        if path == "analyzer/python/resolve.py" and raw_control:
            nominal = "if result[0] == SourceResolution.PARTIALLY_RESOLVED:"
            assert nominal in text
            text = text.replace(nominal, 'if result[0] == "partially_resolved":', 1)
        if path == "ir/model.py" and widen_field:
            text = text.replace("status: CallStatus", "status: str")
        files["archkeel/" + path] = text
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def test_actual_native_source_resolution_target_and_control(tmp_path):
    root, config = _native_repository(tmp_path)
    model = _model(root, config)
    assessments = rule_assessments(model, undecided_by_rule={})
    guard = next(row for row in assessments if row.id == GUARD)
    target = next(row for row in assessments if row.kind == "uml_target")
    assert guard.status == "PASS" and guard.evaluation_proven
    assert target.status == "PASS" and target.evaluation_proven
    assert not trace_valid_violations(model)


def test_native_source_resolution_guard_rejects_actual_raw_control_mutation(tmp_path):
    root, config = _native_repository(tmp_path, raw_control=True)
    original = (root / "contract.json").read_bytes()
    model = _model(root, config)
    guard = next(row for row in rule_assessments(model, undecided_by_rule={}) if row.id == GUARD)
    assert guard.status == "FAIL" and guard.evaluation_proven
    assert any(GUARD in row.rule_ids for row in trace_valid_violations(model))
    assert (root / "contract.json").read_bytes() == original


def test_native_call_row_target_rejects_actual_status_type_weakening(tmp_path):
    root, config = _native_repository(tmp_path, widen_field=True)
    original = (root / "contract.json").read_bytes()
    model = _model(root, config)
    assert any(
        row.kind == "uml_conformance"
        and row.data.get("aspect") == "annotation"
        and row.data.get("subject_id") == "IR-SOURCE-RESOLUTION-CallRow.status"
        for row in trace_valid_violations(model)
    )
    assert (root / "contract.json").read_bytes() == original


def test_authored_source_resolution_targets_keep_owned_api_and_required_test_selection():
    target = _authored_target()
    parse_contract(target)
    by_name = {
        entity["qualified_name"]: entity for entity in target["declarations"]["uml"]["entities"]
    }
    assert by_name["archkeel.ir.facts.parse_source_resolution"]["signature"] == {
        "parameters": [
            {
                "name": "value",
                "kind": "positional",
                "default_known": True,
                "annotation": "JsonValue | RawJson",
            }
        ],
        "returns": "SourceResolution | None",
    }
    assert by_name["archkeel.ir.model.CallRow.status"]["annotation"] == "CallStatus"
    assert by_name["archkeel.analyzer.python.resolve.resolve_name"]["signature"]["returns"] == (
        "tuple[SourceResolution, list[str], str, int]"
    )
    assert tuple(member.value for member in facts.SourceResolution) == (
        "resolved",
        "partially_resolved",
        "unresolved",
    )
    required = (
        (ROOT / "Makefile").read_text().split("pr-test:", 1)[1].split("pr-report-test:", 1)[0]
    )
    assert "tests/test_source_resolution_types.py" in required


def test_actual_source_resolution_ports_fulfil_the_unchanged_authored_targets(tmp_path):
    root, config = _native_repository(tmp_path, include_guard=False)
    comparison = architecture_report(_model(root, config)).comparison
    assert comparison is not None and comparison.status == "PASS", comparison


@pytest.mark.parametrize("producer", [False, True])
def test_native_source_resolution_return_weakening_fails_unchanged_authored_target(
    tmp_path, producer
):
    root, config = _native_repository(tmp_path, include_guard=False)
    path = root / ("archkeel/analyzer/python/resolve.py" if producer else "archkeel/ir/facts.py")
    source = path.read_text()
    if producer:
        prefix, separator, operation = source.partition("def resolve_name(")
        assert separator
        nominal = ") -> tuple[SourceResolution, list[str], str, int]:"
        assert nominal in operation
        source = (
            prefix
            + separator
            + operation.replace(nominal, ") -> tuple[str, list[str], str, int]:", 1)
        )
    else:
        nominal = "-> SourceResolution | None:"
        assert nominal in source
        source = source.replace(nominal, "-> str | None:", 1)
    path.write_text(source)
    authored = (root / "contract.json").read_bytes()
    comparison = architecture_report(_model(root, config)).comparison
    subject = "PYTHON-SOURCE-RESOLUTION-producer" if producer else "IR-SOURCE-RESOLUTION-parse"
    assert comparison is not None and any(
        row.status == "FAIL" and row.aspect == "signature" and row.subject_id == subject
        for row in comparison.assessments
    ), comparison
    assert (root / "contract.json").read_bytes() == authored


def test_future_call_status_survives_actual_source_protocol_without_becoming_proof():
    from test_source_trust_boundary import _payload

    from archkeel.ir.facts_codec import decode_response, encode_response

    payload = _payload()
    record = dict(payload["facts"]["sections"][0]["records"][0])
    record.update(id="CALL-FUTURE", kind="future_call", area="call_hierarchy")
    record["data"] = {
        "source_module": "project.app",
        "source_scope": "project.app",
        "expression": "future()",
        "targets": [],
        "status": "future",
    }
    section = next(row for row in payload["facts"]["sections"] if row["name"] == "calls")
    section["records"].append(record)
    response = decode_response(json.dumps(payload).encode())
    assert json.loads(encode_response(response)) == payload
    call = next(
        row
        for section in response.facts.sections
        for row in section.records
        if row.id == "CALL-FUTURE"
    )
    assert facts.parse_source_resolution(call.data.get("status")) is None


def test_absent_status_and_open_kind_survive_generic_record_codec():
    record = {
        "id": "opaque",
        "evidence_class": "FACT",
        "area": "future",
        "kind": "future_kind",
        "title": "opaque record",
        "subjects": [],
        "evidence_ids": [],
        "rule_ids": [],
        "fact_ids": [],
        "provenance": [],
        "data": {"metadata": {"status": "resolved"}},
    }
    parsed = parse_record(record)
    assert facts.parse_source_resolution(parsed.data.get("status")) is None
    assert record_payload(parsed) == record
