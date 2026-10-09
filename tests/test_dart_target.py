# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Dart intent composes with the shared protocol Target without redefining it."""

import hashlib
import json
from pathlib import Path

from archkeel.ir.codec import load_inside_contract_tree, parse_contract
from archkeel.ir.target_graph import declared_tree_graph

ROOT = Path(__file__).parents[1]


def test_dart_target_links_the_canonical_source_protocol():
    path = "architecture-contract.json"
    raw = (ROOT / path).read_bytes()
    tree = load_inside_contract_tree(
        path,
        parse_contract(json.loads(raw)),
        hashlib.sha256(raw).hexdigest(),
        path,
        lambda relative: ((ROOT / relative).read_bytes(), relative),
    )
    graph = declared_tree_graph(tree, root_path=path)
    assert not tree.issues
    assert not graph.evidence
    names = (
        "archkeel.ir.facts.SourceFacts",
        "archkeel.ir.protocol.CollectionRequest",
        "archkeel.ir.facts.ResolutionInput",
    )
    for name in names:
        matches = [entity for entity in graph.entities if entity.qualified_name == name]
        assert len(matches) == 1
        assert matches[0].presence == "planned"


def test_dart_target_declares_signature_member_and_scope_boundaries():
    contract = json.loads((ROOT / "docs/architecture/contracts/dart.json").read_text())
    uml = contract["declarations"]["uml"]
    entities = {entity["qualified_name"]: entity for entity in uml["entities"]}
    relationships = {(item["source_id"], item["target_id"]) for item in uml["relationships"]}

    assert entities["archkeel.analyzer.dart.parse.Parameter"]["kind"] == "class"
    assert entities["archkeel.analyzer.dart.parse.Member"]["kind"] == "class"
    for dto, fields in {
        "Definition": {
            "name",
            "kind",
            "span",
            "visibility",
            "members",
            "parameters",
            "return_type",
            "extends",
            "with_types",
            "implements",
            "enum_member_spans",
        },
        "Member": {
            "name",
            "kind",
            "span",
            "annotation",
            "return_type",
            "parameters",
            "static",
            "abstract",
            "factory",
            "constant",
            "initializer",
            "redirect",
        },
        "Parameter": {
            "name",
            "annotation",
            "kind",
            "default",
            "default_known",
            "optional",
            "required",
            "field_formal",
            "super_formal",
            "span",
        },
        "Directive": {
            "kind",
            "span",
            "target",
            "prefix",
            "deferred",
            "alternatives",
            "combinators",
        },
        "Site": {
            "kind",
            "expression",
            "expression_source",
            "span",
            "name",
            "receiver",
            "scope",
            "scope_span",
            "scope_depth",
            "use",
            "assigned_name",
            "initializer",
            "initializer_source",
        },
    }.items():
        actual = {
            entity["qualified_name"].rsplit(".", 1)[-1]
            for entity in uml["entities"]
            if entity.get("parent_id") == f"archkeel.analyzer.dart.parse.{dto}"
        }
        assert fields <= actual, f"{dto} misses fields: {sorted(fields - actual)}"

    parse = "archkeel.analyzer.dart.parse."
    for source, target in (
        ("Syntax", "Definition"),
        ("Syntax", "Directive"),
        ("Syntax", "Site"),
        ("Definition", "Member"),
        ("Definition", "Parameter"),
        ("Member", "Parameter"),
    ):
        assert (parse + source, parse + target) in relationships
    for dto in ("Definition", "Member", "Parameter", "Directive", "Site"):
        assert (parse + dto, parse + "Span") in relationships
