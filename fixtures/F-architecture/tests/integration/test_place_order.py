# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Place an order through the use case and read it back from disk."""

from __future__ import annotations

from pathlib import Path

from shop.app.orders import place_order, summarize
from shop.store.repository import OrderRepository
from tests.support.orders import OrderBuilder


def test_placed_order_round_trips(tmp_path: Path) -> None:
    placed = place_order(tmp_path, "order-1", "pen", 3, 150)
    assert OrderRepository(tmp_path).load("order-1") == placed
    assert placed == OrderBuilder().with_line("pen", 3, 150)
    assert summarize(tmp_path, "order-1").cents == 450
