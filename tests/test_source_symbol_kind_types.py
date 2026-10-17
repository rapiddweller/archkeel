# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""One source-symbol vocabulary, without closing generic record extension data."""

import json
from pathlib import Path
from typing import get_type_hints

import pytest
from test_architecture_demo import _prepare_repo
from test_dependency_api_target import _source_members
from test_uml_evaluation import _model

from archkeel.check.ports import ScanConfig
from archkeel.ir import facts, model
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
DOC = "docs/architecture/source-symbol-kind-types.md"
GUARD = "SOURCE-SYMBOL-KIND-READER-CONTROL"
VALUES = {
    "MODULE": "module",
    "CLASS": "class",
    "INTERFACE": "interface",
    "ENUM": "enum",
    "FUNCTION": "function",
    "METHOD": "method",
    "ALIAS": "alias",
    "ATTRIBUTE": "attribute",
    "CONSTANT": "constant",
    "BINDING": "binding",
    "TYPE_ALIAS": "type_alias",
    "STATIC_CONSTANT": "static_constant",
    "DYNAMIC_BINDING": "dynamic_binding",
}


def _kind():
    assert hasattr(facts, "SourceSymbolKind"), "one Facts-owned source symbol vocabulary"
    return facts.SourceSymbolKind


def test_existing_known_symbol_owner_and_function_subset_have_one_identity():
    kind = _kind()
    assert {item.name: item.value for item in kind} == VALUES
    assert kind.__module__ == "archkeel.ir.facts"
    assert model.FUNCTION_KINDS is facts.FUNCTION_KINDS
    assert facts.FUNCTION_KINDS == frozenset({kind.FUNCTION, kind.METHOD})
    assert all(type(item) is kind for item in facts.FUNCTION_KINDS)
    assert get_type_hints(facts.Record)["kind"] is str


@pytest.mark.parametrize("name,raw", VALUES.items())
def test_valid_legacy_and_nominal_values_decode_at_the_owned_scalar_port(name, raw):
    kind = _kind()
    assert facts.parse_source_symbol_kind(raw) is kind[name]
    assert facts.parse_source_symbol_kind(kind[name]) is kind[name]
    assert json.dumps(raw) == json.dumps(kind[name])


@pytest.mark.parametrize(
    "value", ["vendor.future", "", "class_kind", "enum_literal", None, False, 3, [], {}]
)
def test_unknown_tags_and_non_scalar_metadata_have_no_known_projection(value):
    _kind()
    assert facts.parse_source_symbol_kind(value) is None


def _repository(tmp_path, mutation=None):
    _kind()
    target = json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text())
    target.pop("$schema", None)
    target["components"] = [
        dict(
            id="source",
            label="source",
            role="component",
            packages=["archkeel"],
            responsibilities=["Own immutable known source tags and their scalar reader."],
            forbidden_responsibilities=[],
            provenance=[DOC],
            public=["archkeel"],
        )
    ]
    entities = [
        dict(item)
        for item in target["declarations"]["uml"]["entities"]
        if item["id"] in {"archkeel.ir.facts", "SOURCE-SYMBOL-KIND", "SOURCE-SYMBOL-KIND-READER"}
    ]
    assert len(entities) == 3
    for item in entities:
        if item["kind"] == "module":
            item.pop("parent_id", None)
    target["declarations"] = {
        "uml": {"schema_version": "1.0.0", "entities": entities, "relationships": [], "scopes": []}
    }
    target["rules"] = [item for item in target["rules"] if item["id"] == GUARD]
    assert len(target["rules"]) == 1
    source = "from __future__ import annotations\nfrom enum import StrEnum\n" + _source_members(
        "src/archkeel/ir/facts.py", {"SourceSymbolKind", "parse_source_symbol_kind"}
    )
    if mutation:
        old, new = mutation
        assert source.count(old) == 1
        source = source.replace(old, new)
    root = _prepare_repo(
        tmp_path,
        {
            "archkeel/__init__.py": "",
            "archkeel/ir/__init__.py": "",
            "archkeel/ir/facts.py": source,
            "contract.json": json.dumps(target),
            DOC: (ROOT / DOC).read_text(),
            "docs/architecture/language-adapter-target.md": "Source facts owner.\n",
        },
    )
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _valid(observation):
    comparison = architecture_report(observation).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    rows = [row for row in rule_assessments(observation, undecided_by_rule={}) if row.id == GUARD]
    assert len(rows) == 1 and rows[0].status == "PASS" and rows[0].evaluation_proven
    assert not trace_valid_violations(observation)


def test_native_actual_scalar_reader_matches_independent_target(tmp_path):
    root, config = _repository(tmp_path)
    _valid(_model(root, config))


@pytest.mark.parametrize(
    "old,new",
    [
        ("value: JsonValue | RawJson", "value: object"),
        (") -> SourceSymbolKind | None:", ") -> str | None:"),
    ],
)
def test_native_actual_reader_input_or_return_weakening_fails_fixed_intent(tmp_path, old, new):
    root, config = _repository(tmp_path, (old, new))
    before = (root / "contract.json").read_bytes()
    assert trace_valid_violations(_model(root, config))
    assert (root / "contract.json").read_bytes() == before


def test_native_actual_reader_raw_dispatch_regression_fails_fixed_guard(tmp_path):
    root, config = _repository(tmp_path)
    _valid(_model(root, config))
    source = root / "archkeel/ir/facts.py"
    old = "return SourceSymbolKind(value)"
    assert source.read_text().count(old) == 1
    source.write_text(
        source.read_text().replace(
            old,
            'if value == "class":\n'
            "            return SourceSymbolKind.CLASS\n"
            "        return SourceSymbolKind(value)",
        )
    )
    before = (root / "contract.json").read_bytes()
    assert any(GUARD in row.rule_ids for row in trace_valid_violations(_model(root, config)))
    assert (root / "contract.json").read_bytes() == before
