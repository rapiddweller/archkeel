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
from archkeel.ir import interfaces, source_graph
from archkeel.ir.architecture_graph import EntityKind
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
        (False, "class", EntityKind.CLASS),
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
