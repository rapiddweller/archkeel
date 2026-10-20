# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from dataclasses import dataclass


@dataclass(frozen=True)
class Receipt:
    sku: str
    quantity: int
    total_cents: int
