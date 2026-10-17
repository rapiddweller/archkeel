# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Existing class tags have separate conservative UI and graph projections."""

import ast
import json
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_interfaces import _symbol_record
from test_uml_evaluation import _model

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir import interfaces, source_graph
from archkeel.ir.architecture_graph import EntityKind
from archkeel.ir.diagnostics import DiagnosticKind
from archkeel.ir.facts import RecordData, SymbolClassKind, parse_symbol_class_kind
from archkeel.ir.facts_codec import parse_record
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations


def _reader():
    reader = getattr(source_graph, "_classifier_kind", None)
    assert reader is not None, "Graph normalization must own its conservative classifier reader"
    return reader


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("protocol", EntityKind.INTERFACE),
        ("enum", EntityKind.ENUM),
        ("mixin", EntityKind.MIXIN),
        ("dataclass", None),
        ("pydantic_model", None),
        ("class", None),
        ("interface", None),
        ("package", None),
        ("future", None),
        (None, None),
        (1, None),
        (False, None),
        ((), None),
        (RecordData(), None),
    ),
)
def test_graph_reader_recognizes_only_existing_classifier_projections(value, expected):
    assert _reader()(value) is expected


def test_mixin_projection_does_not_expand_the_existing_contract_kind_grammar():
    assert parse_symbol_class_kind("mixin") is None
    with pytest.raises(ValueError):
        SymbolClassKind("mixin")
    assert _reader()("mixin") is EntityKind.MIXIN
    assert all(isinstance(kind, SymbolClassKind) for kind in interfaces._CLASS_KINDS)


@pytest.mark.parametrize(
    ("tag", "ui", "graph"),
    (
        ("dataclass", "dataclass", EntityKind.CLASS),
        ("protocol", "protocol", EntityKind.INTERFACE),
        ("enum", "enum", EntityKind.ENUM),
        ("pydantic_model", "class", EntityKind.CLASS),
        ("class", "class", EntityKind.CLASS),
        ("mixin", "class", EntityKind.MIXIN),
        ("interface", "class", EntityKind.CLASS),
        ("future", "class", EntityKind.CLASS),
        (None, "class", EntityKind.CLASS),
    ),
)
def test_ui_and_graph_keep_their_distinct_wire_projections_and_unknown_fallbacks(tag, ui, graph):
    raw = _symbol_record(
        "SYM-X", kind="class", qualified_name="sample.api.Name", module="sample.api", name="Name"
    )
    raw["data"]["class_kind"] = tag
    record = parse_record(raw)
    assert interfaces._symbol_kind(record) == ui
    assert type(interfaces._symbol_kind(record)) is str
    assert source_graph._symbol(record, "future-language").kind is graph
    assert record.data.get("class_kind") == tag


@pytest.mark.parametrize("kind", ("future-kind", "module", "function", "enum", "protocol"))
def test_interface_names_leave_unrelated_and_future_record_kinds_open(kind):
    raw = _symbol_record(
        "SYM-X", kind=kind, qualified_name="sample.api.Name", module="sample.api", name="Name"
    )
    assert interfaces._symbol_kind(parse_record(raw)) == kind


@pytest.mark.parametrize("value", (False, 1, [], {}))
def test_graph_projection_keeps_existing_malformed_classifier_validation(value):
    raw = _symbol_record(
        "SYM-X", kind="class", qualified_name="sample.api.Name", module="sample.api", name="Name"
    )
    raw["data"]["class_kind"] = value
    with pytest.raises(ValueError, match="source graph expected text"):
        source_graph._symbol(parse_record(raw), "future-language")


def _native_target(tmp_path):
    root = Path(__file__).parents[1]
    contract = json.loads((root / "docs/architecture/contracts/ir.json").read_text())
    contract.pop("$schema", None)
    rules = {
        "TARGET-COMPLETE_REQUIRES",
        "CLASSIFIER-INTERFACE-KIND-CONTROL",
        "CLASSIFIER-GRAPH-KIND-CONTROL",
    }
    contract["rules"] = [rule for rule in contract["rules"] if rule["id"] in rules]
    assert {rule["id"] for rule in contract["rules"]} == rules
    contract["declarations"]["modules"] = []
    target = contract["declarations"]["uml"]
    target["relationships"] = []
    target["scopes"] = []
    ids = {
        "archkeel.ir.facts",
        "IR-UML-architecture_graph",
        "IR-GRAPH-EntityKind",
        "IR-UML-source_graph",
        "IR-DEPENDENCY-model",
        "IR-CLASSIFIER-GRAPH-READER",
    }
    target["entities"] = [entity for entity in target["entities"] if entity["id"] in ids]
    assert {entity["id"] for entity in target["entities"]} == ids
    files = {
        "archkeel/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "contract.json": json.dumps(contract),
        "docs/architecture/classifier-projections.md": "Conservative classifier projection.\n",
        "docs/architecture/uml-model-target.md": "Shared architecture graph.\n",
        "docs/architecture/typed-graph-vocabulary.md": "Canonical graph kinds.\n",
        "docs/architecture/dependency-selector-target.md": "Compatibility facade.\n",
        "docs/architecture/language-adapter-target.md": "Shared source facts.\n",
    }
    for name in ("facts", "model", "architecture_graph", "source_graph", "interfaces"):
        path = f"archkeel/ir/{name}.py"
        files[path] = (root / "src" / path).read_text()
    project = _prepare_repo(tmp_path, files)
    return project, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def test_actual_source_fulfils_independent_classifier_reader_and_function_guards(tmp_path):
    project, config = _native_target(tmp_path)
    observed = _model(project, config)
    comparison = architecture_report(observed).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    assert not trace_valid_violations(observed)


@pytest.mark.parametrize("mutation", ("owner", "input", "return", "reader_control", "ui_control"))
def test_projection_port_weakening_fails_with_unchanged_authored_intent(tmp_path, mutation):
    project, config = _native_target(tmp_path)
    contract = project / "contract.json"
    before = contract.read_bytes()
    path = project / "archkeel/ir/source_graph.py"
    text = path.read_text()
    signature = "def _classifier_kind(value: JsonValue) -> EntityKind | None:"
    if mutation == "owner":
        node = next(
            node
            for node in ast.parse(text).body
            if isinstance(node, ast.FunctionDef) and node.name == "_classifier_kind"
        )
        lines = text.splitlines(keepends=True)
        definition = "".join(lines[node.lineno - 1 : node.end_lineno])
        text = "".join(lines[: node.lineno - 1] + lines[node.end_lineno :])
        text = text.replace(
            "from __future__ import annotations",
            "from __future__ import annotations\nfrom .interfaces import _classifier_kind",
            1,
        )
        destination = project / "archkeel/ir/interfaces.py"
        destination.write_text(
            destination.read_text().replace(
                "from __future__ import annotations",
                "from __future__ import annotations\nfrom .model import JsonValue",
                1,
            )
            + "\n"
            + definition
        )
    elif mutation in {"input", "return"}:
        assert text.count(signature) == 1
        changed = (
            signature.replace("value: JsonValue", "value: object")
            if mutation == "input"
            else signature.replace(" -> EntityKind | None:", " -> str:")
        )
        text = text.replace(signature, changed, 1)
    else:
        name = "_classifier_kind"
        probe = '    if value == "enum":\n        return EntityKind.ENUM\n'
        if mutation == "ui_control":
            path = project / "archkeel/ir/interfaces.py"
            text = path.read_text()
            name = "_symbol_kind"
            probe = '    if symbol.kind == "class":\n        pass\n'
        node = next(
            node
            for node in ast.parse(text).body
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
        lines = text.splitlines(keepends=True)
        lines.insert(node.body[0].lineno - 1, probe)
        text = "".join(lines)
    path.write_text(text)
    if mutation == "owner":
        # The existing guard rejects its missing physical subject before UML comparison.
        result, _ = run_report(project, config=config, analyzer=observe)
        assert result.exit_code == 2
        assert any(
            item.kind is DiagnosticKind.RULE_WITHOUT_SUBJECTS
            and item.subject == "CLASSIFIER-GRAPH-KIND-CONTROL"
            for item in result.diagnostics
        ), result.diagnostics
        assert contract.read_bytes() == before
        return
    observed = _model(project, config)
    comparison = architecture_report(observed).comparison
    assert comparison is not None
    if mutation in {"input", "return"}:
        assert any(
            row.status == "FAIL" and row.subject_id == "IR-CLASSIFIER-GRAPH-READER"
            for row in comparison.assessments
        ), comparison
    else:
        rule = {
            "reader_control": "CLASSIFIER-GRAPH-KIND-CONTROL",
            "ui_control": "CLASSIFIER-INTERFACE-KIND-CONTROL",
        }[mutation]
        assert any(rule in row.rule_ids for row in trace_valid_violations(observed))
    assert contract.read_bytes() == before
