# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from shop.store.repository import save


def place(order_id: int) -> int:
    return save(order_id)
