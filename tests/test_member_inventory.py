# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A closed member scope needs a complete declaration inventory from its owner."""

from dataclasses import replace
from pathlib import Path
from shutil import copyfile

import pytest

from archkeel.check.uml_compare import compare_graphs
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import ArchitectureGraph, Entity, TargetScope
from archkeel.ir.codec import parse_contract
from archkeel.ir.facts import RecordData
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


def _coverage(graph, name, kind):
    owner = next(e for e in graph.entities if e.qualified_name == name)
    return [c for c in graph.coverage if c.scope_id == owner.id and kind in c.entity_kinds]


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
