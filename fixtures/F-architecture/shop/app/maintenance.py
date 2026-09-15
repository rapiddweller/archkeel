# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Maintenance use case: compact the store, the one allowed runtime path to shop.store.sqlite."""

from __future__ import annotations

from shop.store.sqlite import Connection, vacuum


def run_maintenance(connection: Connection) -> None:
    vacuum(connection)
