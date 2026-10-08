# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Flutter shop Target is independently authored before its source."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from archkeel.ir.codec import load_inside_contract_tree, parse_contract
from archkeel.ir.target_graph import declared_tree_graph

FIXTURE = Path(__file__).parents[1] / "fixtures" / "I-flutter-shop"
ROOT_CONTRACT = "architecture-contract.json"
PROVENANCE = ("docs/target.md",)

EXPECTED_MODULES = {
    "lib/main.dart",
    "lib/app/shop_app.dart",
    "lib/presentation/shopping/catalog/catalog_page.dart",
    "lib/presentation/shopping/catalog/catalog_view_model.dart",
    "lib/presentation/shopping/cart/cart_page.dart",
    "lib/presentation/shopping/cart/cart_view_model.dart",
    "lib/presentation/orders/orders_page.dart",
    "lib/presentation/orders/order_detail_page.dart",
    "lib/presentation/orders/orders_view_model.dart",
    "lib/domain/catalog/product.dart",
    "lib/domain/catalog/catalog_repository.dart",
    "lib/domain/cart/cart.dart",
    "lib/domain/orders/order.dart",
    "lib/domain/orders/order_repository.dart",
    "lib/domain/checkout/place_order.dart",
    "lib/domain/checkout/shop_status.dart",
    "lib/data/repositories/cached_catalog_repository.dart",
    "lib/data/repositories/memory_order_repository.dart",
    "lib/data/services/demo_backend.dart",
    "lib/data/services/memory_store.dart",
    "lib/state/async_state.dart",
}

TARGET_CONTRACTS = (
    ROOT_CONTRACT,
    "contracts/presentation.json",
    "contracts/shopping.json",
    "contracts/domain.json",
    "contracts/data.json",
    "contracts/state.json",
)


def _target():
    payload = (FIXTURE / ROOT_CONTRACT).read_bytes()
    contract = parse_contract(json.loads(payload))

    def read(relative: str) -> tuple[bytes, str]:
        return (FIXTURE / relative).read_bytes(), relative

    tree = load_inside_contract_tree(
        ROOT_CONTRACT,
        contract,
        hashlib.sha256(payload).hexdigest(),
        ROOT_CONTRACT,
        read,
    )
    graph = declared_tree_graph(tree, root_path=ROOT_CONTRACT)
    graph.validate()
    return tree, graph


def test_flutter_target_has_agent_owned_responsibilities_and_closed_permissions() -> None:
    _target()
    for relative in TARGET_CONTRACTS:
        payload = json.loads((FIXTURE / relative).read_text(encoding="utf-8"))
        assert payload["components"]
        assert all(
            component["responsibilities"]
            and component["provenance"] == list(PROVENANCE)
            and component["decided_by"] == "agent"
            for component in payload["components"]
        )
        assert [rule["kind"] for rule in payload["rules"]] == ["complete_requires"]
        assert all(
            rule["provenance"] == list(PROVENANCE) and rule["decided_by"] == "agent"
            for rule in payload["rules"]
        )
        assert all(
            requirement["rationale"] and requirement["decided_by"] == "agent"
            for component in payload["components"]
            for requirement in component.get("requires", [])
        )


def test_flutter_target_owns_three_meaningful_component_levels_and_all_modules() -> None:
    _target()
    root = json.loads((FIXTURE / ROOT_CONTRACT).read_text(encoding="utf-8"))
    presentation = json.loads((FIXTURE / "contracts/presentation.json").read_text(encoding="utf-8"))
    shopping = json.loads((FIXTURE / "contracts/shopping.json").read_text(encoding="utf-8"))
    assert {item["id"] for item in root["components"]} >= {
        "composition",
        "presentation",
        "domain",
        "data",
        "state",
    }
    assert {item["id"] for item in presentation["components"]} >= {"shopping", "orders"}
    assert {item["id"] for item in shopping["components"]} >= {"catalog", "cart"}

    _, graph = _target()
    entities = {item.id: item for item in graph.entities}
    modules = {item.file_path: item for item in graph.entities if item.kind == "module"}
    assert set(modules) == EXPECTED_MODULES
    assert len(modules) == len(EXPECTED_MODULES)
    for module in modules.values():
        assert module.parent_id in entities
        assert entities[module.parent_id].kind == "component"
        assert any(
            child.parent_id == module.id and child.kind != "module" for child in graph.entities
        )


def test_flutter_target_pins_journey_signatures_member_scopes_and_flutter_inheritance() -> None:
    _, graph = _target()
    entities = {item.id: item for item in graph.entities}
    names = {item.qualified_name: item for item in entities.values()}
    relations = {
        (
            edge.kind,
            entities[edge.source_id].qualified_name,
            entities[edge.target_id].qualified_name,
        )
        for edge in graph.relationships
    }

    assert "shop.domain.cart.cart.Cart.totalCents" in names
    assert names["shop.domain.cart.cart.CartLine.quantity"].annotation == "int"
    assert (
        names["shop.domain.checkout.place_order.PlaceOrder.call"].signature.returns
        == "Future<Order>"
    )
    assert (
        names[
            "shop.presentation.orders.orders_view_model.OrdersViewModel.findById"
        ].signature.returns
        == "Future<Order?>"
    )
    assert names["shop.domain.orders.order.Order.status"].annotation == "OrderStatus"
    assert names["shop.state.async_state.AsyncState.value"].annotation == "T?"
    assert names["shop.domain.orders.order.OrderStatus.placed"].kind == "enum_literal"
    for port in (
        "shop.domain.catalog.catalog_repository.CatalogRepository",
        "shop.domain.orders.order_repository.OrderRepository",
        "shop.domain.checkout.shop_status.ShopStatus",
    ):
        assert any(
            entity.qualified_name == port and entity.kind == "interface"
            for entity in graph.entities
        )
    assert names["shop.state.async_state.AsyncState.AsyncState"].signature.returns == "AsyncState"
    assert names["shop.domain.orders.order.Order.Order"].signature.returns == "Order"
    assert names["shop.app.shop_app.ShopApp.createState"].signature.returns == "State<ShopApp>"
    assert names["shop.app.shop_app._ShopAppState.dispose"].signature.returns == "void"
    assert (
        names["shop.data.services.memory_store.MemoryStore.dispose"].signature.returns
        == "Future<void>"
    )

    assert (
        names[
            "shop.presentation.shopping.catalog.catalog_view_model.CatalogViewModel.state"
        ].signature.returns
        == "AsyncState<List<Product>>"
    )
    assert (
        names[
            "shop.presentation.shopping.catalog.catalog_view_model.CatalogViewModel.isOnline"
        ].signature.returns
        == "bool"
    )
    assert (
        names[
            "shop.presentation.shopping.cart.cart_view_model.CartViewModel.lines"
        ].signature.returns
        == "List<CartLine>"
    )
    assert (
        names[
            "shop.presentation.shopping.cart.cart_view_model.CartViewModel.totalCents"
        ].signature.returns
        == "int"
    )
    assert (
        names[
            "shop.presentation.shopping.cart.cart_view_model.CartViewModel.isPlacingOrder"
        ].signature.returns
        == "bool"
    )
    assert (
        names[
            "shop.presentation.shopping.cart.cart_view_model.CartViewModel.state"
        ].signature.returns
        == "AsyncState<Order>"
    )
    assert (
        names["shop.presentation.orders.orders_view_model.OrdersViewModel.state"].signature.returns
        == "AsyncState<List<Order>>"
    )

    for classifier in (
        "shop.domain.catalog.product.Product",
        "shop.domain.cart.cart.Cart",
        "shop.domain.cart.cart.CartLine",
        "shop.domain.orders.order.Order",
        "shop.domain.orders.order.OrderLine",
        "shop.domain.orders.order.OrderStatus",
        "shop.state.async_state.AsyncState",
        "shop.app.shop_app.ShopApp",
        "shop.app.shop_app._ShopAppState",
        "shop.data.services.memory_store.MemoryStore",
    ):
        assert any(
            scope.scope_id == names[classifier].id and scope.mode == "closed"
            for scope in graph.target_scopes
        )

    assert (
        "calls",
        "shop.presentation.shopping.cart.cart_page.CartPage.build",
        "shop.presentation.shopping.cart.cart_view_model.CartViewModel.checkout",
    ) in relations
    expected_journey_edges = {
        (
            "creates",
            "shop.main.main",
            "shop.app.shop_app.ShopApp",
        ),
        (
            "creates",
            "shop.app.shop_app._ShopAppState.build",
            "shop.presentation.shopping.catalog.catalog_page.CatalogPage",
        ),
        (
            "creates",
            "shop.app.shop_app._ShopAppState.build",
            "shop.presentation.shopping.cart.cart_page.CartPage",
        ),
        (
            "creates",
            "shop.app.shop_app._ShopAppState.build",
            "shop.presentation.orders.orders_page.OrdersPage",
        ),
        (
            "creates",
            "shop.app.shop_app.ShopApp.createState",
            "shop.app.shop_app._ShopAppState",
        ),
        (
            "inherits",
            "shop.app.shop_app.ShopApp",
            "package:flutter/widgets.dart.StatefulWidget",
        ),
        (
            "inherits",
            "shop.app.shop_app._ShopAppState",
            "package:flutter/widgets.dart.State<ShopApp>",
        ),
        (
            "calls",
            "shop.app.shop_app._ShopAppState.dispose",
            "shop.presentation.shopping.catalog.catalog_view_model.CatalogViewModel.dispose",
        ),
        (
            "calls",
            "shop.app.shop_app._ShopAppState.dispose",
            "shop.presentation.shopping.cart.cart_view_model.CartViewModel.dispose",
        ),
        (
            "calls",
            "shop.app.shop_app._ShopAppState.dispose",
            "shop.presentation.orders.orders_view_model.OrdersViewModel.dispose",
        ),
        (
            "calls",
            "shop.app.shop_app._ShopAppState.dispose",
            "shop.data.services.memory_store.MemoryStore.dispose",
        ),
        (
            "calls",
            "shop.presentation.orders.orders_view_model.OrdersViewModel.dispose",
            "dart:async.StreamSubscription.cancel",
        ),
        (
            "calls",
            "shop.data.services.memory_store.MemoryStore.dispose",
            "dart:async.StreamController.close",
        ),
        (
            "calls",
            "shop.presentation.shopping.catalog.catalog_view_model.CatalogViewModel.CatalogViewModel",
            "shop.presentation.shopping.catalog.catalog_view_model.CatalogViewModel.load",
        ),
        (
            "calls",
            "shop.presentation.shopping.cart.cart_page.CartPage.build",
            "shop.presentation.shopping.cart.cart_view_model.CartViewModel.checkout",
        ),
        (
            "references",
            "shop.presentation.shopping.catalog.catalog_page.CatalogPage.build",
            "shop.presentation.shopping.catalog.catalog_view_model.CatalogViewModel.state",
        ),
        (
            "references",
            "shop.presentation.shopping.cart.cart_page.CartPage.build",
            "shop.presentation.shopping.cart.cart_view_model.CartViewModel.lines",
        ),
        (
            "references",
            "shop.presentation.shopping.cart.cart_page.CartPage.build",
            "shop.presentation.shopping.cart.cart_view_model.CartViewModel.state",
        ),
        (
            "references",
            "shop.presentation.orders.orders_page.OrdersPage.build",
            "shop.presentation.orders.orders_view_model.OrdersViewModel.state",
        ),
        (
            "calls",
            "shop.presentation.shopping.cart.cart_view_model.CartViewModel.checkout",
            "shop.domain.checkout.place_order.PlaceOrder.call",
        ),
        (
            "calls",
            "shop.domain.checkout.place_order.PlaceOrder.call",
            "shop.domain.orders.order_repository.OrderRepository.place",
        ),
        (
            "creates",
            "shop.domain.cart.cart.Cart.add",
            "shop.domain.cart.cart.CartLine",
        ),
        (
            "calls",
            "shop.presentation.orders.orders_view_model.OrdersViewModel.load",
            "shop.domain.orders.order_repository.OrderRepository.watchAll",
        ),
        (
            "realizes",
            "shop.data.repositories.cached_catalog_repository.CachedCatalogRepository",
            "shop.domain.catalog.catalog_repository.CatalogRepository",
        ),
        (
            "inherits",
            "shop.presentation.shopping.cart.cart_view_model.CartViewModel",
            "package:flutter/foundation.dart.ChangeNotifier",
        ),
        (
            "inherits",
            "shop.presentation.shopping.catalog.catalog_page.CatalogPage",
            "package:flutter/widgets.dart.StatelessWidget",
        ),
    }
    assert expected_journey_edges <= relations
    assert (
        entities[
            next(
                item.id
                for item in graph.entities
                if item.qualified_name == "package:flutter/foundation.dart.ChangeNotifier"
            )
        ].presence
        == "referenced"
    )
