# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Persist orders as one JSON file per order id."""

from __future__ import annotations

from pathlib import Path

from shop.model.entities import Order
from shop.store.backend import read_payload, write_payload


class OrderRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    def save(self, order: Order) -> None:
        write_payload(self._path(order.order_id), order.to_dict())

    def load(self, order_id: str) -> Order:
        return Order.from_dict(read_payload(self._path(order_id)))

    def _path(self, order_id: str) -> Path:
        return self._root / f"{order_id}.json"
