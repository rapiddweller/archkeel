# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Reading and writing one order document, and the encoding both agree on."""

from __future__ import annotations

from pathlib import Path

ENCODING = "utf-8"


def read_document(path: Path) -> str:
    return path.read_text(encoding=ENCODING)


def write_document(path: Path, document: str) -> None:
    """Write through a neighbour and rename, so a crash never leaves half an order behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(f"{path.suffix}.part")
    partial.write_text(document, encoding=ENCODING)
    partial.replace(path)


def discard_document(path: Path) -> None:
    path.unlink()
