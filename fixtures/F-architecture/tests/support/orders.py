# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Build the orders the tests share, so each test states only what it varies."""

from __future__ import annotations

from dataclasses import dataclass

from shop.model.entities import Line, Money, Order


@dataclass(frozen=True, slots=True)
class OrderBuilder:
    order_id: str = "order-1"

    def with_line(self, description: str, quantity: int, cents: int) -> Order:
        line = Line(description=description, quantity=quantity, unit_price=Money(cents))
        return Order(order_id=self.order_id, lines=(line,))
