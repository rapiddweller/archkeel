# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A memo keeps a value for one live object and never for an equal copy (epic #880, D1)."""

from __future__ import annotations

import gc
from dataclasses import dataclass, replace

from archkeel.ir.identity_memo import IdentityMemo


@dataclass(frozen=True, slots=True, weakref_slot=True)
class _Owner:
    name: str


def test_one_object_computes_once_per_key() -> None:
    memo: IdentityMemo[_Owner, int] = IdentityMemo()
    owner = _Owner("a")
    calls: list[str] = []

    def compute(key: str) -> int:
        calls.append(key)
        return len(calls)

    assert [memo.get(owner, "x", lambda: compute("x")) for _ in range(3)] == [1, 1, 1]
    assert memo.get(owner, "y", lambda: compute("y")) == 2
    assert calls == ["x", "y"]


def test_an_equal_copy_is_a_new_input_and_recomputes() -> None:
    memo: IdentityMemo[_Owner, int] = IdentityMemo()
    first = _Owner("a")
    copy = replace(first)
    assert copy == first and copy is not first
    counter = iter(range(10))
    assert memo.get(first, "k", lambda: next(counter)) == 0
    assert memo.get(copy, "k", lambda: next(counter)) == 1


def test_the_entry_ends_with_its_owner() -> None:
    memo: IdentityMemo[_Owner, int] = IdentityMemo()
    owner = _Owner("a")
    memo.get(owner, "k", lambda: 1)
    assert len(memo) == 1
    del owner
    gc.collect()
    assert len(memo) == 0
