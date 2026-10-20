# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from orders.pricing.base import Line

UNIT_PRICES = {"book": 12.5, "pen": 1.2, "lamp": 48.0}


def net(line: Line) -> float:
    return UNIT_PRICES[line.sku] * line.quantity
