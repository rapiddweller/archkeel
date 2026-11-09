# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Keep a result for one live object, so a long-lived server never grows with its inputs."""

from __future__ import annotations

import weakref
from collections.abc import Callable, Hashable
from functools import partial
from typing import Generic, TypeVar

Owner = TypeVar("Owner")
T = TypeVar("T")


class IdentityMemo(Generic[Owner, T]):
    """Map one object, by identity, and a key to an immutable value.

    An equal copy is another input and computes again. The entry ends with its owner.
    """

    def __init__(self) -> None:
        self._rows: dict[int, tuple[weakref.ref[Owner], dict[Hashable, T]]] = {}

    def __len__(self) -> int:
        return len(self._rows)

    def _forget(self, identity: int, _: weakref.ref[Owner]) -> None:
        self._rows.pop(identity, None)

    def get(self, owner: Owner, key: Hashable, compute: Callable[[], T]) -> T:
        identity = id(owner)
        row = self._rows.get(identity)
        if row is None or row[0]() is not owner:
            row = (weakref.ref(owner, partial(self._forget, identity)), {})
            self._rows[identity] = row
        values = row[1]
        if key not in values:
            values[key] = compute()
        return values[key]
