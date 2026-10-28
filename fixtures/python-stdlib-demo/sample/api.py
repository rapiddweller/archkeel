# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A facade whose boundary types all come from the standard library."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

LIMIT: Final = 3


def first_lines(path: Path) -> Iterator[str]:
    with path.open() as handle:
        yield from handle.readlines()[:LIMIT]


@contextmanager
def opened(path: Path) -> Iterator[Path]:
    yield path


__all__ = ["LIMIT", "Final", "Iterator", "first_lines", "opened"]
