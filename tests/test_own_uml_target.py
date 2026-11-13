# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The own graph boundary has independent, testable UML intent."""

import json
from pathlib import Path

from archkeel.ir.codec import parse_contract
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
