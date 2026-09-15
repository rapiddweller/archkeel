# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Text projection of an order."""

from __future__ import annotations

from shop.model.entities import Order


def render_order(order: Order) -> str:
    lines = [f"Order {order.order_id}"]
    lines.extend(_indent(f"{line.quantity} x {line.description}") for line in order.lines)
    lines.append(_indent(f"Total: {order.total()}"))
    return "\n".join(lines)


def _indent(text: str) -> str:
    return f"  {text}"
