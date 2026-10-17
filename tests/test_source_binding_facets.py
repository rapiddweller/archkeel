# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Known assignment and result-target tags stay nominal before their JSON boundary."""

import ast
import json
from pathlib import Path

import pytest
from test_analyzer import _parsed_module
from test_architecture_demo import _prepare_repo
from test_uml_evaluation import _model

from archkeel.analyzer.python.calls import collect_calls
from archkeel.analyzer.python.imports import collect_imports
from archkeel.analyzer.python.resolve import build_symbol_index
from archkeel.analyzer.python.symbols import collect_symbols
from archkeel.check.ports import ScanConfig
from archkeel.ir import facts
from archkeel.ir.facts import RecordData
from archkeel.ir.facts_codec import parse_record, record_payload
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations


def _facet(name):
    facet = getattr(facts, name, None)
    assert facet is not None, f"Source facts must own {name}"
    return facet


@pytest.mark.parametrize(
    ("owner", "reader", "values"),
    (
        (
            "ResultBindingTargetKind",
            "parse_result_binding_target_kind",
            ("name", "attribute", "subscript"),
        ),
        (
            "SourceAssignmentKind",
            "parse_source_assignment_kind",
            ("type_alias", "static_constant", "dynamic_binding"),
        ),
    ),
)
def test_known_source_tags_are_closed_only_at_their_actual_reader(owner, reader, values):
    kind = _facet(owner)
    parse = getattr(facts, reader, None)
    assert parse is not None, reader
    assert tuple(item.value for item in kind) == values
    for value in values:
        assert parse(value) is kind(value)
        assert parse(kind(value)) is kind(value)
    for unknown in ("future", "", None, False, 1, (), RecordData(), [], {}):
        assert parse(unknown) is None


def test_actual_python_assignment_producer_publishes_the_shared_tag_owner():
    kind = _facet("SourceAssignmentKind")
    module = _parsed_module(
        "from typing import TypeAlias\nAlias: TypeAlias = list[int]\n"
        "Number = 1\nDynamic = factory()\n"
    )
    collect_imports([module], set(), {}, namespace="sample")
    symbols, _, _ = collect_symbols([module], {})
    by_name = {row["data"]["name"]: row for row in symbols}
    for name, expected in (
        ("Alias", kind.TYPE_ALIAS),
        ("Number", kind.STATIC_CONSTANT),
        ("Dynamic", kind.DYNAMIC_BINDING),
    ):
        row = by_name[name]
        assert row["kind"] is expected
        assert row["data"]["record_kind"] is expected
        wire = json.loads(json.dumps(row))
        assert wire["kind"] == expected.value
        assert json.loads(json.dumps(record_payload(parse_record(wire)))) == wire


def test_actual_python_call_producer_publishes_all_three_result_target_tags():
    kind = _facet("ResultBindingTargetKind")
    module = _parsed_module(
        "def factory(): return object()\n"
        "def work(target, items):\n"
        " name = factory()\n target.item = factory()\n items[0] = factory()\n"
    )
    symbols, _, _ = collect_symbols([module], {})
    calls = collect_calls([module], build_symbol_index(symbols), {})
    actual = {
        binding["name"]: binding["target_kind"]
        for call in calls
        for binding in call["data"].get("result_bindings", [])
    }
    assert actual.keys() == {"name", "target.item", "items[0]"}
    for name, expected in (
        ("name", kind.NAME),
        ("target.item", kind.ATTRIBUTE),
        ("items[0]", kind.SUBSCRIPT),
    ):
        assert actual[name] is expected
    assert json.loads(json.dumps(actual)) == {
        "name": "name",
        "target.item": "attribute",
        "items[0]": "subscript",
    }


def _native_target(tmp_path, contract_name="ir"):
    root = Path(__file__).parents[1]
    contract = json.loads(
        (root / f"docs/architecture/contracts/{contract_name}.json").read_text()
    )
    contract.pop("$schema", None)
    rules = {"TARGET-COMPLETE_REQUIRES"}
    ids = {"PYTHON-PARAMETER-SYMBOLS", "PYTHON-SOURCE-ASSIGNMENT-PRODUCER"}
    modules = ("analyzer/python/symbols",)
    if contract_name == "ir":
        rules.update({
            "RESULT-BINDING-TARGET-READER-CONTROL",
            "SOURCE-ASSIGNMENT-READER-CONTROL",
            "RESULT-BINDING-RECONCILE-CONTROL",
        })
        ids = {
            "archkeel.ir.facts", "IR-DEPENDENCY-model", "IR-UML-source_graph",
            "IR-RESULT-BINDING-TARGET-KIND", "IR-RESULT-BINDING-TARGET-READER",
            "IR-SOURCE-ASSIGNMENT-KIND", "IR-SOURCE-ASSIGNMENT-READER",
            "IR-RESULT-BINDING-RECONCILE",
        }
        modules = ("ir/facts", "ir/model", "ir/source_graph", "ir/architecture_graph")
    contract["rules"] = [rule for rule in contract["rules"] if rule["id"] in rules]
    assert {rule["id"] for rule in contract["rules"]} == rules
    contract["declarations"]["modules"] = []
    target = contract["declarations"]["uml"]
    target["relationships"] = []
    target["scopes"] = []
    target["entities"] = [item for item in target["entities"] if item["id"] in ids]
    assert {item["id"] for item in target["entities"]} == ids
    files = {"archkeel/__init__.py": "", "contract.json": json.dumps(contract)}
    for module in modules:
        path = f"archkeel/{module}.py"
        files[path] = (root / "src" / path).read_text()
        parent = Path(path).parent
        while str(parent) != ".":
            files[str(parent / "__init__.py")] = ""
            parent = parent.parent
    provenance = {
        path
        for item in (*contract["components"], *contract["rules"], *target["entities"])
        for path in item.get("provenance", ())
    }
    files.update({path: "Authored architecture intent.\n" for path in provenance})
    return _prepare_repo(tmp_path, files), ScanConfig(
        ("archkeel",), "archkeel", "contract.json", "0" * 64
    )


@pytest.mark.parametrize("contract_name", ("ir", "python"))
def test_actual_source_fulfils_authored_binding_ports_and_native_guards(tmp_path, contract_name):
    project, config = _native_target(tmp_path, contract_name)
    observed = _model(project, config)
    comparison = architecture_report(observed).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    assert not trace_valid_violations(observed)


@pytest.mark.parametrize(
    ("function", "owner", "subject"),
    (
        ("parse_result_binding_target_kind", "ResultBindingTargetKind", "IR-RESULT-BINDING-TARGET-READER"),
        ("parse_source_assignment_kind", "SourceAssignmentKind", "IR-SOURCE-ASSIGNMENT-READER"),
        ("_reconcile_result_binding", None, "IR-RESULT-BINDING-RECONCILE"),
        ("_assignment_symbol", None, "PYTHON-SOURCE-ASSIGNMENT-PRODUCER"),
    ),
)
@pytest.mark.parametrize("mutation", ("input", "return"))
def test_binding_port_weakening_is_rejected_with_fixed_intent(
    tmp_path, function, owner, subject, mutation
):
    project, config = _native_target(tmp_path, "python" if function == "_assignment_symbol" else "ir")
    contract = project / "contract.json"
    before = contract.read_bytes()
    module = "analyzer/python/symbols" if function == "_assignment_symbol" else (
        "ir/facts" if owner else "ir/source_graph"
    )
    path = project / f"archkeel/{module}.py"
    text = path.read_text()
    if owner:
        old = f"def {function}(value: JsonValue | RawJson) -> {owner} | None:"
        new = old.replace("value: JsonValue | RawJson", "value: object") if mutation == "input" else old.replace(f" -> {owner} | None:", " -> object:")
    else:
        node = next(
            item for item in ast.parse(text).body
            if isinstance(item, ast.FunctionDef) and item.name == function
        )
        lines = text.splitlines(keepends=True)
        old = "".join(lines[node.lineno - 1 : node.body[0].lineno - 1])
        kind = "SourceAssignmentKind" if function == "_assignment_symbol" else "ResultBindingTargetKind"
        new = old.replace(f": {kind}", ": str") if mutation == "input" else (
            old.replace(" -> RawRecord:", " -> object:")
            if function == "_assignment_symbol"
            else old.replace(" -> tuple[str, str | None, tuple[DefinitionContext, ...]]:", " -> object:")
        )
    assert old != new and text.count(old) == 1
    path.write_text(text.replace(old, new, 1))
    observed = _model(project, config)
    comparison = architecture_report(observed).comparison
    assert comparison is not None
    assert any(
        row.status == "FAIL" and row.subject_id == subject for row in comparison.assessments
    ), comparison
    assert contract.read_bytes() == before


@pytest.mark.parametrize("owner", ("ResultBindingTargetKind", "SourceAssignmentKind"))
def test_shared_assignment_owner_cannot_move_behind_governance(tmp_path, owner):
    project, config = _native_target(tmp_path)
    contract = project / "contract.json"
    before = contract.read_bytes()
    path = project / "archkeel/ir/facts.py"
    text = path.read_text()
    node = next(
        item for item in ast.parse(text).body
        if isinstance(item, ast.ClassDef) and item.name == owner
    )
    lines = text.splitlines(keepends=True)
    definition = "".join(lines[node.lineno - 1 : node.end_lineno])
    text = "".join(lines[: node.lineno - 1] + lines[node.end_lineno :])
    text = text.replace(
        "from __future__ import annotations",
        f"from __future__ import annotations\nfrom .model import {owner}", 1
    )
    path.write_text(text)
    (project / "archkeel/ir/model.py").write_text("from enum import StrEnum\n\n" + definition)
    observed = _model(project, config)
    assert any(
        item.rule_ids == ("TARGET-COMPLETE_REQUIRES",)
        for item in trace_valid_violations(observed)
    ), observed.records("violations")
    assert contract.read_bytes() == before


@pytest.mark.parametrize(
    ("module", "function", "rule", "probe"),
    (
        ("facts", "parse_result_binding_target_kind", "RESULT-BINDING-TARGET-READER-CONTROL", '    if value == "name":\n        pass\n'),
        ("facts", "parse_source_assignment_kind", "SOURCE-ASSIGNMENT-READER-CONTROL", '    if value == "dynamic_binding":\n        pass\n'),
        ("source_graph", "_reconcile_result_binding", "RESULT-BINDING-RECONCILE-CONTROL", '    if target_kind == "name":\n        pass\n'),
    ),
)
def test_actual_native_guard_rejects_raw_protocol_dispatch(tmp_path, module, function, rule, probe):
    project, config = _native_target(tmp_path)
    contract = project / "contract.json"
    before = contract.read_bytes()
    path = project / f"archkeel/ir/{module}.py"
    text = path.read_text()
    node = next(
        item for item in ast.parse(text).body
        if isinstance(item, ast.FunctionDef) and item.name == function
    )
    lines = text.splitlines(keepends=True)
    lines.insert(node.body[0].lineno - 1, probe)
    path.write_text("".join(lines))
    observed = _model(project, config)
    assert any(rule in item.rule_ids for item in trace_valid_violations(observed))
    assert contract.read_bytes() == before
