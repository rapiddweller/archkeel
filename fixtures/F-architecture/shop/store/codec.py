# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The stored document format: a versioned envelope around one order payload."""

from __future__ import annotations

import json
from typing import TypedDict

from shop.model.entities import Order, OrderPayload

DOCUMENT_VERSION = 1


class OrderDocument(TypedDict):
    """What a stored file holds: the payload, and the format that wrote it."""

    version: int
    order: OrderPayload


def encode(order: Order) -> str:
    """Sorted keys, so two runs that store the same order write the same bytes."""
    document: OrderDocument = {"version": DOCUMENT_VERSION, "order": order.to_dict()}
    return json.dumps(document, sort_keys=True)


def decode(document: str) -> Order:
    parsed: OrderDocument = json.loads(document)
    version = parsed["version"]
    if version != DOCUMENT_VERSION:
        raise ValueError(f"order document version {version} was written by another store")
    return Order.from_dict(parsed["order"])
