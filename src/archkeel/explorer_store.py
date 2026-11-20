# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Atomically publish and pin derived SQLite snapshots in a bounded local cache."""

import hashlib
import json
import os
import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

_FORMAT = 4
_READABLE_FORMATS = {3, _FORMAT}
_PAGE = 4096
CACHE_BYTES = 1024**3
_KEY = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class SnapshotIdentity:
    """Revision, effective policy and source fingerprints for one collector build."""

    revision: str
    contract: str
    source: str

    def key(self, version: int = _FORMAT) -> str:
        """Return a versioned, portable cache key."""
        fields = [version, self.revision, self.contract, self.source]
        return hashlib.sha256(json.dumps(fields).encode()).hexdigest()


def cache_path(cache_root: Path, repository: Path, identity: SnapshotIdentity) -> Path:
    """Locate a snapshot within its repository namespace."""
    repo = hashlib.sha256(os.fsencode(repository.resolve())).hexdigest()
    return cache_root / repo / (identity.key() + ".sqlite3")


def _root(path: Path) -> Path:
    return path.parent.parent if _KEY.fullmatch(path.parent.name) else path.parent


def _lease(path: Path) -> Path:
    # Fixed slots keep the lock inventory bounded. Collisions only defer eviction.
    slot = hashlib.sha256(os.fsencode(path.absolute())).hexdigest()[:2]
    return _root(path) / (".lease-" + slot)


@contextmanager
def _lock(path: Path, exclusive: bool, timeout: float = 0) -> Iterator[None]:
    # SQLite's file locks work across processes on both Unix and Windows.
    with closing(sqlite3.connect(path, timeout=timeout)) as guard:
        guard.execute("PRAGMA journal_mode=MEMORY")
        guard.execute("BEGIN EXCLUSIVE" if exclusive else "BEGIN")
        guard.execute("SELECT name FROM sqlite_schema").fetchall()
        yield


@contextmanager
def repository_writer(path: Path) -> Iterator[None]:
    """Serialize cold scans of a repository before collection starts."""
    _root(path).mkdir(parents=True, mode=0o700, exist_ok=True)
    path.parent.mkdir(mode=0o700, exist_ok=True)
    with _lock(path.parent / ".scanner", exclusive=True, timeout=30):
        yield


@contextmanager
def open_snapshot(
    path: Path, identity: SnapshotIdentity | None = None
) -> Iterator[sqlite3.Connection]:
    """Pin a published snapshot and verify its format and optional expected identity."""
    with _lock(_lease(path), exclusive=False, timeout=5):
        uri = path.resolve().as_uri() + "?mode=ro&immutable=1"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in _READABLE_FORMATS:
                raise ValueError("unsupported Explorer snapshot format")
            row = connection.execute(
                "SELECT revision, contract, source, coverage FROM snapshot WHERE complete=1"
            ).fetchone()
            if row is None or not row["coverage"]:
                raise ValueError("incomplete Explorer snapshot")
            actual = SnapshotIdentity(row["revision"], row["contract"], row["source"])
            if (identity is not None and identity != actual) or (
                _KEY.fullmatch(path.stem) and path.stem != actual.key(version)
            ):
                raise ValueError("Explorer snapshot identity mismatch")
            yield connection


def _usage(root: Path) -> int:
    return sum(entry.stat().st_size for entry in root.rglob("*") if entry.is_file())


def _evict(root: Path, keep: Path, needed: int) -> int:
    candidates = [
        item
        for item in root.glob("*/*.sqlite3")
        if item != keep and _KEY.fullmatch(item.parent.name) and _KEY.fullmatch(item.stem)
    ]
    ordered = sorted((item.stat().st_mtime_ns, item) for item in candidates)
    # Keep this repository usable if a larger replacement still exceeds the budget.
    latest = max((stamp for stamp, item in ordered if item.parent == keep.parent), default=None)
    reclaimed = 0
    for stamp, item in ordered:
        if item.parent == keep.parent and stamp == latest:
            continue
        try:
            with _lock(_lease(item), exclusive=True):
                size = item.stat().st_size
                item.unlink()
                reclaimed += size
                if reclaimed >= needed:
                    break
        except sqlite3.OperationalError as exc:
            if exc.sqlite_errorcode != sqlite3.SQLITE_BUSY:
                raise
    return reclaimed


def _build(
    temp: Path,
    identity: SnapshotIdentity,
    populate: Callable[[sqlite3.Connection], None],
    coverage: str,
    available: int,
) -> None:
    if available < _PAGE:
        raise ValueError("Explorer snapshot cache budget exhausted")
    with closing(sqlite3.connect(temp)) as connection:
        connection.execute(f"PRAGMA page_size={_PAGE}")
        connection.execute(f"PRAGMA max_page_count={available // _PAGE}")
        # The build is private and discarded on error. No WAL or temporary disk spill.
        connection.execute("PRAGMA journal_mode=MEMORY")
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.execute("BEGIN")
        populate(connection)
        connection.execute(
            "CREATE TABLE snapshot(revision TEXT,contract TEXT,source TEXT,coverage TEXT,"
            "complete INTEGER)"
        )
        connection.execute(
            "INSERT INTO snapshot VALUES (?,?,?,?,1)",
            (identity.revision, identity.contract, identity.source, coverage),
        )
        connection.execute(f"PRAGMA user_version={_FORMAT}")
        connection.commit()


def publish_snapshot(
    path: Path,
    identity: SnapshotIdentity,
    populate: Callable[[sqlite3.Connection], None],
    coverage: str,
    *,
    max_bytes: int = CACHE_BYTES,
) -> None:
    """Reuse a matching snapshot or publish a completed private build within the global cap."""
    if not coverage or max_bytes < _PAGE:
        raise ValueError("missing coverage or invalid Explorer snapshot cache budget")
    if _KEY.fullmatch(path.stem) and path.stem != identity.key():
        raise ValueError("Explorer snapshot path and identity mismatch")
    root = _root(path)
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    path.parent.mkdir(mode=0o700, exist_ok=True)
    with _lock(root / ".publisher", exclusive=True, timeout=30):
        temp = root / ".building.sqlite3"
        temp.unlink(missing_ok=True)
        if path.is_file():
            with open_snapshot(path, identity):
                return
        available = max_bytes - _usage(root)
        try:
            while True:
                try:
                    _build(temp, identity, populate, coverage, available)
                    break
                except (ValueError, sqlite3.OperationalError) as exc:
                    full = available < _PAGE or (
                        isinstance(exc, sqlite3.OperationalError)
                        and exc.sqlite_errorcode == sqlite3.SQLITE_FULL
                    )
                    if not full:
                        raise
                    temp.unlink(missing_ok=True)
                    # Retry with increasing space, evicting the oldest idle snapshots first.
                    reclaimed = _evict(root, path, max(available, 3 * _PAGE))
                    if not reclaimed:
                        raise
                    available += reclaimed
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
