# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Protocol Target intent includes the language selector, not architecture policy."""

import json
from dataclasses import replace
from pathlib import Path

from archkeel.check.uml_compare import compare_graphs
from archkeel.ir.codec import parse_contract
from archkeel.ir.model import Observation
from archkeel.ir.source_graph import observed_graph
from archkeel.ir.target_graph import declared_graph

ROOT = Path(__file__).parents[1]
SETTINGS = {
    "PythonSettings": {"language": "Literal['python']"},
    "DartSettings": {"language": "Literal['dart']"},
    "TypeScriptSettings": {"language": "Literal['typescript']", "tsconfig": "str"},
}
PROTOCOL_REFERENCES = {
    ("archkeel.ir.protocol", f"archkeel.ir.protocol.{name}") for name in SETTINGS
} | {
    ("archkeel.ir.protocol.CollectionRequest", "archkeel.ir.protocol.ResolverSettings"),
    ("archkeel.ir.protocol.CollectionRequest", "archkeel.ir.protocol.PROTOCOL_VERSION"),
    ("archkeel.ir.protocol.CollectionResponse", "archkeel.ir.protocol.PROTOCOL_VERSION"),
}


def _graphs(observation: Observation):
    contract = parse_contract(
        json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text())
    )
    target = declared_graph(contract)
    return observed_graph(observation), target


def test_protocol_target_has_all_resolver_variants_and_typed_public_fields(
    self_observation: Observation,
):
    observed, target = _graphs(self_observation)
    by_name = {e.qualified_name: e for e in target.entities}
    for name, fields in SETTINGS.items():
        classifier = by_name[f"archkeel.ir.protocol.{name}"]
        assert classifier.kind == "class" and classifier.presence == "planned"
        assert classifier.modifiers == ("frozen",)
        for field, annotation in fields.items():
            value = by_name[f"{classifier.qualified_name}.{field}"]
            assert value.kind == "attribute" and value.parent_id == classifier.id
            assert value.visibility.kind == "public" and value.annotation == annotation
    assert by_name["archkeel.ir.protocol.ResolverSettings"].kind == "type_alias"
    assert by_name["archkeel.ir.protocol.PROTOCOL_VERSION"].kind == "constant"
    comparison = compare_graphs(observed, target)
    ids = {by_name[f"archkeel.ir.protocol.{name}"].id for name in SETTINGS}
    assert all(
        any(
            a.subject_id == id and a.aspect == "existence" and a.status == "PASS"
            for a in comparison.assessments
        )
        for id in ids
    )


def test_protocol_target_links_language_variants_request_and_shared_version(
    self_observation: Observation,
):
    observed, target = _graphs(self_observation)
    entities = {e.id: e for e in target.entities}
    relations = [
        r
        for r in target.relationships
        if r.kind == "references"
        and entities[r.source_id].qualified_name.startswith("archkeel.ir.protocol")
    ]
    assert {
        (entities[r.source_id].qualified_name, entities[r.target_id].qualified_name)
        for r in relations
    } == PROTOCOL_REFERENCES
    assert all(r.provenance and not r.evidence_ids and not r.record_ids for r in relations)
    comparison = compare_graphs(observed, target)
    assert all(
        any(
            a.subject_id == r.id and a.aspect == "relationship" and a.status == "PASS"
            for a in comparison.assessments
        )
        for r in relations
    )


def test_protocol_target_rejects_a_changed_language_discriminator_without_copying_source(
    self_observation: Observation,
):
    observed, target = _graphs(self_observation)
    wanted = next(
        e
        for e in target.entities
        if e.qualified_name == "archkeel.ir.protocol.TypeScriptSettings.language"
    )
    actual = next(
        e
        for e in observed.entities
        if e.qualified_name == wanted.qualified_name and e.kind == "attribute"
    )
    changed = replace(
        observed,
        entities=tuple(
            replace(e, annotation="str") if e.id == actual.id else e for e in observed.entities
        ),
    )
    comparison = compare_graphs(changed, target)
    assert any(
        a.subject_id == wanted.id and a.aspect == "annotation" and a.status == "FAIL"
        for a in comparison.assessments
    )
    assert target.entities == _graphs(self_observation)[1].entities


def test_expanded_self_target_retains_exactly_eight_incomplete_member_scopes(
    self_observation: Observation,
):
    unknowns = self_observation.records("unknowns")
    inventory = tuple(item for item in unknowns if item.kind == "uml_conformance")
    assert len(inventory) == 8
    assert {item.data.get("subject_id") for item in inventory} == {
        "ir:source-facts",
        "ir:coverage",
        "ir:snapshot",
        "ir:scope",
        "ir:request",
        "ir:response",
        "ir:error",
        "check:port",
    }
    assert all(
        item.data.get("aspect") == "completeness" and item.data.get("status") == "UNKNOWN"
        for item in inventory
    )
    # AD-207 retains saved-query facade limits without changing these member scopes.
    from archkeel.check.ratchets import unknown_positions_by_rule

    counts = dict(unknown_positions_by_rule(self_observation))
    assert {rule: count for rule, count in counts.items() if not rule.startswith("UML-TARGET")} == {
        "RENDER-TYPES-DECLARED": 25,
        "CHECK-TYPES-DECLARED": 19,
        "ANALYZER-TYPES-DECLARED": 1,
    }
    assert sum(counts.values()) == 53
    detail_positions = [
        item
        for item in unknowns
        if item.kind == "boundary_type_position"
        and item.data.get("qualified_name") == "archkeel.render.html.render_architecture_details"
    ]
    assert len(detail_positions) == 1
    assert detail_positions[0].data.get("annotation") == "RunResult"
    assert detail_positions[0].data.get("reason") == "forward_reference"
    baseline = json.loads((ROOT / "architecture-baseline.json").read_text())
    assert baseline["budgets"]["unknown_positions"] == 53
