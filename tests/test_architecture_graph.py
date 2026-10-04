# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The shared graph must retain uncertainty and reject broken references."""

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    Coverage,
    Entity,
    Parameter,
    PublicAPIEntry,
    Relationship,
    Signature,
    TargetScope,
    Visibility,
)
from archkeel.ir.model import Evidence
from tools.architecture_graph_schema import graph_schema

ROOT = Path(__file__).parents[1]
SOURCE = Evidence("source", "example.py", 1, 4, 0, "class Service: ...")


def _entity(identity: str, kind="class", **changes) -> Entity:
    return Entity(
        identity, kind, f"example.{identity}", "python", evidence_ids=("source",), **changes
    )


def _observed(*entities: Entity, relationships=(), coverage=()) -> ArchitectureGraph:
    return ArchitectureGraph("observed", entities, relationships, coverage, (SOURCE,))


def test_invalid_ancestor_is_a_validation_error_regardless_of_entity_order() -> None:
    child = _entity("child", parent_id="parent")
    parent = _entity("parent", parent_id="missing")
    for ordered in ((child, parent), (parent, child)):
        with pytest.raises(ValueError, match="unknown lexical parent"):
            _observed(*ordered).validate()


@pytest.mark.parametrize(
    "changes",
    [
        {"id": ""},
        {"selector": " "},
        {"provenance": ()},
        {"provenance": (" ",)},
    ],
)
def test_global_public_api_intent_requires_identity_selector_and_independent_provenance(changes):
    entry = PublicAPIEntry("api", "example:Service", ("target.md",))
    with pytest.raises(ValueError):
        ArchitectureGraph("declared", public_api=(replace(entry, **changes),)).validate()


def test_global_api_selectors_are_not_source_entities_or_language_visibility():
    from archkeel.ir.graph_codec import graph_bytes, parse_graph

    entry = PublicAPIEntry("api", "example:Future", ("target.md",))
    graph = ArchitectureGraph("declared", public_api=(entry,))
    graph.validate()
    assert not graph.entities and not graph.relationships
    assert parse_graph(json.loads(graph_bytes(graph))) == graph
    Draft202012Validator(graph_schema()).validate(json.loads(graph_bytes(graph)))
    with pytest.raises(ValueError, match="declared graph"):
        ArchitectureGraph("observed", public_api=(entry,)).validate()
    with pytest.raises(ValueError, match="identity"):
        ArchitectureGraph(
            "declared", public_api=(entry, replace(entry, selector="example:Other"))
        ).validate()
    with pytest.raises(ValueError, match="selector"):
        ArchitectureGraph("declared", public_api=(entry, replace(entry, id="other"))).validate()
    entity = Entity("api", "class", "example.Service", "python", provenance=("target.md",))
    with pytest.raises(ValueError, match="identity"):
        ArchitectureGraph("declared", (entity,), public_api=(entry,)).validate()
    wire = json.loads(graph_bytes(graph))
    wire["public_api"][0]["visibility"] = "public"
    with pytest.raises(ValueError, match="fields mismatch"):
        parse_graph(wire)


def test_qualified_names_are_not_identity_overloads_and_package_initializers_survive() -> None:
    module = _entity("module", "module")
    package = replace(module, id="package", kind="package")
    overload = _entity("function", "function", parent_id=module.id)
    implementation = replace(overload, id="implementation")
    _observed(package, module, overload, implementation).validate()


@pytest.mark.parametrize("target", ["a", "b"])
def test_dependency_cycles_and_self_calls_are_valid(target: str) -> None:
    edge = Relationship("call", "calls", "a", target, "resolved", evidence_ids=("source",))
    _observed(_entity("a"), _entity("b"), relationships=(edge,)).validate()


@pytest.mark.parametrize(
    "changes",
    [
        {"through": ("",)},
        {"through": ("example.a", "example.a")},
        {"reason": " "},
        {"expression": "example.a"},
        {"decided_by": "unknown"},
        {"target_id": None},
    ],
)
def test_permission_metadata_is_validated_at_the_shared_boundary(changes):
    owners = tuple(
        Entity(id, "component", id, "architecture", provenance=("target.md",)) for id in ("a", "b")
    )
    permission = Relationship(
        "permission", "requires", "a", "b", reason="Use the boundary.", provenance=("target.md",)
    )
    ArchitectureGraph("declared", owners, (permission,)).validate()
    with pytest.raises(ValueError):
        ArchitectureGraph("declared", owners, (replace(permission, **changes),)).validate()


def test_import_permission_is_not_an_observed_fact_or_a_uml_completeness_kind():
    owners = tuple(
        Entity(id, "component", id, "architecture", provenance=("target.md",)) for id in ("a", "b")
    )
    permission = Relationship(
        "permission", "requires", "a", "b", reason="Use the boundary.", provenance=("target.md",)
    )
    with pytest.raises(ValueError, match="declared component endpoints"):
        ArchitectureGraph(
            "observed",
            tuple(replace(owner, evidence_ids=(SOURCE.id,), provenance=()) for owner in owners),
            (permission,),
            evidence=(SOURCE,),
        ).validate()
    noncomponent = replace(owners[1], kind="class")
    with pytest.raises(ValueError, match="declared component endpoints"):
        ArchitectureGraph("declared", (owners[0], noncomponent), (permission,)).validate()
    with pytest.raises(ValueError, match="existing Core rules"):
        ArchitectureGraph(
            "declared",
            owners,
            (permission,),
            target_scopes=(
                TargetScope(
                    "a",
                    "closed",
                    "Keep policy explicit.",
                    ("target.md",),
                    relationship_kinds=("requires",),
                ),
            ),
        ).validate()
    with pytest.raises(ValueError, match="metadata belongs on requires"):
        ArchitectureGraph(
            "declared", owners, (replace(permission, kind="imports", through=("a",)),)
        ).validate()


@pytest.mark.parametrize(
    "edge",
    [
        Relationship("call", "calls", "a", "missing", "resolved", evidence_ids=("source",)),
        Relationship("call", "calls", "missing", "a", "resolved", evidence_ids=("source",)),
        Relationship(
            "call", "calls", "a", "b", "partial", expression="value.run", evidence_ids=("source",)
        ),
        Relationship(
            "call",
            "calls",
            "a",
            resolution="resolved",
            expression="value.run",
            evidence_ids=("source",),
        ),
        Relationship(
            "call",
            "calls",
            "a",
            resolution="partial",
            candidate_ids=("missing",),
            expression="value.run",
            evidence_ids=("source",),
        ),
    ],
)
def test_invalid_relationship_endpoints_never_validate(edge: Relationship) -> None:
    with pytest.raises(ValueError):
        _observed(_entity("a"), _entity("b"), relationships=(edge,)).validate()


def test_lexical_cycles_are_invalid() -> None:
    with pytest.raises(ValueError, match="lexical containment cycle"):
        _observed(_entity("a", parent_id="b"), _entity("b", parent_id="a")).validate()


def test_partial_candidates_keep_their_resolution_limits() -> None:
    edge = Relationship(
        "call",
        "calls",
        "a",
        resolution="partial",
        candidate_ids=("b",),
        expression="value.run",
        evidence_ids=("source",),
        candidate_count=3,
        candidates_truncated=True,
        reason="runtime receiver unknown",
    )
    graph = _observed(_entity("a"), _entity("b"), relationships=(edge,))
    graph.validate()
    payload = asdict(graph)["relationships"][0]
    assert payload["target_id"] is None
    assert payload["candidate_ids"] == ("b",)
    assert payload["candidate_count"] == 3
    assert payload["candidates_truncated"] is True
    assert payload["reason"] == "runtime receiver unknown"


def test_truncated_definition_candidates_may_have_an_unknown_total() -> None:
    edge = Relationship(
        "call",
        "calls",
        "a",
        resolution="partial",
        candidate_ids=("b",),
        expression="value.run",
        evidence_ids=("source",),
        candidates_truncated=True,
        reason="omitted qualified names may each represent several definitions",
    )
    _observed(_entity("a"), _entity("b"), relationships=(edge,)).validate()
    assert edge.candidate_count is None


def test_visibility_and_signature_are_the_same_shape_for_independent_target() -> None:
    owner = _entity("Service")
    method = _entity(
        "run",
        "method",
        parent_id=owner.id,
        visibility=Visibility("public", "convention", "run"),
        signature=Signature((Parameter("limit", "int", "keyword_only", "10", True),), "str"),
    )
    source = _observed(owner, method)
    target = ArchitectureGraph(
        "declared",
        (
            Entity(
                "expected-service",
                "class",
                "example.Service",
                "python",
                provenance=("contract.json#/service",),
            ),
            Entity(
                "expected-run",
                "method",
                "example.Service.run",
                "python",
                parent_id="expected-service",
                visibility=Visibility("public", "declared"),
                signature=Signature(
                    (Parameter("limit", "int", "keyword_only", "10", True),), "str"
                ),
                provenance=("contract.json#/service/run",),
            ),
        ),
    )
    for graph in (source, target):
        graph.validate()
        Draft202012Validator(graph_schema()).validate(json.loads(json.dumps(asdict(graph))))
    assert target.entities[1].signature == method.signature


@pytest.mark.parametrize(
    "change",
    [
        {"evidence_ids": ()},
        {"evidence_ids": ("missing",)},
        {"signature": Signature()},
        {"parent_id": "a"},
    ],
)
def test_invalid_entities_never_validate(change: dict) -> None:
    with pytest.raises(ValueError):
        _observed(replace(_entity("a"), **change)).validate()


def test_method_requires_its_lexical_classifier() -> None:
    with pytest.raises(ValueError, match="method without a classifier"):
        _observed(_entity("run", "method")).validate()


def test_declared_edges_cannot_turn_source_candidates_into_confirmed_intent() -> None:
    entities = tuple(
        replace(_entity(i), evidence_ids=(), provenance=("contract.json",)) for i in ("a", "b")
    )
    edge = Relationship("call", "calls", "a", "b", "resolved", provenance=("contract.json",))
    with pytest.raises(ValueError, match="Target does not assert observed resolution"):
        ArchitectureGraph("declared", entities, (edge,)).validate()


def test_target_requires_independent_provenance() -> None:
    with pytest.raises(ValueError, match="Target needs independent provenance"):
        ArchitectureGraph("declared", (replace(_entity("a"), evidence_ids=()),)).validate()


def test_partial_coverage_needs_a_reason() -> None:
    with pytest.raises(ValueError, match="limited coverage needs a reason"):
        _observed(
            _entity("scope", "module"), coverage=(Coverage("scope", status="partial"),)
        ).validate()


def test_schema_is_generated_from_the_model() -> None:
    schema = graph_schema()
    Draft202012Validator.check_schema(schema)
    assert json.loads((ROOT / "schema/architecture-graph.schema.json").read_bytes()) == schema


@pytest.mark.parametrize(
    "path, value",
    [
        (("schema_version",), "99"),
        (("entities", 0, "kind"), "widget"),
        (("entities", 0, "visibility", "kind"), "internalish"),
        (("entities", 0, "extra"), True),
        (("evidence", 0, "line"), True),
    ],
)
def test_schema_rejects_malformed_wire_values(path: tuple, value: object) -> None:
    raw = json.loads(json.dumps(asdict(_observed(_entity("a")))))
    parent = raw
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    assert list(Draft202012Validator(graph_schema()).iter_errors(raw))
