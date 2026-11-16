# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The shape type and the two builders of the scaling shape tables (AD-323)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Shape:
    """One input of size n: the maker of the bytes and the count that takes about 0.15 s."""

    make: Callable[[int], bytes]
    # The count that takes about 0.15 s in the debug build; the test doubles it until it is slow
    # enough to measure.
    base: int
    suffix: str = ".ts"


def join_lines(template: str, n: int, sep: str = "\n") -> str:
    """The template written n times, with `{i}` replaced by the index, joined by `sep`."""
    return sep.join(template.replace("{i}", str(i)) for i in range(n))


def as_bytes(make: Callable[[int], str]) -> Callable[[int], bytes]:
    """A maker of text as a maker of bytes."""
    return lambda n: make(n).encode()
