# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Known assignment and result-target tags stay nominal before their JSON boundary."""

import json

import pytest
from test_analyzer import _parsed_module

from archkeel.analyzer.python.calls import collect_calls
from archkeel.analyzer.python.imports import collect_imports
from archkeel.analyzer.python.resolve import build_symbol_index
from archkeel.analyzer.python.symbols import collect_symbols
from archkeel.ir import facts
from archkeel.ir.facts import RecordData
from archkeel.ir.facts_codec import parse_record, record_payload


def _facet(name):
    facet = getattr(facts, name, None)
    assert facet is not None, f"Source facts must own {name}"
    return facet


@pytest.mark.parametrize(
    ("owner", "reader", "values"),
    (
        ("ResultBindingTargetKind", "parse_result_binding_target_kind", ("name", "attribute", "subscript")),
        ("SourceAssignmentKind", "parse_source_assignment_kind", ("type_alias", "static_constant", "dynamic_binding")),
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
        "name": "name", "target.item": "attribute", "items[0]": "subscript"
    }
