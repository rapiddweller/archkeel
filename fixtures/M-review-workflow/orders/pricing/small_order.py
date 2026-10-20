# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from orders.pricing.base import Line


class SmallOrderSurcharge:
    """A single low-value unit carries a handling surcharge."""

    def apply(self, line: Line, amount: float) -> float:
        return amount + 1.0 if line.quantity == 1 and amount < 5 else amount
