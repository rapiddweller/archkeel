# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 showcase and clean rows: the default "tour" view, and the unmodified sample."""

from __future__ import annotations

from fixtures.demo_catalog_dependencies import REPOSITORY_WITH_MONEY_IMPORT, SHOP_EXTRA
from fixtures.demo_catalog_interfaces import MAIN_WITH_UNDERSCORE_IMPORT
from fixtures.demo_catalog_support import HEADER, Variant

_TOUR_RENDER_TEXT = HEADER + (
    '"""Text projection of an order."""\n\n'
    "from __future__ import annotations\n\n"
    "from shop.model.entities import Order\n"
    "from shop.store.repository import OrderRepository\n\n"
    "_REPOSITORY_LABEL = OrderRepository.__name__\n\n\n"
    "def render_order(order: Order) -> str:\n"
    '    lines = [f"Order {order.order_id}"]\n'
    "    lines.extend(\n"
    '        _indent(f"{line.quantity} x {line.description}") for line in order.lines\n'
    "    )\n"
    '    lines.append(_indent(f"Total: {order.total()}"))\n'
    '    return "\\n".join(lines)\n\n\n'
    "def _indent(text: str) -> str:\n"
    '    return f"  {text}"\n'
)
_TOUR_APP_ORDERS = HEADER + (
    '"""Use cases: place an order and summarise its total."""\n\n'
    "from __future__ import annotations\n\n"
    "import json\n"
    "from pathlib import Path\n"
    "from typing import TYPE_CHECKING\n\n"
    "from shop.model.entities import Line, Money, Order\n"
    "from shop.store import OrderRepository\n"
    "from shop.store.backend.files import write_payload\n"
    "from shop.store.sqlite import vacuum\n\n"
    "if TYPE_CHECKING:\n"
    "    from shop.store.sqlite import Connection\n\n\n"
    "def place_order(\n"
    "    store_dir: Path,\n"
    "    order_id: str,\n"
    "    description: str,\n"
    "    quantity: int,\n"
    "    unit_price_cents: int,\n"
    ") -> Order:\n"
    "    line = Line(description=description, quantity=quantity, "
    "unit_price=Money(unit_price_cents))\n"
    "    order = Order(order_id=order_id, lines=(line,))\n"
    "    OrderRepository(store_dir).save(order)\n"
    "    return order\n\n\n"
    "def summarize(store_dir: Path, order_id: str) -> Money:\n"
    "    return OrderRepository(store_dir).load(order_id).total()\n\n\n"
    "def describe_connection(connection: Connection) -> str:\n"
    '    """Type-only use of the maintenance connection; never imported at runtime here."""\n'
    '    return f"connection to {connection.path}"\n\n\n'
    "def touch_store(connection: object) -> str:\n"
    '    """A stray runtime reach into the store internals, for the showcase tour."""\n'
    "    vacuum(connection)\n"
    '    write_payload(Path(getattr(connection, "path")), {"order_id": "probe", "lines": []})\n'
    '    return json.dumps({"touched": True})\n'
)
_TOUR_MODEL_ENTITIES = HEADER + (
    '"""Order and Line value types with Money arithmetic."""\n\n'
    "from __future__ import annotations\n\n"
    "from dataclasses import dataclass\n"
    "from typing import Any, TypedDict\n\n"
    '__all__ = ["Order", "Line", "Money", "OrderPayload", "LinePayload"]\n\n\n'
    "class LinePayload(TypedDict):\n"
    '    """The serialised shape of one order line."""\n\n'
    "    description: str\n"
    "    quantity: int\n"
    "    unit_price: int\n\n\n"
    "class OrderPayload(TypedDict):\n"
    '    """The serialised shape of one order."""\n\n'
    "    order_id: str\n"
    "    lines: list[LinePayload]\n\n\n"
    "@dataclass(frozen=True, slots=True)\n"
    "class Money:\n"
    '    """An amount in integer cents."""\n\n'
    "    cents: int\n\n"
    "    def __add__(self, other: Money) -> Money:\n"
    "        return Money(self.cents + other.cents)\n\n"
    "    def __mul__(self, quantity: int) -> Money:\n"
    "        return Money(self.cents * quantity)\n\n"
    "    def __str__(self) -> str:\n"
    '        return f"{self.cents / 100:.2f}"\n\n\n'
    "@dataclass(frozen=True, slots=True)\n"
    "class Discount:\n"
    '    """A percentage discount; not part of the component\'s public interface."""\n\n'
    "    percent: int\n\n"
    "    def apply(self, amount: Money) -> Money:\n"
    "        return Money(amount.cents * (100 - self.percent) // 100)\n\n\n"
    "@dataclass(frozen=True, slots=True)\n"
    "class Line:\n"
    "    description: str\n"
    "    quantity: int\n"
    "    unit_price: Money\n\n"
    "    def total(self) -> Money:\n"
    "        return self.unit_price * self.quantity\n\n"
    "    def to_dict(self) -> LinePayload:\n"
    "        return {\n"
    '            "description": self.description,\n'
    '            "quantity": self.quantity,\n'
    '            "unit_price": self.unit_price.cents,\n'
    "        }\n\n"
    "    @classmethod\n"
    "    def from_dict(cls, payload: LinePayload) -> Line:\n"
    "        return cls(\n"
    '            description=payload["description"],\n'
    '            quantity=payload["quantity"],\n'
    '            unit_price=Money(payload["unit_price"]),\n'
    "        )\n\n\n"
    "@dataclass(frozen=True, slots=True)\n"
    "class Order:\n"
    "    order_id: str\n"
    "    lines: tuple[Line, ...]\n\n"
    "    def total(self) -> Money:\n"
    "        result = Money(0)\n"
    "        for line in self.lines:\n"
    "            result = result + line.total()\n"
    "        return result\n\n"
    "    def to_dict(self) -> OrderPayload:\n"
    '        return {"order_id": self.order_id, "lines": [line.to_dict() for line in '
    "self.lines]}\n\n"
    "    @classmethod\n"
    "    def from_dict(cls, payload: OrderPayload) -> Order:\n"
    '        lines = tuple(Line.from_dict(item) for item in payload["lines"])\n'
    '        return cls(order_id=payload["order_id"], lines=lines)\n\n\n'
    "def audit_total(order: Order, options: Any) -> str:\n"
    '    """Assert/eval probe, an Any parameter and a local render import, for the tour."""\n'
    '    assert order.lines, "orders must have at least one line"\n'
    '    doubled = eval("1 + 1")\n'
    "    from shop.render.text import render_order\n\n"
    '    return f"{render_order(order)} (audit {doubled} of {options})"\n'
)
_TOUR_APP_MAINTENANCE = HEADER + (
    '"""Maintenance use case: compact the store, the one allowed runtime path to '
    'shop.store.sqlite."""\n\n'
    "from __future__ import annotations\n\n"
    "from shop.store.sqlite import Connection, vacuum\n\n\n"
    "def run_maintenance(connection: Connection) -> None:\n"
    "    try:\n"
    "        vacuum(connection)\n"
    "    except Exception:\n"
    "        raise\n"
)
_TOUR = Variant(
    id="tour",
    section="showcase",
    item="tour",
    summary="Every Class A rule kind fires at least once in a single run: a forbidden "
    "render->store pair, a store->Money target_symbol violation, an app->store.sqlite "
    "runtime reach, an app->store.backend reach one package level deeper, an app->json "
    "scope violation, a cli->render underscore reach, a "
    "three-member model/render/store cycle that also violates DEP-MODEL-NO-RENDER, an "
    "assert, an eval and a getattr, Any in the shop.model serialisation boundary, an "
    "allowed_sources-scoped broad except, and an "
    "unassigned module. Real run: 13 rule ids and 14 violations, since CONSTRUCT-NO-DYNAMIC "
    "answers both the eval and the getattr; at validate time the same 14 rule.violated "
    "diagnostics plus 2 closed_world.observed_forbidden pairs (model->render, "
    "render->store) and 1 graph.drift, since the marked graph never declared either edge.",
    files={
        "shop/render/text.py": _TOUR_RENDER_TEXT,
        "shop/app/orders.py": _TOUR_APP_ORDERS,
        "shop/store/repository.py": REPOSITORY_WITH_MONEY_IMPORT,
        "shop/cli/main.py": MAIN_WITH_UNDERSCORE_IMPORT,
        "shop/model/entities.py": _TOUR_MODEL_ENTITIES,
        "shop/app/maintenance.py": _TOUR_APP_MAINTENANCE,
        "shop/extra.py": SHOP_EXTRA,
    },
    expected_violations=(
        "ASSIGNMENT-COMPLETE",
        "COMPONENT-NO-CYCLES",
        "CONSTRUCT-NO-ANY",
        "CONSTRUCT-NO-ASSERT",
        "CONSTRUCT-NO-BROAD-EXCEPT",
        "CONSTRUCT-NO-DYNAMIC",
        "CONSTRUCT-NO-DYNAMIC",
        "DEP-APP-NO-STORE-BACKEND",
        "DEP-APP-NO-STORE-SQLITE",
        "DEP-MODEL-NO-RENDER",
        "DEP-RENDER-NO-STORE",
        "DEP-STORE-NO-MONEY",
        "EXTERNAL-JSON-STORE",
        "INTERFACE-BOUNDARY",
    ),
    expected_codes=(
        "closed_world.observed_forbidden",
        "closed_world.observed_forbidden",
        "graph.drift",
        "rule.violated",
        "rule.violated",
        "rule.violated",
        "rule.violated",
        "rule.violated",
        "rule.violated",
        "rule.violated",
        "rule.violated",
        "rule.violated",
        "rule.violated",
        "rule.violated",
        "rule.violated",
        "rule.violated",
        "rule.violated",
    ),
)
_CLEAN = Variant(
    id="clean",
    section="clean",
    item="shop sample",
    summary="The unmodified shop sample; validate and report both report no findings.",
    files={},
    expected_violations=(),
    expected_codes=(),
)

VARIANTS: tuple[Variant, ...] = (_TOUR, _CLEAN)
