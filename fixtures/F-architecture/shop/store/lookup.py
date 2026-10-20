# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Resolve an order path without embedding an order identifier."""

from __future__ import annotations

from pathlib import Path

from shop.store.backend.paths import order_path


def lookup_order(root: Path, order_id: str) -> Path:
    return order_path(root, order_id)


def find_order(root: Path, order_id: str) -> Path:
    return lookup_order(root, order_id)


def read_option(key: str) -> str:
    """Return the selected option key for the architecture demo."""
    return key
