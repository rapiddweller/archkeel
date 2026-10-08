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
    composition = labels["composition"].component_id
    root_dependencies = {
        edge.target_id
        for edge in graph.relationships
        if edge.kind == "requires" and edge.source_id == composition
    }
    assert root_dependencies == {
        labels["presentation"].component_id,
        labels["ordering"].component_id,
        labels["adapters"].component_id,
    }
    names = {entity.id: entity.qualified_name for entity in entities.values()}
    assert "commerce.main.CheckoutRequest" not in names.values()
    assert any(
        edge.kind == "calls"
        and names[edge.source_id] == "commerce.main.main"
        and names[edge.target_id] == "commerce.presentation.controller.CheckoutController.submit"
        for edge in graph.relationships
    )
    assert any(
        edge.kind == "creates"
        and names[edge.source_id] == "commerce.main.main"
        and names[edge.target_id]
        == "commerce.ordering.application.checkout_service.CheckoutService"
        for edge in graph.relationships
    )
    assert any(
        edge.kind == "creates"
        and names[edge.source_id] == "commerce.main.main"
        and names[edge.target_id]
        == "commerce.adapters.memory.in_memory_order_repository.InMemoryOrderRepository"
        for edge in graph.relationships
    )
    repository_binding = next(
        entity for entity in entities.values() if entity.qualified_name.endswith("main.repository")
    )
    assert repository_binding.kind == "binding"
    assert repository_binding.parent_id == next(
        entity.id for entity in entities.values() if entity.qualified_name == "commerce.main.main"
    )
    assert repository_binding.initializer == "InMemoryOrderRepository()"
    assert any(
        edge.kind == "instance_of"
        and edge.source_id == repository_binding.id
        and names[edge.target_id]
        == "commerce.adapters.memory.in_memory_order_repository.InMemoryOrderRepository"
        for edge in graph.relationships
    )
    assert any(
        edge.kind == "inherits"
        and names[edge.source_id]
        == "commerce.ordering.domain.pricing.discount_policy.PercentageDiscount"
        and names[edge.target_id] == "commerce.ordering.domain.pricing.discount_policy.DiscountBase"
        for edge in graph.relationships
    )
    assert any(
        edge.kind == "realizes"
        and names[edge.source_id].endswith("PercentageDiscount")
        and names[edge.target_id].endswith("DiscountPolicy")
        for edge in graph.relationships
    )
    assert any(
        edge.kind == "calls"
        and names[edge.source_id].endswith("PercentageDiscount.discountCents")
        and names[edge.target_id]
        == "commerce.ordering.domain.pricing.discount_policy.DiscountBase.clampDiscount"
        for edge in graph.relationships
    )
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
    assert graph.target_scopes


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


def test_dart_private_fields_and_classifier_scopes_are_truthful():
    _, graph = _target_graph()
    entities = {entity.id: entity for entity in graph.entities}
    modules = {entity.id for entity in graph.entities if entity.kind == "module"}
    module_scopes = {
        scope.scope_id: scope for scope in graph.target_scopes if scope.scope_id in modules
    }
    assert len(module_scopes) == len(modules)
    assert all(scope.mode == "open" for scope in module_scopes.values())
    assert all("open" in scope.rationale.lower() for scope in module_scopes.values())
    assert all(set(scope.entity_kinds) == {"module"} for scope in module_scopes.values())
    assert all(
        set(scope.relationship_kinds) == {"calls", "imports"} for scope in module_scopes.values()
    )

    classifiers = {
        entity.id: entity
        for entity in graph.entities
        if entity.presence == "planned" and entity.kind in {"class", "interface", "enum"}
    }
    closed_scopes = {
        scope.scope_id: scope for scope in graph.target_scopes if scope.mode == "closed"
    }
    assert closed_scopes.keys() == classifiers.keys()
    for classifier_id, scope in closed_scopes.items():
        direct_member_kinds = {
            entity.kind
            for entity in graph.entities
            if entity.parent_id == classifier_id
            and entity.kind in {"attribute", "method", "enum_literal"}
        }
        assert set(scope.entity_kinds) == direct_member_kinds
        assert not scope.relationship_kinds

    percent = next(
        entity
        for entity in graph.entities
        if entity.qualified_name.endswith("PercentageDiscount._percent")
    )
    assert percent.visibility.kind == "private"
    assert percent.qualified_name.endswith("._percent")
    assert all(
        entity.qualified_name.rsplit(".", 1)[-1].startswith("_")
        for entity in graph.entities
        if entity.visibility.kind == "private"
    )
    discount_ctor = next(
        entity
        for entity in graph.entities
        if entity.qualified_name.endswith("PercentageDiscount.PercentageDiscount")
    )
    assert [
        (item.name, item.kind, item.default) for item in discount_ctor.signature.parameters
    ] == [("percent", "keyword_only", "0")]
    request = next(
        entity for entity in graph.entities if entity.qualified_name.endswith("CheckoutRequest")
    )
    constructor = next(
        entity
        for entity in graph.entities
        if entity.qualified_name.endswith("CheckoutRequest.CheckoutRequest")
    )
    assert constructor.parent_id == request.id
    assert [(item.name, item.annotation) for item in constructor.signature.parameters] == [
        ("requestId", "String"),
        ("lines", "List<OrderLine>"),
    ]
    assert constructor.signature.returns == "CheckoutRequest"
    request_fields = {
        entity.qualified_name.rsplit(".", 1)[-1]: entity
        for entity in graph.entities
        if entity.parent_id == request.id
    }
    assert set(request_fields) == {"requestId", "lines", "CheckoutRequest"}
    assert all(request_fields[name].kind == "attribute" for name in ("requestId", "lines"))
    assert entities["ordering:repository-field"].visibility.kind == "private"
    assert entities["presentation:checkout-field"].visibility.kind == "private"
    assert all(
        item.responsibilities
        for item in (entities["ordering:repository-field"], entities["presentation:checkout-field"])
    )
    checkout_ctor = next(
        entity
        for entity in graph.entities
        if entity.qualified_name.endswith("CheckoutService.CheckoutService")
    )
    controller_ctor = next(
        entity
        for entity in graph.entities
        if entity.qualified_name.endswith("CheckoutController.CheckoutController")
    )
    assert [item.name for item in checkout_ctor.signature.parameters] == ["repository"]
    assert [item.name for item in controller_ctor.signature.parameters] == ["checkout"]


def test_multicomponent_target_scopes_decide_all_dependency_pairs():
    expected = {
        "architecture-contract.json": {
            "presentation": {"ordering"},
            "ordering": set(),
            "adapters": {"ordering"},
            "composition": {"presentation", "ordering", "adapters"},
        },
        "contracts/ordering.json": {
            "application": {"domain", "ports"},
            "ports": {"domain"},
            "domain": set(),
        },
        "contracts/domain.json": {"orders": set(), "pricing": {"orders"}},
        "contracts/adapters.json": {"memory": set(), "diagnostics": set()},
    }
    expected_through = {
        "architecture-contract.json": {
            "presentation": {
                "ordering": ("commerce.ordering.application", "commerce.ordering.domain.orders")
            },
            "ordering": {},
            "adapters": {
                "ordering": ("commerce.ordering.ports", "commerce.ordering.domain.orders")
            },
            "composition": {
                "presentation": ("commerce.presentation.controller",),
                "ordering": ("commerce.ordering.application", "commerce.ordering.domain.orders"),
                "adapters": ("commerce.adapters.memory",),
            },
        },
        "contracts/ordering.json": {
            "application": {
                "domain": (
                    "commerce.ordering.domain.orders.order",
                    "commerce.ordering.domain.pricing.discount_policy",
                ),
                "ports": ("commerce.ordering.ports.order_repository",),
            },
            "ports": {"domain": ("commerce.ordering.domain.orders.order",)},
            "domain": {},
        },
        "contracts/domain.json": {
            "orders": {},
            "pricing": {"orders": ("commerce.ordering.domain.orders.order",)},
        },
        "contracts/adapters.json": {"memory": {}, "diagnostics": {}},
    }
    for path, expected_requires in expected.items():
        contract = parse_contract(json.loads((FIXTURE / path).read_text()))
        components = {item.label: item for item in contract.components}
        assert set(components) == set(expected_requires)
        assert len(contract.components) > 1
        assert [rule.id for rule in contract.rules if rule.kind == "complete_requires"] == [
            "REQUIRES-COMPLETE"
        ]
        assert all(
            rule.provenance == (PROVENANCE,) and rule.decided_by == "architect"
            for rule in contract.rules
            if rule.kind == "complete_requires"
        )
        for source, expected_targets in expected_requires.items():
            requires = components[source].requires or ()
            assert {entry.component for entry in requires} == expected_targets
            for entry in requires:
                assert entry.rationale and entry.decided_by == "architect"
                assert entry.through == expected_through[path][source][entry.component]
                published_modules = {
                    item.partition(":")[0] for item in components[entry.component].public or ()
                }
                assert all(
                    any(
                        module == published or module.startswith(f"{published}.")
                        for published in published_modules
                    )
                    for module in entry.through
                )

    domain = parse_contract(json.loads((FIXTURE / "contracts/domain.json").read_text()))
    domain_components = {item.label: item for item in domain.components}
    assert {item.component for item in domain_components["orders"].requires or ()} == set()
    assert {item.component for item in domain_components["pricing"].requires or ()} == {"orders"}
    presentation = parse_contract(json.loads((FIXTURE / "contracts/presentation.json").read_text()))
    assert presentation.components[0].public == (
        "commerce.presentation.controller:CheckoutController",
    )


def test_composition_owns_only_main_and_modules_have_no_visibility():
    _, graph = _target_graph()
    contract = parse_contract(json.loads((FIXTURE / "architecture-contract.json").read_text()))
    composition = next(item for item in contract.components if item.label == "composition")
    assert composition.packages == ()
    assert composition.exact_modules == ("commerce.main",)
    assert contract.component_for("commerce.main") == composition

    modules = [entity for entity in graph.entities if entity.kind == "module"]
    assert len(modules) == 8
    contract_paths = [
        FIXTURE / "architecture-contract.json",
        *sorted((FIXTURE / "contracts").glob("*.json")),
    ]
    declared_modules = [
        entity
        for path in contract_paths
        for entity in json.loads(path.read_text())
        .get("declarations", {})
        .get("uml", {})
        .get("entities", [])
        if entity["kind"] == "module"
    ]
    assert len(declared_modules) == len(modules)
    assert all("visibility" not in entity for entity in declared_modules)
    assert all(entity.visibility.kind == "unknown" for entity in modules)

    expected_through = {
        "presentation": ("commerce.presentation.controller",),
        "ordering": ("commerce.ordering.application", "commerce.ordering.domain.orders"),
        "adapters": ("commerce.adapters.memory",),
    }
    requires = {entry.component: entry.through for entry in composition.requires}
    assert requires == expected_through
    by_id = {item.id: item for item in contract.components}
    for target, paths in requires.items():
        published = {entry.partition(":")[0] for entry in by_id[target].public or ()}
        assert all(
            any(path == item or path.startswith(f"{item}.") for item in published) for path in paths
        )
