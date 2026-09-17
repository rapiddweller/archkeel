# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Where an order document lives, and how the whole set is found."""

from __future__ import annotations

from pathlib import Path

DOCUMENT_SUFFIX = ".json"


def order_path(root: Path, order_id: str) -> Path:
    return root / f"{order_id}{DOCUMENT_SUFFIX}"


def order_paths(root: Path) -> list[Path]:
    """Sorted, because a caller that walks the store must not depend on directory order."""
    return sorted(root.glob(f"*{DOCUMENT_SUFFIX}"))
