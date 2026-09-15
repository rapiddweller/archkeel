# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A maintenance-only view of the JSON store, kept out of ordinary order use cases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Connection:
    path: Path


def vacuum(connection: Connection) -> None:
    """Remove empty leftover order files from the store directory."""
    for candidate in connection.path.glob("*.json"):
        if candidate.stat().st_size == 0:
            candidate.unlink()
