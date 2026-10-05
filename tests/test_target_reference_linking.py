# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Target references bind to one independently declared definition."""

from dataclasses import asdict, replace

import pytest

from archkeel.ir.architecture_graph import Entity, Relationship, Signature, TargetDefinition
from archkeel.ir.codec import parse_contract
from archkeel.ir.target_graph import declared_graph

PROVENANCE = ("docs/target.md",)


def _definition(identity, kind, name, parent=None, **details):
    return Entity(
        identity,
        kind,
        name,
        "python",
        parent_id=parent,
        presence="planned",
        responsibilities=("Own this independently declared boundary.",),
        provenance=PROVENANCE,
        **details,
    )


def _reference(identity, kind, name, parent=None, **details):
    return Entity(
        identity,
        kind,
        name,
        "python",
        parent_id=parent,
        presence="referenced",
        provenance=PROVENANCE,
        **details,
    )


def _contract(*, references=(), definitions=(), relationships=()):
    return parse_contract(
        {
            "schema_version": "2.2.0",
            "components": [
                {
                    "id": "owner",
                    "label": "owner",
                    "role": "component",
                    "packages": ["sample"],
                    "responsibilities": ["Own independent declarations."],
                    "forbidden_responsibilities": [],
                    "provenance": list(PROVENANCE),
                }
            ],
            "rules": [],
            "declarations": {
                "uml": asdict(
                    TargetDefinition(
                        entities=(*definitions, *references), relationships=relationships
                    )
                )
            },
        }
    )


def test_target_reference_reuses_the_declared_classifier_identity():
    dto = _definition("dto", "class", "sample.DTO")
    caller = _definition("run", "function", "sample.run")
    ref = _reference("dto-ref", "class", "sample.DTO")
    edge = Relationship("use", "references", "run", "dto-ref", provenance=PROVENANCE)
    graph = declared_graph(
        _contract(definitions=(dto, caller), references=(ref,), relationships=(edge,))
    )
    assert ref not in graph.entities
    assert graph.relationships[0].target_id == dto.id
    assert graph.entities == (graph.entities[0], dto, caller)
    assert graph.relationships[0].provenance == edge.provenance


def test_reference_binding_checks_kind_and_language_without_guessing():
    dto = _definition("dto", "class", "sample.DTO")
    other_kind = _reference("other-kind", "interface", dto.qualified_name)
    other_language = replace(
        _reference("other-language", "class", dto.qualified_name), language="dart"
    )
    graph = declared_graph(_contract(definitions=(dto,), references=(other_kind, other_language)))
    assert other_kind in graph.entities
    assert other_language in graph.entities


def test_an_external_reference_remains_a_reference_without_a_definition():
    ref = _reference("foreign", "class", "external.DTO")
    graph = declared_graph(_contract(references=(ref,)))
    assert ref in graph.entities
    assert ref.presence == "referenced"
    assert not graph.evidence


def test_ambiguous_target_definitions_do_not_choose_a_reference_destination():
    dto = _definition("dto", "class", "sample.DTO")
    other = replace(dto, id="other")
    with pytest.raises(ValueError, match="ambiguous Target reference"):
        _contract(
            definitions=(dto, other), references=(_reference("ref", "class", dto.qualified_name),)
        )


@pytest.mark.parametrize(
    "details",
    [
        {"annotation": "str"},
        {"modifiers": ("frozen",)},
        {"responsibilities": ("Own a different boundary.",)},
    ],
)
def test_binding_cannot_discard_reference_constraints(details):
    dto = _definition("dto", "class", "sample.DTO")
    ref = _reference("ref", "class", dto.qualified_name, **details)
    with pytest.raises(ValueError, match="Target reference carries definition constraints"):
        _contract(definitions=(dto,), references=(ref,))


def test_method_reference_keeps_its_declared_classifier_owner():
    dto = _definition("dto", "class", "sample.DTO")
    method = _definition("run", "method", "sample.DTO.run", "dto", signature=Signature((), "None"))
    class_ref = _reference("class-ref", "class", dto.qualified_name)
    method_ref = _reference("method-ref", "method", method.qualified_name, class_ref.id)
    edge = Relationship("call", "calls", "method-ref", "method-ref", provenance=PROVENANCE)
    graph = declared_graph(
        _contract(
            definitions=(dto, method), references=(class_ref, method_ref), relationships=(edge,)
        )
    )
    assert graph.relationships[0].source_id == method.id
    assert graph.relationships[0].target_id == method.id
    assert all(entity.presence != "referenced" for entity in graph.entities)


def test_method_definition_and_reference_compare_their_linked_owners():
    dto = _definition("dto", "class", "sample.DTO")
    class_ref = _reference("class-ref", "class", dto.qualified_name)
    method = _definition("run", "method", "sample.DTO.run", class_ref.id)
    method_ref = _reference("method-ref", "method", method.qualified_name, dto.id)
    graph = declared_graph(_contract(definitions=(dto, method), references=(class_ref, method_ref)))
    linked = next(entity for entity in graph.entities if entity.id == method.id)
    assert linked.parent_id == dto.id
    assert all(entity.presence != "referenced" for entity in graph.entities)


def test_method_reference_rejects_a_conflicting_owner():
    dto = _definition("dto", "class", "sample.DTO")
    unrelated = _definition("other", "class", "sample.Other")
    method = _definition("run", "method", "sample.DTO.run", "dto")
    ref = _reference("ref", "method", method.qualified_name, unrelated.id)
    with pytest.raises(ValueError, match="Target reference owner differs"):
        _contract(definitions=(dto, unrelated, method), references=(ref,))


def test_reference_provenance_survives_binding():
    dto = _definition("dto", "class", "sample.DTO")
    ref = replace(_reference("ref", "class", dto.qualified_name), provenance=("docs/caller.md",))
    graph = declared_graph(_contract(definitions=(dto,), references=(ref,)))
    linked = next(entity for entity in graph.entities if entity.id == dto.id)
    assert linked.provenance == ("docs/caller.md", "docs/target.md")


def test_reference_binding_cannot_remove_a_completeness_constraint():
    from archkeel.ir.architecture_graph import TargetScope

    dto = _definition("dto", "class", "sample.DTO")
    ref = _reference("ref", "class", dto.qualified_name)
    contract = _contract(references=(ref,))
    target = replace(
        contract.declarations.uml,
        entities=(dto, ref),
        scopes=(
            TargetScope(
                ref.id,
                "closed",
                "Do not drop this constraint.",
                PROVENANCE,
                entity_kinds=("attribute",),
            ),
        ),
    )
    changed = replace(contract, declarations=replace(contract.declarations, uml=target))
    with pytest.raises(ValueError, match="reference cannot own a completeness scope"):
        declared_graph(changed)


@pytest.mark.parametrize("root_version", ["2.1.0", "2.2.0"])
def test_inner_contract_references_bind_to_the_authenticated_nested_definition(
    tmp_path, root_version
):
    import hashlib
    import json

    from test_target_graph import _nested_repository

    from archkeel.check.report import run_report
    from archkeel.cli.observe import observe
    from archkeel.ir.codec import (
        decode_canonical_model,
        load_inside_contract_tree,
        parse_observation,
    )
    from archkeel.ir.target_graph import declared_tree_graph
    from archkeel.ir.target_records import recorded_target_graph

    root, config = _nested_repository(tmp_path, root_version)
    leaf = json.loads((root / "leaf.json").read_bytes())
    for entity in leaf["declarations"]["uml"]["entities"]:
        entity["qualified_name"] = entity["qualified_name"].replace(".Service", ".NestedService")
    (root / "leaf.json").write_text(json.dumps(leaf))
    inner = json.loads((root / "inside.json").read_bytes())
    inner["declarations"]["uml"]["entities"].append(
        asdict(_reference("nested-ref", "class", "sample.core.NestedService"))
    )
    inner["declarations"]["uml"]["relationships"].append(
        asdict(Relationship("nested-use", "references", "run", "nested-ref", provenance=PROVENANCE))
    )
    (root / "inside.json").write_text(json.dumps(inner))
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
    link = next(edge for edge in independent.relationships if edge.id == "core:nested-use")
    assert link.target_id == "core:service:service"
    assert not any(entity.id == "core:nested-ref" for entity in independent.entities)
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    observation = parse_observation(decode_canonical_model(json.loads(encoded)))
    declaration = next(
        item for item in observation.records("declarations") if item.kind == "uml_target"
    )
    assert recorded_target_graph(observation, declaration) == independent
