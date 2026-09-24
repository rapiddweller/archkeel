# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Order arithmetic without persistence."""

from __future__ import annotations

from tests.support.orders import OrderBuilder


def test_order_total_multiplies_quantity() -> None:
    order = OrderBuilder().with_line("pen", 3, 150)
    assert order.total().cents == 450
