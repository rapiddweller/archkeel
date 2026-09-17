# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A maintenance-only view of the document store, kept out of ordinary order use cases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shop.store.backend import discard_document, order_paths


@dataclass(frozen=True, slots=True)
class Connection:
    path: Path


def vacuum(connection: Connection) -> None:
    """Remove empty leftover order documents from the store directory."""
    for candidate in order_paths(connection.path):
        if candidate.stat().st_size == 0:
            discard_document(candidate)
