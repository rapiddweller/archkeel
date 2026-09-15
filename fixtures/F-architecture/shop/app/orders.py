# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Use cases: place an order and summarise its total."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from shop.model.entities import Line, Money, Order
from shop.store import OrderRepository

if TYPE_CHECKING:
    from shop.store.sqlite import Connection


def place_order(
    store_dir: Path,
    order_id: str,
    description: str,
    quantity: int,
    unit_price_cents: int,
) -> Order:
    line = Line(description=description, quantity=quantity, unit_price=Money(unit_price_cents))
    order = Order(order_id=order_id, lines=(line,))
    OrderRepository(store_dir).save(order)
    return order


def summarize(store_dir: Path, order_id: str) -> Money:
    return OrderRepository(store_dir).load(order_id).total()


def describe_connection(connection: Connection) -> str:
    """Type-only use of the maintenance connection; never imported at runtime here."""
    return f"connection to {connection.path}"
