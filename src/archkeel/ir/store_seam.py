# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The seam to the Rust store of one collection (AD-346, opt-in).

The store keeps the whole records of a reply; the Python check holds only their read-set. So
three steps that need the whole records go to the store: the receipt digest of a dependency proof
(`dependency_binding`), the binding of a member inventory proof (`member_inventory`) and the
canonical `architecture.json` (`codec_store`). A collector
that uses the store opens a session with `open_store`; the report path closes it.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Protocol

# A bound or saved entry: the id of an entry that the store holds, or the entry of the shell.
StoreEntry = str | Mapping[str, object]


class StoreSeam(Protocol):
    """One collection that a store process holds."""

    def holds_record(self, identifier: str) -> bool: ...

    def holds_evidence(self, identifier: str) -> bool: ...

    def bind(self, records: Sequence[StoreEntry], evidence: Sequence[StoreEntry]) -> str:
        """The receipt digest of the entries, in the order of the caller."""
        ...

    def digest(self, value: Mapping[str, object]) -> str:
        """The member inventory binding digest of the parts of the shell."""
        ...

    def write(self, model: Mapping[str, object]) -> bytes:
        """The canonical `architecture.json` of the parts of the shell."""
        ...

    def close(self) -> None: ...


_ACTIVE: ContextVar[StoreSeam | None] = ContextVar("archkeel_store", default=None)
_ENABLED: ContextVar[bool] = ContextVar("archkeel_store_enabled", default=True)


def store_enabled() -> bool:
    """False inside `store_disabled`: a collector then decodes its reply in Python."""
    return _ENABLED.get()


@contextmanager
def store_disabled() -> Iterator[None]:
    """Observe without the store. `check` compares two observations and hashes them with the
    Python writer; a store holds one collection only, so `check` runs on the Python path."""
    token = _ENABLED.set(False)
    try:
        yield
    finally:
        _ENABLED.reset(token)


def active_store() -> StoreSeam | None:
    return _ACTIVE.get()


def open_store(seam: StoreSeam) -> None:
    """Make `seam` the store of the current collection; a previous store closes first."""
    close_store()
    _ACTIVE.set(seam)


def close_store() -> None:
    seam = _ACTIVE.get()
    if seam is not None:
        _ACTIVE.set(None)
        seam.close()
