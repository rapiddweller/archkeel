# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from orders.checkout import Receipt, place
from orders.checkout.rounding import round_cents
from orders.common.util import slugify
from orders.pricing import price


def place_order(sku: str, quantity: int, region: str, coupon: str | None = None) -> Receipt:
    """Entry point: price one order line, persist the receipt and return it."""
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    return place(slugify(sku), quantity, region, coupon)


def quote(sku: str, quantity: int, region: str, coupon: str | None = None) -> int:
    """Entry point: the total in cents an order would cost, without placing it."""
    return round_cents(price(slugify(sku), quantity, region, coupon))
