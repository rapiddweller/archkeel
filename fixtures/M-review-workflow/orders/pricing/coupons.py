# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from orders.pricing.base import Line

_COUPONS = {"WELCOME5": 5.0, "SPRING10": 10.0}


class CouponDiscount:
    """A known coupon takes a fixed amount off, never below zero."""

    def apply(self, line: Line, amount: float) -> float:
        return max(amount - _COUPONS.get(line.coupon or "", 0.0), 0.0)
