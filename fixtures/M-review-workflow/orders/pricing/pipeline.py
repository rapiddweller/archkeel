# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from orders.pricing.base import Line, PriceStep
from orders.pricing.bulk import BulkDiscount
from orders.pricing.catalog import net
from orders.pricing.clearance import Clearance
from orders.pricing.coupons import CouponDiscount
from orders.pricing.currency import Currency
from orders.pricing.shipping import Shipping
from orders.pricing.small_order import SmallOrderSurcharge
from orders.pricing.tax import Vat

# Order matters: discounts apply to the net amount, tax to the discounted one, and
# currency conversion comes last.
STEPS: tuple[PriceStep, ...] = (
    Clearance(),
    BulkDiscount(),
    CouponDiscount(),
    Vat(),
    SmallOrderSurcharge(),
    Shipping(),
    Currency(),
)


def run(line: Line) -> float:
    amount = net(line)
    for step in STEPS:
        amount = step.apply(line, amount)
    return amount
