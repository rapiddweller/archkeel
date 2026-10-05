# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Enum literals need measured identities, not a guess from every class assignment."""

from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator
from test_member_inventory import _observation

from archkeel.check.uml_compare import compare_graphs
from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    Coverage,
    Entity,
    TargetDefinition,
    TargetScope,
)
from archkeel.ir.codec import decode_json
from archkeel.ir.graph_codec import graph_bytes, parse_graph, parse_target
from archkeel.ir.source_graph import observed_graph
from tools.architecture_graph_schema import graph_schema


def _target():
    context = {"presence": "planned", "provenance": ("target.md",)}
    return ArchitectureGraph(
        "declared",
        (
            Entity("module", "module", "sample.model", "python", **context),
            Entity("enum", "enum", "sample.model.State", "python", "module", **context),
            Entity(
                "ready", "enum_literal", "sample.model.State.READY", "python", "enum", **context
            ),
        ),
        target_scopes=(
            TargetScope(
                "enum", "closed", "All intended literals.", ("target.md",), ("enum_literal",)
            ),
        ),
    )


def test_literal_enum_members_keep_the_field_site_without_static_attribute_notation(tmp_path):
    observed = observed_graph(
        _observation(
            tmp_path,
            "from enum import StrEnum\nclass State(StrEnum):\n READY = 'ready'\n OTHER = 'other'\n",
        )
    )
    literals = [e for e in observed.entities if e.kind == "enum_literal"]
    assert {e.qualified_name.rsplit(".", 1)[-1] for e in literals} == {"READY", "OTHER"}
    assert all(
        e.parent_id and e.evidence_ids and e.record_ids and not e.modifiers for e in literals
    )
    assert not any(e.kind == "attribute" for e in observed.entities)
    assert parse_graph(decode_json(graph_bytes(observed))) == observed
    Draft202012Validator(graph_schema()).validate(decode_json(graph_bytes(observed)))
    comparison = compare_graphs(observed, _target())
    assert any(
        a.subject_id == "ready" and a.aspect == "existence" and a.status == "PASS"
        for a in comparison.assessments
    )
    assert any(
        a.subject_id == "enum" and a.aspect == "completeness" and a.status == "FAIL"
        for a in comparison.assessments
    )


@pytest.mark.parametrize(
    "body",
    [
        " READY = auto()\n",
        " _ignore_ = 'READY'\n READY = 'ready'\n",
        " READY = 'ready'\n READY = 'replaced'\n",
    ],
)
def test_unproven_enum_members_remain_unknown_instead_of_a_wrong_kind_failure(tmp_path, body):
    observed = observed_graph(
        _observation(tmp_path, "from enum import Enum, auto\nclass State(Enum):\n" + body)
    )
    assert not any(e.kind == "enum_literal" for e in observed.entities)
    comparison = compare_graphs(observed, _target())
    assert {a.status for a in comparison.assessments if a.subject_id == "ready"} == {"UNKNOWN"}
    assert {
        a.status
        for a in comparison.assessments
        if a.subject_id == "enum" and a.aspect == "completeness"
    } == {"UNKNOWN"}


def test_an_actual_operation_cannot_pass_as_an_enum_literal(tmp_path):
    observed = observed_graph(
        _observation(
            tmp_path, "from enum import Enum\nclass State(Enum):\n def READY(self): pass\n"
        )
    )
    comparison = compare_graphs(observed, _target())
    assert any(
        a.subject_id == "ready" and a.aspect == "kind" and a.status == "FAIL"
        for a in comparison.assessments
    )


@pytest.mark.parametrize("parent_kind", [None, "class", "module"])
def test_enum_literal_needs_its_enumeration_parent(parent_kind):
    target = _target()
    entities = tuple(
        replace(e, kind=parent_kind)
        if e.id == "enum" and parent_kind
        else replace(e, parent_id=None)
        if e.id == "ready" and parent_kind is None
        else e
        for e in target.entities
    )
    with pytest.raises(ValueError, match="enum literal"):
        replace(target, entities=entities).validate()


def test_enum_literal_rejects_operation_modifiers():
    target = _target()
    with pytest.raises(ValueError, match="enum literal"):
        replace(
            target,
            entities=tuple(
                replace(e, modifiers=("static",)) if e.id == "ready" else e for e in target.entities
            ),
        ).validate()


def test_legacy_graph_and_target_versions_roundtrip_without_silent_upgrade():
    graph = ArchitectureGraph("declared", schema_version="1.0.0")
    assert parse_graph(decode_json(graph_bytes(graph))) == graph
    assert parse_target({"schema_version": "1.0.0"}) == TargetDefinition(schema_version="1.0.0")


@pytest.mark.parametrize("part", ["entities", "scopes", "coverage"])
def test_enum_vocabulary_cannot_be_encoded_as_graph_version_one(part):
    target = _target()
    if part == "entities":
        graph = replace(target, target_scopes=(), schema_version="1.0.0")
    elif part == "scopes":
        graph = replace(target, entities=target.entities[:2], schema_version="1.0.0")
    else:
        graph = replace(
            target,
            entities=target.entities[:2],
            target_scopes=(),
            coverage=(
                Coverage("enum", ("enum_literal",), status="partial", reason="Not exhaustive."),
            ),
            schema_version="1.0.0",
        )
    with pytest.raises(ValueError, match="enum literal.*1.1.0"):
        graph.validate()


def test_target_codec_rejects_new_vocabulary_under_the_old_version():
    data = decode_json(graph_bytes(_target()))
    for key in tuple(data):
        if key not in {"entities", "relationships", "schema_version"}:
            del data[key]
    data["schema_version"] = "1.0.0"
    with pytest.raises(ValueError, match="enum literal.*1.1.0"):
        parse_target(data)
