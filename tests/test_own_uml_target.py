# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The own graph boundary has independent, testable UML intent."""

import json
from dataclasses import replace
from pathlib import Path

from archkeel.check.uml_compare import compare_graphs
from archkeel.ir.codec import parse_contract
from archkeel.ir.model import Observation
from archkeel.ir.source_graph import observed_graph
from archkeel.ir.target_graph import declared_graph

ROOT = Path(__file__).parents[1]
# The observed classifier includes implementation methods beyond the authored Target.
OBSERVED_GRAPH_METHODS = frozenset(
    {
        "__post_init__",
        "validate",
        "_validate_public_api",
        "_validate_physical_intent",
        "_validate_entities",
        "_validate_permission_metadata",
        "_validate_classifier_relationship",
        "_validate_relationships",
        "_validate_scopes",
        "_validate_evidence",
    }
)

TYPE_DEPENDENCIES = {
    ("ComponentIntent", "ComponentRole"),
    ("TargetDefinition", "GraphSchemaVersion"),
    ("ArchitectureGraph", "GraphSchemaVersion"),
    ("Signature", "Parameter"),
    ("Entity", "Visibility"),
    ("Entity", "Signature"),
    ("TargetDefinition", "Entity"),
    ("TargetDefinition", "Relationship"),
    ("TargetDefinition", "TargetScope"),
    ("GraphComparison", "GraphAssessment"),
    ("GraphComparison", "EntityCorrespondence"),
    ("ArchitectureGraph", "Entity"),
    ("ArchitectureGraph", "Relationship"),
    ("ArchitectureGraph", "Coverage"),
    ("ArchitectureGraph", "TargetScope"),
    ("ArchitectureReport", "ArchitectureGraph"),
    ("ArchitectureReport", "GraphComparison"),
    ("ArchitectureReport", "ReportFinding"),
    ("ArchitectureReport", "ComponentMembership"),
    ("ArchitectureReport", "DependencyDecisionGap"),
    ("ArchitectureGraph", "ExternalDependencyScopeRule"),
}


def test_own_target_declares_the_component_role_enum_literals():
    target = _target()
    role = next(
        e
        for e in target.entities
        if e.qualified_name == "archkeel.ir.architecture_graph.ComponentRole"
    )
    assert role.kind == "enum"
    assert {
        e.qualified_name.rsplit(".", 1)[-1]
        for e in target.entities
        if e.parent_id == role.id and e.kind == "enum_literal"
    } == {"COMPONENT", "INTERFACE", "CONTRACT", "PROJECTION", "FOUNDATION"}
    assert target.schema_version == "1.1.0"


def _target():
    path = ROOT / "docs/architecture/contracts/ir.json"
    return declared_graph(parse_contract(json.loads(path.read_bytes())), contract_path=str(path))


def test_own_graph_boundary_declares_fields_methods_and_imports():
    target = _target()
    by_name = {item.qualified_name: item for item in target.entities}
    graph = by_name["archkeel.ir.architecture_graph.ArchitectureGraph"]
    validate = by_name["archkeel.ir.architecture_graph.ArchitectureGraph.validate"]
    origin = by_name["archkeel.ir.architecture_graph.ArchitectureGraph.origin"]
    private = by_name["archkeel.ir.architecture_graph.ArchitectureGraph._validate_entities"]

    assert graph.kind == "class" and "frozen" in graph.modifiers
    assert validate.kind == "method" and validate.parent_id == graph.id
    assert validate.visibility.kind == "public"
    assert validate.signature is not None and validate.signature.returns == "None"
    assert origin.kind == "attribute" and origin.annotation == "OriginKind"
    assert private.visibility.kind == "private"
    assert any(item.kind == "imports" for item in target.relationships)
    assert any(item.kind == "calls" for item in target.relationships)
    assert not target.evidence
    assert all(not item.record_ids and not item.evidence_ids for item in target.entities)


def test_own_class_model_has_independent_type_dependencies(self_observation: Observation):
    target = _target()
    entities = {item.id: item for item in target.entities}
    references = tuple(
        item
        for item in target.relationships
        if item.kind == "references"
        and entities[item.source_id].qualified_name.startswith("archkeel.ir.architecture_graph.")
    )
    assert {
        (
            entities[item.source_id].qualified_name.rsplit(".", 1)[-1],
            entities[item.target_id].qualified_name.rsplit(".", 1)[-1],
        )
        for item in references
    } == TYPE_DEPENDENCIES
    assert all(
        item.provenance and not item.record_ids and not item.evidence_ids for item in references
    )

    observed = observed_graph(self_observation)
    before = compare_graphs(observed, target)
    assert all(
        any(
            item.subject_id == reference.id
            and item.aspect == "relationship"
            and item.status == "PASS"
            for item in before.assessments
        )
        for reference in references
    )
    wanted = next(
        item
        for item in references
        if entities[item.source_id].qualified_name.endswith(".Signature")
    )
    source = next(
        item.id
        for item in observed.entities
        if item.qualified_name == entities[wanted.source_id].qualified_name
    )
    endpoint = next(
        item.id
        for item in observed.entities
        if item.qualified_name == entities[wanted.target_id].qualified_name
    )
    changed = replace(
        observed,
        relationships=tuple(
            item
            for item in observed.relationships
            if not (
                item.kind == "references"
                and item.source_id == source
                and item.target_id == endpoint
            )
        ),
    )
    after = compare_graphs(changed, target)
    assert any(
        item.subject_id == wanted.id and item.aspect == "relationship" and item.status == "UNKNOWN"
        for item in after.assessments
    )
    certified = replace(
        changed,
        coverage=tuple(
            replace(item, status="complete", reason=None)
            if "references" in item.relationship_kinds
            else item
            for item in changed.coverage
        ),
    )
    assert any(
        item.subject_id == wanted.id and item.aspect == "relationship" and item.status == "FAIL"
        for item in compare_graphs(certified, target).assessments
    )
    assert _target() == target


def test_own_target_does_not_follow_an_observed_method_change(self_observation: Observation):
    target = _target()
    model = self_observation
    observed = observed_graph(model)
    qualified_name = "archkeel.ir.architecture_graph.ArchitectureGraph.validate"
    wanted = next(item for item in target.entities if item.qualified_name == qualified_name)
    actual = next(item for item in observed.entities if item.qualified_name == qualified_name)
    before = compare_graphs(observed, target)
    assert any(
        item.subject_id == wanted.id and item.aspect == "signature" and item.status == "PASS"
        for item in before.assessments
    )

    assert actual.signature is not None
    changed = replace(actual, signature=replace(actual.signature, returns="str"))
    after = compare_graphs(
        replace(
            observed,
            entities=tuple(changed if item.id == actual.id else item for item in observed.entities),
        ),
        target,
    )
    assert any(
        item.subject_id == wanted.id and item.aspect == "signature" and item.status == "FAIL"
        for item in after.assessments
    )
    assert _target() == target


def test_own_target_distinguishes_a_field_from_its_value_binding(self_observation: Observation):
    target = _target()
    model = self_observation
    observed = observed_graph(model)
    name = "archkeel.ir.architecture_graph.Entity.visibility"
    wanted = next(item for item in target.entities if item.qualified_name == name)
    assert {item.kind for item in observed.entities if item.qualified_name == name} == {
        "attribute",
        "binding",
    }
    comparison = compare_graphs(observed, target)
    assert any(
        item.subject_id == wanted.id and item.aspect == "existence" and item.status == "PASS"
        for item in comparison.assessments
    )
    field = next(
        item
        for item in observed.entities
        if item.qualified_name == name and item.kind == "attribute"
    )
    duplicate = replace(field, id=field.id + ":duplicate")
    ambiguous = compare_graphs(replace(observed, entities=observed.entities + (duplicate,)), target)
    assert any(
        item.subject_id == wanted.id
        and item.aspect == "existence"
        and item.status == "UNKNOWN"
        and item.change == "ambiguous"
        for item in ambiguous.assessments
    )
    wrong_kind = compare_graphs(
        replace(
            observed, entities=tuple(item for item in observed.entities if item.id != field.id)
        ),
        target,
    )
    assert any(
        item.subject_id == wanted.id and item.aspect == "kind" and item.status == "FAIL"
        for item in wrong_kind.assessments
    )


def test_own_graph_observes_the_normalizer_and_classifier_relationship_validator(self_observation):
    graph = observed_graph(self_observation)
    classifier = next(
        entity
        for entity in graph.entities
        if entity.qualified_name == "archkeel.ir.architecture_graph.ArchitectureGraph"
    )
    methods = {
        entity.qualified_name.rsplit(".", 1)[-1]
        for entity in graph.entities
        if entity.parent_id == classifier.id and entity.kind == "method"
    }
    assert methods == OBSERVED_GRAPH_METHODS
