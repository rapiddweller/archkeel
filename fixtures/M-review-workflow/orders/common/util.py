# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import time
from collections.abc import Iterator, Sequence


def slugify(text: str) -> str:
    return "-".join(text.lower().split())


def chunked(items: Sequence[str], size: int) -> Iterator[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
