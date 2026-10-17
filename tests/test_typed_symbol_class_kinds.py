# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Python classifier decisions share their actual source-fact vocabulary."""

import ast
import json
from pathlib import Path

import pytest
from test_analyzer import _parsed_module
from test_architecture_demo import _prepare_repo
from test_uml_evaluation import _model

from archkeel.analyzer.python.imports import collect_imports
from archkeel.analyzer.python.symbols import collect_symbols
from archkeel.check.ports import ScanConfig
from archkeel.ir import facts, model
from archkeel.ir.facts_codec import parse_record, record_payload
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

TAGS = ("protocol", "enum", "pydantic_model", "dataclass", "class")


def _api():
    kind = getattr(facts, "SymbolClassKind", None)
    reader = getattr(facts, "parse_symbol_class_kind", None)
    assert kind is not None and reader is not None, (
        "Facts must own the shared classifier vocabulary"
    )
    assert model.SymbolClassKind is kind
    assert kind.__module__ == facts.__name__
    assert tuple(item.value for item in kind) == TAGS
    return kind, reader


@pytest.mark.parametrize("tag", TAGS)
def test_one_reader_accepts_actual_legacy_tags_and_identical_nominal_members(tag):
    kind, reader = _api()
    assert reader(tag) is kind(tag)
    assert reader(kind(tag)) is kind(tag)


@pytest.mark.parametrize("value", (None, "", "ENUM", "future", "mixin", 1, False, [], {}))
def test_foreign_or_opaque_classifiers_remain_unclassified(value):
    _, reader = _api()
    assert reader(value) is None


def test_actual_fixpoint_produces_nominal_values_without_changing_classifier_records():
    kind, reader = _api()
    module = _parsed_module(
        "from typing import Protocol\n"
        "from enum import Enum\n"
        "from dataclasses import dataclass\n"
        "from pydantic import BaseModel, ConfigDict\n"
        "class Child(Later): pass\n"
        "class Later(Enum): VALUE = 1\n"
        "class Port(Protocol): pass\n"
        "class Client(Port): pass\n"
        "class Extended(Port, Protocol): pass\n"
        "@dataclass\n"
        "class Data: value: int\n"
        "@dataclass\n"
        "class Mixed(Port, Protocol): pass\n"
        "class Plain: pass\n"
        "class Model(BaseModel):\n"
        " model_config = ConfigDict(frozen=True)\n"
        "if enabled:\n"
        " class Conditional(Enum): VALUE = 1\n"
    )
    collect_imports([module], set(), {}, namespace="sample")
    records, _, _ = collect_symbols([module], {})
    classes = {row["title"]: row for row in records if row["kind"] == "class"}
    expected = {
        "Child": kind.ENUM,
        "Later": kind.ENUM,
        "Port": kind.PROTOCOL,
        "Client": kind.CLASS,
        "Extended": kind.PROTOCOL,
        "Data": kind.DATACLASS,
        "Mixed": kind.DATACLASS,
        "Plain": kind.CLASS,
        "Model": kind.PYDANTIC_MODEL,
    }
    assert set(classes) == set(expected) | {"Conditional"}
    assert "class_kind" not in classes["Conditional"]["data"]
    for name, member in expected.items():
        row = classes[name]
        assert row["data"]["class_kind"] is member
        frozen = parse_record(json.loads(json.dumps(row)))
        assert reader(frozen.data.get("class_kind")) is member
        assert json.loads(json.dumps(record_payload(frozen))) == json.loads(json.dumps(row))
    assert classes["Later"]["data"]["enum_members"] == ["VALUE"]
    assert classes["Model"]["data"]["frozen_object"] is True


def _native_target(tmp_path):
    root = Path(__file__).parents[1]
    contract = json.loads((root / "docs/architecture/contracts/ir.json").read_text())
    contract.pop("$schema", None)
    contract["rules"] = [
        rule for rule in contract["rules"] if rule["id"] == "TARGET-COMPLETE_REQUIRES"
    ]
    assert len(contract["rules"]) == 1
    contract["declarations"]["modules"] = []
    target = contract["declarations"]["uml"]
    target["relationships"] = []
    target["scopes"] = []
    ids = {"archkeel.ir.facts", "IR-SYMBOL-CLASS-KIND", "IR-SYMBOL-CLASS-KIND-READER"}
    target["entities"] = [entity for entity in target["entities"] if entity["id"] in ids]
    assert {entity["id"] for entity in target["entities"]} == ids
    project = _prepare_repo(
        tmp_path,
        {
            "archkeel/__init__.py": "",
            "archkeel/ir/__init__.py": "",
            "archkeel/ir/facts.py": (root / "src/archkeel/ir/facts.py").read_text(),
            "contract.json": json.dumps(contract),
            "docs/architecture/python-class-kind.md": "Shared classifier kind.\n",
            "docs/architecture/language-adapter-target.md": "Shared source facts.\n",
        },
    )
    return project, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def test_actual_source_fulfils_the_unchanged_classifier_owner_and_reader_target(tmp_path):
    project, config = _native_target(tmp_path)
    observed = _model(project, config)
    comparison = architecture_report(observed).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    assert not trace_valid_violations(observed)


@pytest.mark.parametrize("mutation", ("owner", "input", "return"))
def test_classifier_port_weakening_fails_the_existing_authored_target(tmp_path, mutation):
    project, config = _native_target(tmp_path)
    contract = project / "contract.json"
    before = contract.read_bytes()
    path = project / "archkeel/ir/facts.py"
    text = path.read_text()
    if mutation == "owner":
        node = next(
            node
            for node in ast.parse(text).body
            if isinstance(node, ast.ClassDef) and node.name == "SymbolClassKind"
        )
        lines = text.splitlines(keepends=True)
        definition = "".join(lines[node.lineno - 1 : node.end_lineno])
        text = "".join(lines[: node.lineno - 1] + lines[node.end_lineno :])
        text = text.replace(
            "from __future__ import annotations",
            "from __future__ import annotations\nfrom .model import SymbolClassKind",
            1,
        )
        (project / "archkeel/ir/model.py").write_text("from enum import StrEnum\n\n" + definition)
        subject = "IR-SYMBOL-CLASS-KIND"
    else:
        old = (
            "value: JsonValue | RawJson | SymbolClassKind"
            if mutation == "input"
            else " -> SymbolClassKind | None:"
        )
        new = "value: object" if mutation == "input" else " -> object:"
        assert text.count(old) == 1
        text = text.replace(old, new, 1)
        subject = "IR-SYMBOL-CLASS-KIND-READER"
    path.write_text(text)
    observed = _model(project, config)
    comparison = architecture_report(observed).comparison
    assert comparison is not None
    if mutation == "owner":
        assert any(
            item.rule_ids == ("TARGET-COMPLETE_REQUIRES",)
            for item in trace_valid_violations(observed)
        ), observed.records("violations")
    else:
        assert any(
            item.status == "FAIL" and item.subject_id == subject for item in comparison.assessments
        ), comparison
    assert contract.read_bytes() == before
