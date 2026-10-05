# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A closed member scope needs a complete declaration inventory from its owner."""

from dataclasses import replace
from pathlib import Path

import pytest
from test_analyzer import _observe

from archkeel.check.uml_compare import compare_graphs
from archkeel.ir.architecture_graph import ArchitectureGraph, Entity, TargetScope
from archkeel.ir.facts import RecordData
from archkeel.ir.model import Section
from archkeel.ir.source_graph import observed_graph


def _observation(tmp_path: Path, source: str):
    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "model.py").write_text(source)
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    return result.observation


def _coverage(graph, name, kind):
    owner = next(e for e in graph.entities if e.qualified_name == name)
    return [c for c in graph.coverage if c.scope_id == owner.id and kind in c.entity_kinds]


@pytest.mark.parametrize(
    "source,attribute_status,method_status",
    [
        ("class Data:\n value: str\n def run(self): ...\n", "complete", "complete"),
        (
            "from typing import Protocol\nclass Data(Protocol):\n def run(self): ...\n",
            "complete",
            "complete",
        ),
        (
            "from __future__ import annotations\nfrom dataclasses import dataclass\n"
            "@dataclass(frozen=True, slots=True)\nclass Data:\n value: str\n",
            "complete",
            "partial",
        ),
        ("class Data:\n value = 1\n", "partial", "complete"),
        ("class Data:\n def run(self): self.value = 1\n", "partial", "complete"),
        ("class Data:\n if True:\n  value: str\n", "partial", "partial"),
        (
            "def decorate(cls): return cls\n@decorate\nclass Data:\n value: str\n",
            "partial",
            "partial",
        ),
        ("class Base: pass\nclass Data(Base):\n value: str\n", "partial", "partial"),
        ("class Data:\n def run(self): setattr(self, 'value', 1)\n", "partial", "complete"),
        ("class Data:\n value: str\nData = object\n", "partial", "partial"),
        ("def create(): return str\nclass Data:\n value: create()\n", "partial", "partial"),
        (
            "def create(): return 1\nclass Data:\n def run(self, x=create()): ...\n",
            "partial",
            "partial",
        ),
    ],
)
def test_member_inventory_cannot_promote_unsupported_declarations(
    tmp_path, source, attribute_status, method_status
):
    graph = observed_graph(_observation(tmp_path, source))
    assert [c.status for c in _coverage(graph, "sample.model.Data", "attribute")] == [
        attribute_status
    ]
    assert [c.status for c in _coverage(graph, "sample.model.Data", "method")] == [method_status]


def _target(*names):
    owner = Entity(
        "target-data",
        "class",
        "sample.model.Data",
        "python",
        presence="planned",
        provenance=("docs/target.md",),
        responsibilities=("Own data fields.",),
    )
    children = tuple(
        Entity(
            name,
            "attribute",
            f"sample.model.Data.{name}",
            "python",
            parent_id=owner.id,
            presence="planned",
            provenance=("docs/target.md",),
            responsibilities=("Carry a declared value.",),
        )
        for name in names
    )
    return ArchitectureGraph(
        "declared",
        (owner, *children),
        target_scopes=(
            TargetScope(
                owner.id, "closed", "All declared fields.", ("docs/target.md",), ("attribute",)
            ),
        ),
    )


@pytest.mark.parametrize(
    "names,expected", [((), "FAIL"), (("value",), "PASS"), (("value", "missing"), "FAIL")]
)
def test_closed_scope_detects_extra_and_missing_fields(tmp_path, names, expected):
    graph = observed_graph(_observation(tmp_path, "class Data:\n value: str\n"))
    comparison = compare_graphs(graph, _target(*names))
    if expected == "PASS":
        assert {a.status for a in comparison.assessments} == {"PASS"}
    else:
        assert "FAIL" in {a.status for a in comparison.assessments}


def test_legacy_field_inventory_stays_unknown(tmp_path):
    observation = _observation(tmp_path, "class Data:\n value: str\n")
    symbols = tuple(
        replace(
            r,
            data=RecordData(tuple((k, v) for k, v in r.data.entries if k != "member_inventories")),
        )
        for r in observation.records("symbols")
    )
    observation = replace(
        observation,
        sections=tuple(
            Section(s.name, symbols) if s.name == "symbols" else s for s in observation.sections
        ),
    )
    comparison = compare_graphs(observed_graph(observation), _target("value"))
    assert "UNKNOWN" in {a.status for a in comparison.assessments}


@pytest.mark.parametrize("alter", ["foreign", "omit", "kind", "reason"])
def test_inventory_rejects_inconsistent_receipts(tmp_path, alter):
    observation = _observation(tmp_path, "class Data:\n value: str\n def run(self): ...\n")
    symbols = list(observation.records("symbols"))
    index = next(i for i, r in enumerate(symbols) if r.data.get("name") == "Data")
    owner = symbols[index]
    receipts = list(owner.data.get("member_inventories"))
    receipt = receipts[0]
    values = dict(receipt.entries)
    if alter == "foreign":
        values["definition_ids"] = ("foreign",)
    elif alter == "omit":
        values["definition_ids"] = ()
    elif alter == "kind":
        values["kind"] = "function"
    else:
        values["reason"] = "unsupported"
    receipts[0] = RecordData(tuple(values.items()))
    symbols[index] = replace(
        owner,
        data=RecordData(
            tuple(
                (k, tuple(receipts) if k == "member_inventories" else v)
                for k, v in owner.data.entries
            )
        ),
    )
    observation = replace(
        observation,
        sections=tuple(
            Section(s.name, tuple(symbols)) if s.name == "symbols" else s
            for s in observation.sections
        ),
    )
    with pytest.raises(ValueError, match="inventory"):
        observed_graph(observation)


@pytest.mark.parametrize(
    "alter", [None, "foreign", "omit", "duplicate", "version", "role", "static"]
)
def test_source_process_preserves_and_validates_inventory(tmp_path, alter):
    import json

    from archkeel.analyzer.python.collect import collect
    from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
    from archkeel.ir.protocol import (
        CollectionRequest,
        CollectionResponse,
        PythonSettings,
        SnapshotInput,
        SourceScope,
    )

    _observation(tmp_path, "class Data:\n value: str\n def run(self): ...\n")
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope((".",), "sample"),
            PythonSettings(),
        )
    )
    payload = json.loads(encode_response(CollectionResponse(facts)))
    records = next(s["records"] for s in payload["facts"]["sections"] if s["name"] == "symbols")
    owner = next(r for r in records if r["data"]["name"] == "Data")
    receipt = owner["data"]["member_inventories"][0]
    if alter == "foreign":
        receipt["definition_ids"] = [records[-1]["id"]]
    elif alter == "omit":
        receipt["definition_ids"] = []
    elif alter == "duplicate":
        receipt["definition_ids"] *= 2
    elif alter == "version":
        receipt["schema_version"] = "2.0.0"
    elif alter == "static":
        owner["data"]["attribute_declarations"][0]["static"] = "true"
    elif alter == "role":
        operation = next(r for r in records if r["kind"] == "method")
        operation["data"]["member_inventories"] = owner["data"]["member_inventories"]
    encoded = json.dumps(payload).encode()
    if alter is None:
        assert json.loads(encode_response(decode_response(encoded))) == payload
    else:
        with pytest.raises(ProtocolError, match="inventory|static modifier"):
            decode_response(encoded)


def test_member_inventory_schema_is_generated_from_the_source_dataclass():
    import json

    from jsonschema import Draft202012Validator

    from tools.architecture_graph_schema import member_inventory_schema

    path = Path(__file__).parents[1] / "schema/source-member-inventory.schema.json"
    schema = json.loads(path.read_bytes())
    assert schema == member_inventory_schema()
    Draft202012Validator.check_schema(schema)
    valid = {
        "schema_version": "1.0.0",
        "kind": "attribute",
        "status": "complete",
        "definition_ids": ["field"],
        "reason": None,
    }
    assert Draft202012Validator(schema).is_valid(valid)
    assert not Draft202012Validator(schema).is_valid({**valid, "kind": "function"})
    assert not Draft202012Validator(schema).is_valid({**valid, "definition_ids": [True]})


@pytest.mark.parametrize(
    "names,expected", [((), "FAIL"), (("run",), "PASS"), (("run", "missing"), "FAIL")]
)
def test_closed_method_scope_detects_extra_and_missing_operations(tmp_path, names, expected):
    graph = observed_graph(_observation(tmp_path, "class Data:\n def run(self): ...\n"))
    target = _target(*names)
    target = replace(
        target,
        entities=tuple(
            replace(e, kind="method") if e.parent_id is not None else e for e in target.entities
        ),
        target_scopes=tuple(replace(s, entity_kinds=("method",)) for s in target.target_scopes),
    )
    comparison = compare_graphs(graph, target)
    if expected == "PASS":
        assert {a.status for a in comparison.assessments} == {"PASS"}
    else:
        assert "FAIL" in {a.status for a in comparison.assessments}


def test_complete_member_receipt_cannot_override_incomplete_file_collection(tmp_path):
    observation = _observation(tmp_path, "class Data:\n value: str\n")
    observation = replace(observation, coverage=replace(observation.coverage, status="UNKNOWN"))
    graph = observed_graph(observation)
    assert [c.status for c in _coverage(graph, "sample.model.Data", "attribute")] == ["partial"]
    comparison = compare_graphs(graph, _target("value", "missing"))
    assert "UNKNOWN" in {a.status for a in comparison.assessments}
    assert "FAIL" not in {a.status for a in comparison.assessments}


def test_python_profile_embeds_the_generated_member_schema_for_existing_consumers():
    import json

    from jsonschema import Draft202012Validator

    from tools.architecture_graph_schema import member_inventory_schema

    path = Path(__file__).parents[1] / "schema/architecture-ir-python-decoded.schema.json"
    profile = json.loads(path.read_bytes())
    assert profile["$defs"]["member_inventory"] == member_inventory_schema()
    payload = profile["properties"]["symbols"]["items"]["allOf"][-1]
    schema = {"$schema": profile["$schema"], "$defs": profile["$defs"], **payload}
    valid = {
        "kind": "class",
        "data": {
            "member_inventories": [
                {
                    "schema_version": "1.0.0",
                    "kind": kind,
                    "status": "complete",
                    "definition_ids": [],
                    "reason": None,
                }
                for kind in ("attribute", "method")
            ]
        },
    }
    assert Draft202012Validator(schema).is_valid(valid)
    valid["data"]["member_inventories"][0]["definition_ids"] = [True]
    assert not Draft202012Validator(schema).is_valid(valid)
