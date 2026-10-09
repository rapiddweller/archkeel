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
