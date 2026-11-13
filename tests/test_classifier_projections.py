# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Existing class tags have separate conservative UI and graph projections."""

import json
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_interfaces import _symbol_record

from archkeel.check.ports import ScanConfig
from archkeel.ir import interfaces, source_graph
from archkeel.ir.architecture_graph import EntityKind
from archkeel.ir.facts import RecordData, SymbolClassKind, parse_symbol_class_kind
from archkeel.ir.facts_codec import parse_record


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
