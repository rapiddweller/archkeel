# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source spelling visibility is distinct from language API visibility."""

import json

import pytest
from test_analyzer import _parsed_module
from test_interfaces import _observation, _symbol_record

from archkeel.analyzer.python.imports import collect_imports
from archkeel.analyzer.python.symbols import collect_symbols
from archkeel.check.evaluation.rules import _interface_verdict
from archkeel.check.onboarding import public_top_level_names
from archkeel.ir import facts
from archkeel.ir.architecture_graph import AssessmentStatus
from archkeel.ir.facts_codec import parse_record, record_payload
from archkeel.ir.interfaces import _public_symbol_names
from archkeel.ir.model import ComponentRole, ContractComponent
from archkeel.ir.reexports import resolve_reexports


def _api():
    owner = getattr(facts, "SourceNameVisibility", None)
    reader = getattr(facts, "parse_source_name_visibility", None)
    assert owner is not None and reader is not None, (
        "Facts must own the source-name visibility vocabulary"
    )
    assert owner.__module__ == facts.__name__
    assert tuple(item.value for item in owner) == ("private", "public_name")
    return owner, reader


@pytest.mark.parametrize("tag", ("private", "public_name"))
def test_reader_accepts_legacy_tags_and_identical_nominal_values(tag):
    owner, reader = _api()
    assert reader(tag) is owner(tag)
    assert reader(owner(tag)) is owner(tag)


@pytest.mark.parametrize("value", (None, "public", "", "PUBLIC_NAME", "future", 1, False, [], {}))
def test_reader_keeps_foreign_visibility_domains_and_opaque_values_unclassified(value):
    _, reader = _api()
    assert reader(value) is None


def test_actual_python_writers_preserve_wire_and_independent_dunder_visibility():
    owner, reader = _api()
    module = _parsed_module(
        "class Public: pass\n"
        "class _Private: pass\n"
        "def public(): pass\n"
        "def _private(): pass\n"
        "def __iter__(): pass\n"
        "VALUE = 1\n"
        "_VALUE = 2\n"
    )
    collect_imports([module], set(), {}, namespace="sample")
    records, _, _ = collect_symbols([module], {})
    names = {row["title"]: row for row in records}
    expected = {
        "Public": owner.PUBLIC_NAME,
        "_Private": owner.PRIVATE,
        "public": owner.PUBLIC_NAME,
        "_private": owner.PRIVATE,
        "__iter__": owner.PRIVATE,
        "VALUE": owner.PUBLIC_NAME,
        "_VALUE": owner.PRIVATE,
    }
    assert set(names) == set(expected)
    for name, member in expected.items():
        row = names[name]
        assert row["data"]["visibility"] is member
        frozen = parse_record(json.loads(json.dumps(row)))
        assert reader(frozen.data["visibility"]) is member
        assert json.loads(json.dumps(record_payload(frozen))) == json.loads(json.dumps(row))
    assert names["__iter__"]["data"]["visibility_detail"]["kind"] == "public"


def test_actual_import_origin_writer_uses_source_name_visibility():
    owner, _ = _api()
    module = _parsed_module("from sample.api import Public, _private\nimport sample.api\n")
    records, _, _ = collect_imports([module], {"sample.api"}, {}, namespace="sample")
    resolve_reexports(records, {})
    actual = {row["data"]["symbol"]: row["data"]["symbol_visibility"] for row in records}
    assert actual["Public"] is owner.PUBLIC_NAME
    assert actual["_private"] is owner.PRIVATE
    assert actual[None] is None


@pytest.mark.parametrize(
    ("tag", "is_public"),
    (("public_name", True), ("private", False), ("public", False), ("future", False), (None, False)),
)
def test_public_name_consumers_preserve_conservative_wire_behavior(tag, is_public):
    symbol = _symbol_record(
        "SYM-X", kind="function", qualified_name="sample.api.Name", module="sample.api", name="Name"
    )
    symbol["data"]["visibility"] = tag
    observed = _observation(symbols=(symbol,))
    expected = {"sample.api": {"Name"}} if is_public else {}
    assert public_top_level_names(observed.records("symbols")) == expected
    assert _public_symbol_names(observed) == expected
    target = ContractComponent("C", "api", ComponentRole.COMPONENT, ("sample.api",), (), (), ())
    data = {
        "symbols_known": True,
        "target_module": "sample.api",
        "symbol": "Name",
        "symbol_visibility": tag,
        "reexport_candidates": ["sample.api.Name"],
        "reexport_chain": ["sample.api.Name"],
        "binding": "Name",
        "reexport": False,
        "origin_definition": "sample.api.Name",
    }
    expected_verdict = AssessmentStatus.UNKNOWN if is_public else AssessmentStatus.FAIL
    assert _interface_verdict(data, target, {}, frozenset()) is expected_verdict
