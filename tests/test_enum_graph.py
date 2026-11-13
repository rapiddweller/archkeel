# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Enum literals need measured identities, not a guess from every class assignment."""

from dataclasses import replace

import pytest

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    Coverage,
    Entity,
    TargetDefinition,
    TargetScope,
)
from archkeel.ir.codec import decode_json
from archkeel.ir.graph_codec import graph_bytes, parse_graph, parse_target


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
