# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Re-export the storage backend: where documents live, and how they are read and written."""

from __future__ import annotations

from shop.store.backend.files import discard_document, read_document, write_document
from shop.store.backend.paths import order_path, order_paths

__all__ = [
    "discard_document",
    "order_path",
    "order_paths",
    "read_document",
    "write_document",
]
