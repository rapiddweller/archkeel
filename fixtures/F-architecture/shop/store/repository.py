# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Persist orders as one document per order id."""

from __future__ import annotations

from pathlib import Path

from shop.model.entities import Order
from shop.store.backend import order_path, read_document, write_document
from shop.store.codec import decode, encode


class OrderRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    def save(self, order: Order) -> None:
        write_document(order_path(self._root, order.order_id), encode(order))

    def load(self, order_id: str) -> Order:
        return decode(read_document(order_path(self._root, order_id)))
