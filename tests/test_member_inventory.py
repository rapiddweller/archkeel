# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A closed member scope needs a complete declaration inventory from its owner."""

import ast
from dataclasses import replace
from pathlib import Path
from shutil import copyfile
from textwrap import indent

import pytest
from test_analyzer import _observe

from archkeel.check.uml_compare import compare_graphs
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import ArchitectureGraph, Entity, TargetScope
from archkeel.ir.codec import parse_contract
from archkeel.ir.facts import RecordData
from archkeel.ir.model import Section
from archkeel.ir.source_graph import observed_graph
from archkeel.ir.target_graph import declared_graph


def test_actual_python_dto_declarations_certify_the_eight_original_closed_scopes(tmp_path):
    import json

    repository = Path(__file__).parents[1]
    paths = ("ir/facts.py", "ir/protocol.py", "check/ports.py")
    for path in paths:
        target = tmp_path / "src/archkeel" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        copyfile(repository / "src/archkeel" / path, target)
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "contract.json").write_text('{"schema_version":"2.1.0","components":[],"rules":[]}')
    result = observe(
        tmp_path,
        roots=("src",),
        namespace="archkeel",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )
    assert result.observation is not None, result.diagnostics
    assert result.coverage.status == "PASS"
    assert result.coverage.files_parsed == len(paths)
    graph = observed_graph(result.observation)
    for owner, identities in (
        ("ir", {"source-facts", "coverage", "snapshot", "scope", "request", "response", "error"}),
        ("check", {"port"}),
    ):
        contract = parse_contract(
            json.loads((repository / f"docs/architecture/contracts/{owner}.json").read_bytes())
        )
        comparison = compare_graphs(graph, declared_graph(contract))
        assessed = {
            item.subject_id: item.status
            for item in comparison.assessments
            if item.aspect == "completeness" and item.subject_id in identities
        }
        assert assessed == dict.fromkeys(identities, "PASS")
    selected = {
        "SourceFacts",
        "CollectionCoverage",
        "SnapshotInput",
        "SourceScope",
        "CollectionRequest",
        "CollectionResponse",
        "CollectionError",
        "SourceCollector",
    }
    classes = [
        item
        for item in result.observation.records("symbols") or ()
        if item.kind == "class" and item.data.get("name") in selected
    ]
    assert len(classes) == len(selected)
    assert all(item.data.get("source_member_binding_static") is False for item in classes)


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
            "complete",
        ),
        ("class Data:\n value = 1\n", "complete", "complete"),
        ("class Data:\n def run(self): self.value = 1\n", "complete", "complete"),
        ("class Data:\n if True:\n  value: str\n", "partial", "partial"),
        (
            "def decorate(cls): return cls\n@decorate\nclass Data:\n value: str\n",
            "complete",
            "complete",
        ),
        ("class Base: pass\nclass Data(Base):\n value: str\n", "complete", "complete"),
        ("class Data:\n def run(self): setattr(self, 'value', 1)\n", "complete", "complete"),
        ("class Data:\n value: str\nData = object\n", "partial", "partial"),
        ("def create(): return str\nclass Data:\n value: create()\n", "complete", "complete"),
        (
            "def create(): return 1\nclass Data:\n def run(self, x=create()): ...\n",
            "complete",
            "complete",
        ),
        ("class Data:\n from opaque import value\n", "partial", "partial"),
        ("class Data:\n value += 1\n", "partial", "partial"),
        ("class Data:\n value = (hidden := 1)\n", "partial", "partial"),
        ("class Data:\n global value\n value = 1\n", "partial", "partial"),
        ("class Data:\n value: str\n value: int\n", "partial", "complete"),
        ("class Data:\n def run(self): ...\n def run(self): ...\n", "complete", "partial"),
    ],
)
def test_member_inventory_measures_declarations_separately_from_runtime_effects(
    tmp_path, source, attribute_status, method_status
):
    graph = observed_graph(_observation(tmp_path, source))
    assert [c.status for c in _coverage(graph, "sample.model.Data", "attribute")] == [
        attribute_status
    ]
    assert [c.status for c in _coverage(graph, "sample.model.Data", "method")] == [method_status]


@pytest.mark.parametrize(
    "state",
    [
        "present",
        "missing",
        "conditional",
        "duplicate",
        "import_before",
        "import_after",
        "conditional_import",
        "global_rebind",
        "deleted",
        "walrus",
        "local_shadow",
        "member_write",
        "star_import",
    ],
)
def test_actual_source_scope_needs_one_unconditional_source_definition(tmp_path, state):
    path = Path(__file__).parents[1] / "src/archkeel/ir/protocol.py"
    scope = next(
        node
        for node in ast.parse(path.read_text()).body
        if isinstance(node, ast.ClassDef) and node.name == "SourceScope"
    )
    declaration = ast.unparse(scope) + "\n"
    source = {
        "present": declaration,
        "missing": "",
        "conditional": "if enabled:\n" + indent(declaration, "    "),
        "duplicate": declaration + declaration,
        "import_before": "from other import SourceScope\n" + declaration,
        "import_after": declaration + "from other import SourceScope\n",
        "conditional_import": declaration + "if enabled:\n    from other import SourceScope\n",
        "global_rebind": declaration
        + "def alter():\n    global SourceScope\n    SourceScope = object\n",
        "deleted": declaration + "del SourceScope\n",
        "walrus": declaration + "items = [(SourceScope := object) for item in [1]]\n",
        "local_shadow": declaration + "def read():\n    SourceScope = 1\n    return SourceScope\n",
        "member_write": declaration + "SourceScope.extra = 1\n",
        "star_import": declaration + "from missing import *\n",
    }[state]
    observation = _observation(tmp_path, "from dataclasses import dataclass\n" + source)
    graph = observed_graph(observation)
    target = _target("roots", "namespace", "exclude_test_sources")
    target = replace(
        target,
        entities=tuple(
            replace(entity, qualified_name=entity.qualified_name.replace(".Data", ".SourceScope"))
            for entity in target.entities
        ),
    )
    [assessment] = [
        item
        for item in compare_graphs(graph, target).assessments
        if item.subject_id == "target-data" and item.aspect == "completeness"
    ]
    assert assessment.status == (
        "PASS" if state in {"present", "local_shadow", "member_write"} else "UNKNOWN"
    )
    if state == "present":
        [owner] = [
            item
            for item in observation.records("symbols") or ()
            if item.data.get("name") == "SourceScope"
        ]
        assert owner.data.get("source_binding_unique") is True
        assert owner.data.get("source_member_binding_static") is False
        assert owner.evidence_ids


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


def test_dart_receipts_prove_enum_members_but_keep_module_calls_partial(tmp_path):
    observation = _observation(
        tmp_path,
        "from enum import StrEnum\nclass State(StrEnum):\n READY = 'ready'\n"
        "def helper(): return 1\ndef run(): return helper()\n",
    )
    symbols = list(observation.records("symbols") or ())
    state = next(item for item in symbols if item.data.get("name") == "State")
    inventories = tuple(
        RecordData(
            tuple(
                (
                    key,
                    "complete" if key == "status" else None if key == "reason" else value,
                )
                for key, value in item.entries
            )
        )
        if isinstance(item, RecordData) and item.get("kind") == "attribute"
        else item
        for item in state.data.get("member_inventories")
    )
    state = replace(
        state,
        data=RecordData(
            tuple(
                (key, inventories if key == "member_inventories" else value)
                for key, value in state.data.entries
            )
        ),
    )
    from archkeel.ir.model import Section

    observation = replace(
        observation,
        analyzer=replace(observation.analyzer, name="archkeel-dart-analyzer"),
        sections=tuple(
            Section(
                section.name,
                tuple(state if item.id == state.id else item for item in section.records),
            )
            if section.name == "symbols"
            else section
            for section in observation.sections
        ),
    )
    graph = observed_graph(observation)
    state_coverage = [
        item
        for item in graph.coverage
        if item.scope_id == state.id and "enum_literal" in item.entity_kinds
    ]
    module = next(item for item in graph.entities if item.kind == "module")
    module_calls = [
        item
        for item in graph.coverage
        if item.scope_id == module.id and "calls" in item.relationship_kinds
    ]
    module_symbols = [
        item
        for item in graph.coverage
        if item.scope_id == module.id and "class" in item.entity_kinds
    ]

    assert state_coverage and all(item.status == "complete" for item in state_coverage)
    assert observation.records("calls")
    assert module_calls and all(item.status == "partial" for item in module_calls)
    assert module_symbols and all(item.status == "partial" for item in module_symbols)


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


@pytest.mark.parametrize(
    "parent", ["owner", "other", "", None, False, 1, (), ("owner",), RecordData(), [], {}]
)
@pytest.mark.parametrize("claimed", [False, True])
def test_method_inventory_needs_the_exact_string_parent(parent, claimed):
    from test_source_evaluation import _facts

    from archkeel.ir.facts_validation import _member_inventory_bindings

    seed = _facts().sections[0].records[0]
    inventory = RecordData(
        (
            ("schema_version", "1.0.0"),
            ("kind", "method"),
            ("status", "complete"),
            ("definition_ids", ("method",) if claimed else ()),
        )
    )
    attributes = RecordData(
        (
            ("schema_version", "1.0.0"),
            ("kind", "attribute"),
            ("status", "complete"),
            ("definition_ids", ()),
        )
    )
    owner = replace(
        seed,
        id="owner",
        kind="class",
        data=RecordData(
            (("member_inventories", (attributes, inventory)), ("attribute_declarations", ()))
        ),
    )
    method = replace(
        seed, id="method", kind="method", data=RecordData((("lexical_parent_id", parent),))
    )
    for records in ([owner, method], [method, owner]):
        if claimed is (parent == "owner"):
            _member_inventory_bindings(records)
        else:
            with pytest.raises(ValueError, match="inventory identities"):
                _member_inventory_bindings(records)


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
