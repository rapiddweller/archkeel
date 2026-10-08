# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Dart checkout Target is authored independently of observed source facts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from archkeel.ir.codec import load_inside_contract_tree, parse_contract
from archkeel.ir.target_graph import declared_graph, declared_tree_graph

FIXTURE = Path(__file__).parents[1] / "fixtures" / "H-uml-dart"
PROVENANCE = "docs/target.md"


def _target_graph():
    path = "architecture-contract.json"
    payload = (FIXTURE / path).read_bytes()
    contract = parse_contract(json.loads(payload))

    def read(relative: str) -> tuple[bytes, str]:
        return (FIXTURE / relative).read_bytes(), relative

    tree = load_inside_contract_tree(
        path, contract, hashlib.sha256(payload).hexdigest(), path, read
    )
    return tree, declared_tree_graph(tree, root_path=path)


def test_checkout_target_owns_three_nested_levels_and_independent_uml_intent():
    config = (FIXTURE / "archkeel.toml").read_text()
    package = (FIXTURE / "pubspec.yaml").read_text()
    tree, graph = _target_graph()

    assert 'namespace = "commerce"' in config
    assert "name: commerce" in package
    assert not tree.issues
    assert len(tree.mounts) >= 3
    components = {intent.component_id: intent for intent in graph.component_intents}
    labels = {intent.label: intent for intent in components.values()}
    assert labels["ordering"].parent_id is None
    assert labels["domain"].parent_id == labels["ordering"].component_id
    assert labels["orders"].parent_id == labels["domain"].component_id
    assert {
        intent.label
        for intent in components.values()
        if intent.parent_id == labels["ordering"].component_id
    } >= {
        "application",
        "ports",
        "domain",
    }
    assert {
        intent.label
        for intent in components.values()
        if intent.parent_id == labels["domain"].component_id
    } >= {
        "orders",
        "pricing",
    }
    assert any(
        edge.kind == "requires"
        and edge.source_id == labels["pricing"].component_id
        and edge.target_id == labels["orders"].component_id
        for edge in graph.relationships
    )

    entities = {entity.id: entity for entity in graph.entities}
    assert "commerce.ordering.domain.orders.order.Order.status" in {
        entity.qualified_name for entity in entities.values()
    }
    modules = {
        entity.file_path: entity.qualified_name
        for entity in entities.values()
        if entity.kind == "module"
    }
    expected_modules = dict(
        (
            ("lib/main.dart", "commerce.main"),
            ("lib/presentation/controller.dart", "commerce.presentation.controller"),
            (
                "lib/ordering/application/checkout_service.dart",
                "commerce.ordering.application.checkout_service",
            ),
            (
                "lib/ordering/ports/order_repository.dart",
                "commerce.ordering.ports.order_repository",
            ),
            ("lib/ordering/domain/orders/order.dart", "commerce.ordering.domain.orders.order"),
            (
                "lib/ordering/domain/pricing/discount_policy.dart",
                "commerce.ordering.domain.pricing.discount_policy",
            ),
            (
                "lib/adapters/memory/in_memory_order_repository.dart",
                "commerce.adapters.memory.in_memory_order_repository",
            ),
            (
                "lib/adapters/diagnostics/receipt_formatter.dart",
                "commerce.adapters.diagnostics.receipt_formatter",
            ),
        )
    )
    assert modules == expected_modules
    order_ctor = next(
        entity for entity in entities.values() if entity.qualified_name.endswith("Order.Order")
    )
    assert order_ctor.signature.parameters[0].name == "id"
    assert order_ctor.signature.parameters[1].default == "const []"
    assert any(
        edge.kind == "realizes"
        and entities[edge.source_id].qualified_name.endswith("InMemoryOrderRepository")
        and entities[edge.target_id].qualified_name.endswith("OrderRepository")
        for edge in graph.relationships
    )
    for entity in entities.values():
        if entity.kind == "component":
            assert entity.responsibilities and entity.provenance == (PROVENANCE,)
        else:
            assert entity.responsibilities and entity.provenance == (PROVENANCE,)
    for edge in graph.relationships:
        assert edge.source_id in entities
        assert edge.target_id in entities
        assert edge.provenance == (PROVENANCE,)
    assert graph.target_scopes and all(scope.mode == "closed" for scope in graph.target_scopes)
    assert all(not scope.relationship_kinds for scope in graph.target_scopes)


def test_checkout_target_rejects_an_unowned_uml_endpoint():
    payload = json.loads((FIXTURE / "contracts" / "domain.json").read_text())
    payload["declarations"]["uml"]["relationships"][0]["target_id"] = "missing-classifier"
    with pytest.raises(ValueError, match="unknown relationship target"):
        declared_graph(parse_contract(payload)).validate()


def test_checkout_target_rejects_a_member_mounted_under_its_module():
    payload = json.loads((FIXTURE / "contracts" / "domain.json").read_text())
    member = next(
        item for item in payload["declarations"]["uml"]["entities"] if item["id"] == "order-id"
    )
    member["parent_id"] = "order-module"
    with pytest.raises(ValueError, match="planned attribute without a classifier"):
        declared_graph(parse_contract(payload)).validate()
