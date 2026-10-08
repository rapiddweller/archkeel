# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-only Flutter shop variants for the shared UML report path."""

from __future__ import annotations

from pathlib import Path

from fixtures.demo_catalog_support import Variant

FLUTTER_FIXTURE_DIR = Path(__file__).resolve().parent / "I-flutter-shop"

_ORDER = "lib/domain/orders/order.dart"
_ORDERS_VIEW_MODEL = "lib/presentation/orders/orders_view_model.dart"
_CART_PAGE = "lib/presentation/shopping/cart/cart_page.dart"


def _replace(relative: str, old: str, new: str) -> str:
    source = (FLUTTER_FIXTURE_DIR / relative).read_text()
    if source.count(old) != 1:
        raise ValueError(f"{relative}: expected one mutation anchor {old!r}")
    return source.replace(old, new, 1)


VARIANTS: tuple[Variant, ...] = (
    Variant(
        id="flutter-shop",
        section="clean",
        item="flutter:shop",
        summary="The independently Targeted Flutter shop journey: catalog, cart, checkout, and "
        "orders. Local source facts are compared through the shared UML graph; unresolved "
        "framework and inferred-type facts remain UNKNOWN.",
        files={},
        expected_violations=(),
        expected_codes=(),
        fixture=FLUTTER_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
    ),
    Variant(
        id="flutter-signature-fail",
        section="class_a",
        item="flutter:signature",
        summary="Widen OrderLine.lineTotalCents from int to num. The Dart source remains valid, "
        "but the Target's closed member signature no longer matches.",
        files={_ORDER: _replace(_ORDER, "int get lineTotalCents", "num get lineTotalCents")},
        expected_violations=(),
        expected_codes=(),
        fixture=FLUTTER_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
    ),
    Variant(
        id="flutter-missing-member-fail",
        section="class_a",
        item="flutter:member",
        summary="Remove the unused completed enum literal. The closed OrderStatus inventory "
        "reports a precise existence mismatch without breaking Dart compilation.",
        files={_ORDER: _replace(_ORDER, "  completed('Completed');", "  ;")},
        expected_violations=(),
        expected_codes=(),
        fixture=FLUTTER_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
    ),
    Variant(
        id="flutter-forbidden-dependency-fail",
        section="class_a",
        item="flutter:forbidden_dependency",
        summary="Make CartPage call the concrete DemoBackend service. The observed presentation-to-"
        "data edge violates the existing complete_requires boundary.",
        files={
            _CART_PAGE: _replace(
                _CART_PAGE,
                "import 'package:shop/presentation/shopping/cart/cart_view_model.dart';",
                "import 'package:shop/data/services/demo_backend.dart';\n"
                "import 'package:shop/presentation/shopping/cart/cart_view_model.dart';",
            ).replace(
                "        children: [\n          Expanded(",
                "        children: [\n"
                "          Text(DemoBackend().isOnline() ? 'Online' : 'Offline'),\n"
                "          Expanded(",
                1,
            )
        },
        expected_violations=(),
        expected_codes=(),
        fixture=FLUTTER_FIXTURE_DIR,
        expected_declared_rules="FAIL",
    ),
    Variant(
        id="flutter-dynamic-unknown",
        section="class_a",
        item="flutter:dynamic_dispatch",
        summary="Invoke the required order stream through a local dynamic value. The source "
        "remains valid, but static dispatch cannot prove the Target call.",
        files={
            _ORDERS_VIEW_MODEL: _replace(
                _ORDERS_VIEW_MODEL,
                "    _ordersSubscription ??= _repository.watchAll().listen(_receiveOrders);",
                "    final dynamic repository = _repository;\n"
                "    _ordersSubscription ??= repository.watchAll().listen(_receiveOrders);",
            )
        },
        expected_violations=(),
        expected_codes=(),
        fixture=FLUTTER_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
    ),
    Variant(
        id="flutter-unsupported-declaration",
        section="class_a",
        item="flutter:unsupported_declaration",
        summary="Add a valid Dart extension on OrderStatus. The native profile does not model "
        "extension declarations, so UML coverage stays explicitly incomplete.",
        files={
            _ORDER: _replace(
                _ORDER,
                "class OrderLine {",
                "extension OrderStatusLabel on OrderStatus {\n"
                "  String get displayLabel => this == OrderStatus.completed\n"
                "      ? 'Completed'\n"
                "      : 'Placed';\n"
                "}\n\n"
                "class OrderLine {",
            )
        },
        expected_violations=(),
        expected_codes=(),
        fixture=FLUTTER_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
    ),
)
