# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Dependency permissions retain their authenticated root and nested owners."""

import json
from dataclasses import replace

import pytest
from test_target_graph import (
    _nested_repository,
    _permission_contract,
    _repository,
)

from archkeel.check.report import run_report
from archkeel.check.uml import assemble_uml
from archkeel.cli.observe import observe
from archkeel.ir.codec import (
    decode_canonical_model,
    load_inside_contract_tree,
    parse_contract,
    parse_observation,
)
from archkeel.ir.graph_codec import graph_bytes, parse_graph
from archkeel.ir.target_graph import declared_graph, declared_tree_graph
from archkeel.ir.target_records import recorded_target_graph


@pytest.mark.parametrize("nested", [False, True])
def test_permission_producers_agree_and_preserve_independent_approval(tmp_path, nested):
    import hashlib

    root, config = _nested_repository(tmp_path) if nested else _repository(tmp_path)
    for path in (config.contract, "inside.json", "leaf.json") if nested else (config.contract,):
        raw = _permission_contract(json.loads((root / path).read_bytes()))
        (root / path).write_text(json.dumps(raw))
    data = (root / config.contract).read_bytes()
    tree = load_inside_contract_tree(
        config.contract,
        parse_contract(json.loads(data)),
        hashlib.sha256(data).hexdigest(),
        config.contract,
        lambda path: ((root / path).read_bytes(), path),
    )
    independent = declared_tree_graph(tree, root_path=config.contract)
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    declaration = next(item for item in model.records("declarations") if item.kind == "uml_target")
    assert recorded_target_graph(model, declaration) == independent
    permissions = tuple(item for item in independent.relationships if item.kind == "requires")
    assert len(permissions) == (3 if nested else 1)
    assert all(
        item.through == ("sample.core.peer",) and item.decided_by == "agent" for item in permissions
    )
    assert not any(item.expression for item in permissions)
    assert parse_graph(json.loads(graph_bytes(independent))) == independent


@pytest.mark.parametrize(
    "field,value",
    [
        ("component", "core"),
        ("through", ()),
        ("rationale", "Changed intent."),
        ("decided_by", "architect"),
    ],
)
def test_core_authenticates_dependency_permission_contents(tmp_path, field, value):
    root, config = _repository(tmp_path)
    (root / config.contract).write_text(json.dumps(_permission_contract()))
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    owner = next(item for item in original.observation.records("declarations") if item.id == "core")
    permissions = owner.data.get("requires")
    changed = replace(
        permissions[0], entries=tuple({**dict(permissions[0].entries), field: value}.items())
    )
    forged = replace(
        owner,
        data=replace(
            owner.data, entries=tuple({**dict(owner.data.entries), "requires": (changed,)}.items())
        ),
    )
    sections = tuple(
        replace(
            section,
            records=tuple(forged if item.id == owner.id else item for item in section.records),
        )
        for section in original.observation.sections
    )
    result = assemble_uml(
        replace(original, observation=replace(original.observation, sections=sections)),
        root,
        config.contract,
    )
    assert result.diagnostics


def test_uml_cannot_redeclare_component_permissions():
    raw = _permission_contract()
    raw["declarations"]["uml"]["relationships"].append(
        {
            "id": "permission",
            "kind": "requires",
            "source_id": "core",
            "target_id": "PEER",
            "provenance": ["docs/target.md"],
        }
    )
    with pytest.raises(ValueError, match="component requires"):
        parse_contract(raw)


def test_permission_identity_survives_reordering_slices_and_duplicate_entries(tmp_path):
    raw = _permission_contract()
    owner = raw["components"][0]
    narrowed = owner["requires"][0]
    narrowed["through"].append("sample.core.peer:Port")
    inherited = {"component": "peer", "rationale": "Use the published boundary."}
    owner["requires"].extend([dict(narrowed), inherited])
    expected = declared_graph(parse_contract(raw))
    permissions = tuple(item for item in expected.relationships if item.kind == "requires")
    assert len(permissions) == len({item.id for item in permissions}) == 3
    assert {(item.through, item.decided_by) for item in permissions} == {
        (("sample.core.peer", "sample.core.peer:Port"), "agent"),
        ((), "architect"),
    }
    reordered = json.loads(json.dumps(raw))
    reordered["components"][0]["requires"].reverse()
    for entry in reordered["components"][0]["requires"]:
        entry.get("through", []).reverse()
    assert declared_graph(parse_contract(reordered)) == expected
    root, config = _repository(tmp_path)
    (root / config.contract).write_text(json.dumps(reordered))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    declaration = next(item for item in model.records("declarations") if item.kind == "uml_target")
    assert recorded_target_graph(model, declaration) == expected


@pytest.mark.parametrize("root_version", ["2.1.0", "2.2.0"])
def test_nested_uml_uses_one_authenticated_target_and_the_same_independent_graph(
    tmp_path, root_version
):
    import hashlib

    root, config = _nested_repository(tmp_path, root_version)
    payload = (root / config.contract).read_bytes()
    tree = load_inside_contract_tree(
        config.contract,
        parse_contract(json.loads(payload)),
        hashlib.sha256(payload).hexdigest(),
        config.contract,
        lambda path: ((root / path).read_bytes(), path),
    )
    assert not tree.issues
    independent = declared_tree_graph(tree, root_path=config.contract)
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    observation = parse_observation(decode_canonical_model(json.loads(encoded)))
    targets = tuple(
        item for item in observation.records("declarations") or () if item.kind == "uml_target"
    )
    assert len(targets) == 1
    graph = recorded_target_graph(observation, targets[0])
    assert graph == independent
    intents = {item.component_id: item for item in graph.component_intents}
    assert intents["ROOT"].parent_id is None
    assert intents["core:core"].parent_id == "ROOT"
    assert intents["core:core"].label == "service"
    assert intents["core:service:core"].parent_id == "core:core"
    assert intents["ROOT"].layout_rule_ids == ("core:layout",)
    assert [(item.component_id, len(item.modules)) for item in graph.module_inventories] == [
        ("ROOT", 1),
        ("core:core", 0),
    ]
    assert {item.id for item in graph.entities if item.kind == "class"} == {
        "core:service",
        "core:service:service",
    }
    assert not any(item.evidence_ids for item in graph.entities)
    assert (
        len(
            tuple(
                item
                for item in observation.records("scope_observations") or ()
                if item.kind == "rule_evaluation" and targets[0].id in item.rule_ids
            )
        )
        == 1
    )
    assert parse_graph(json.loads(graph_bytes(graph))) == graph


@pytest.mark.parametrize(
    "field,value", [("parent_id", "other"), ("role", "projection"), ("public", ())]
)
def test_core_rejects_tampered_inside_owners(tmp_path, field, value):
    root, config = _nested_repository(tmp_path)
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assert original.observation is not None
    owner = next(
        item
        for item in original.observation.records("declarations") or ()
        if item.kind == "inside_component_responsibility"
    )
    fields = {**dict(owner.data.entries), field: value}
    forged = replace(owner, data=replace(owner.data, entries=tuple(fields.items())))
    sections = tuple(
        replace(
            section,
            records=tuple(forged if item.id == owner.id else item for item in section.records),
        )
        for section in original.observation.sections
    )
    result = assemble_uml(
        replace(original, observation=replace(original.observation, sections=sections)),
        root,
        config.contract,
    )
    assert result.diagnostics


def test_incomplete_nested_target_is_not_a_partial_pass(tmp_path):
    root, config = _nested_repository(tmp_path)
    (root / "leaf.json").unlink()
    result, _ = run_report(root, config=config, analyzer=observe)
    assert result.diagnostics and result.declared_rules == "UNKNOWN"


def test_nested_uml_ids_cannot_collide_with_outer_component_ids(tmp_path):
    root, config = _nested_repository(tmp_path)
    outer = json.loads((root / config.contract).read_bytes())
    outer["components"][0]["id"] = "core:service"
    (root / config.contract).write_text(json.dumps(outer))
    result, _ = run_report(root, config=config, analyzer=observe)
    assert result.diagnostics and result.declared_rules == "UNKNOWN"
    assert "collision" in result.diagnostics[0].unknown_claim


@pytest.mark.parametrize(
    "field,value",
    [
        ("component_id", "missing"),
        ("owner_ids", ()),
        ("module_target_ids", ()),
        ("layout_rule_ids", ()),
    ],
)
def test_core_rejects_altered_nested_target_references(tmp_path, field, value):
    root, config = _nested_repository(tmp_path)
    original = assemble_uml(
        observe(
            root,
            roots=config.roots,
            namespace=config.namespace,
            contract=config.contract,
            git_head="a" * 40,
            dirty=False,
            contract_root=root,
        ),
        root,
        config.contract,
    )
    assert original.observation is not None and not original.diagnostics
    declaration = next(
        item
        for item in original.observation.records("declarations") or ()
        if item.kind == "uml_target"
    )
    levels = declaration.data.get("inside_levels")
    changed = replace(levels[0], entries=tuple({**dict(levels[0].entries), field: value}.items()))
    data = replace(
        declaration.data,
        entries=tuple(
            {**dict(declaration.data.entries), "inside_levels": (changed, *levels[1:])}.items()
        ),
    )
    forged = replace(declaration, data=data)
    sections = tuple(
        replace(
            section,
            records=tuple(forged if item.id == forged.id else item for item in section.records),
        )
        for section in original.observation.sections
    )
    result = assemble_uml(
        replace(original, observation=replace(original.observation, sections=sections)),
        root,
        config.contract,
    )
    assert result.diagnostics
