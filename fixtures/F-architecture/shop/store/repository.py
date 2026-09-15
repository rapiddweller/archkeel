# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Persist orders as one JSON file per order id."""

from __future__ import annotations

import json
from pathlib import Path

from shop.model.entities import Order


class OrderRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    def save(self, order: Order) -> None:
        self._path(order.order_id).write_text(json.dumps(order.to_dict()))

    def load(self, order_id: str) -> Order:
        return Order.from_dict(json.loads(self._path(order_id).read_text()))

    def _path(self, order_id: str) -> Path:
        return self._root / f"{order_id}.json"
