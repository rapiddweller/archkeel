# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Argument parsing and composition; the single broad error boundary lives here."""

from __future__ import annotations

from pathlib import Path

from shop.app.orders import place_order
from shop.render.text import render_order


def main(argv: list[str]) -> int:
    try:
        order_id, description, quantity, unit_price_cents, store_dir = argv
        order = place_order(
            Path(store_dir), order_id, description, int(quantity), int(unit_price_cents)
        )
        print(render_order(order))
        return 0
    except Exception:
        return 1
