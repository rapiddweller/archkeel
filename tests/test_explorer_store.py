# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest

from archkeel.explorer_store import SnapshotIdentity, cache_path, open_snapshot, publish_snapshot


def _populate(db: sqlite3.Connection) -> None:
    db.execute("CREATE TABLE fact(name TEXT)")
    db.execute("INSERT INTO fact VALUES ('known')")


def test_identity_reuse_and_format(tmp_path: Path) -> None:
    identity = SnapshotIdentity("rev", "policy", "source")
    path = cache_path(tmp_path, tmp_path, identity)
    publish_snapshot(path, identity, _populate, "UNKNOWN")
    publish_snapshot(path, identity, lambda db: pytest.fail("recollected"), "UNKNOWN")
    with open_snapshot(path) as db:
        assert db.execute("SELECT name FROM fact").fetchone()["name"] == "known"
        assert db.execute("SELECT coverage FROM snapshot").fetchone()[0] == "UNKNOWN"
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.execute("DELETE FROM fact")
    with (
        pytest.raises(ValueError, match="identity"),
        open_snapshot(path, SnapshotIdentity("rev", "other", "source")),
    ):
        pass
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(ValueError, match="format"), open_snapshot(path):
        pass


@pytest.mark.parametrize("version", [3, 4, 5, 6])
def test_previous_snapshot_stays_readable_after_projection_upgrade(
    tmp_path: Path, version: int
) -> None:
    identity = SnapshotIdentity("rev", "policy", "source")
    path = cache_path(tmp_path, tmp_path, identity)
    publish_snapshot(path, identity, _populate, "UNKNOWN")
    previous = path.with_name(identity.key(version) + ".sqlite3")
    with closing(sqlite3.connect(path)) as db:
        db.execute(f"PRAGMA user_version={version}")
    path.rename(previous)
    assert previous != path
    with open_snapshot(previous, identity) as db:
        assert tuple(db.execute("SELECT source,contract FROM snapshot").fetchone()) == (
            "source",
            "policy",
        )
    publish_snapshot(path, identity, _populate, "UNKNOWN")
    with open_snapshot(path, identity) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 7


def test_interrupted_build_and_concurrent_reuse(tmp_path: Path) -> None:
    identity = SnapshotIdentity("rev", "policy", "source")
    path = cache_path(tmp_path, tmp_path, identity)

    def abort(db: sqlite3.Connection) -> None:
        _populate(db)
        db.commit()
        raise RuntimeError("aborted")

    with pytest.raises(RuntimeError):
        publish_snapshot(path, identity, abort, "INCOMPLETE")
    assert not path.exists() and not (tmp_path / ".building.sqlite3").exists()
    called = []

    def build(db: sqlite3.Connection) -> None:
        called.append(True)
        _populate(db)

    with ThreadPoolExecutor(2) as pool:
        jobs = [
            pool.submit(publish_snapshot, path, identity, build, "INCOMPLETE") for _ in range(2)
        ]
        for job in jobs:
            job.result()
    assert called == [True]


def test_global_budget_and_active_readers(tmp_path: Path) -> None:
    old = SnapshotIdentity("old", "p", "old")
    new = SnapshotIdentity("new", "p", "new")
    first = cache_path(tmp_path, tmp_path / "one", old)
    second = cache_path(tmp_path, tmp_path / "two", new)
    publish_snapshot(first, old, _populate, "UNKNOWN")
    cap = first.stat().st_size
    with open_snapshot(first) as active:
        with pytest.raises(ValueError, match="budget"):
            publish_snapshot(second, new, _populate, "UNKNOWN", max_bytes=cap)
        assert active.execute("SELECT name FROM fact").fetchone()[0] == "known"
        assert first.exists() and not second.exists()
    publish_snapshot(second, new, _populate, "UNKNOWN", max_bytes=cap)
    assert not first.exists() and second.exists()
    assert sum(p.stat().st_size for p in tmp_path.rglob("*") if p.is_file()) <= cap


def test_oversized_snapshot_and_incomplete_metadata(tmp_path: Path) -> None:
    identity = SnapshotIdentity("rev", "policy", "source")
    path = cache_path(tmp_path, tmp_path, identity)
    with pytest.raises(sqlite3.OperationalError, match="full"):
        publish_snapshot(path, identity, _populate, "UNKNOWN", max_bytes=4096)
    assert not path.exists()
    publish_snapshot(path, identity, _populate, "FAIL")
    with closing(sqlite3.connect(path)) as db:
        db.execute("UPDATE snapshot SET complete=0")
        db.commit()
    with pytest.raises(ValueError, match="incomplete"), open_snapshot(path):
        pass


def test_process_crash_keeps_last_snapshot(tmp_path: Path) -> None:
    old = SnapshotIdentity("old", "policy", "source")
    new = SnapshotIdentity("new", "policy", "source")
    first = cache_path(tmp_path, tmp_path, old)
    second = cache_path(tmp_path, tmp_path, new)
    publish_snapshot(first, old, _populate, "complete")
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            """import os, sys
from pathlib import Path
from archkeel.explorer_store import SnapshotIdentity, publish_snapshot

def crash(db):
    db.execute("CREATE TABLE partial(x)")
    db.commit()
    os._exit(43)

publish_snapshot(Path(sys.argv[1]), SnapshotIdentity("new", "policy", "source"), crash, "UNKNOWN")
""",
            str(second),
        ],
        check=False,
        env=os.environ | {"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    assert process.returncode == 43 and not second.exists()
    with open_snapshot(first, old) as db:
        assert db.execute("SELECT name FROM fact").fetchone()[0] == "known"
    publish_snapshot(second, new, _populate, "INCOMPLETE")
    assert not (tmp_path / ".building.sqlite3").exists()
    with open_snapshot(second, new) as db:
        assert db.execute("SELECT coverage FROM snapshot").fetchone()[0] == "INCOMPLETE"


def test_oversize_refresh_keeps_newest_generation(tmp_path: Path) -> None:
    repo = tmp_path / "project"
    older, current, new = (SnapshotIdentity(r, "policy", r) for r in ("a", "b", "c"))
    first, second, third = (cache_path(tmp_path, repo, item) for item in (older, current, new))
    publish_snapshot(first, older, _populate, "complete")
    os.utime(first, ns=(1, 1))
    publish_snapshot(second, current, _populate, "complete")
    cap = first.stat().st_size + second.stat().st_size

    def oversize(db: sqlite3.Connection) -> None:
        _populate(db)
        db.execute("INSERT INTO fact VALUES (zeroblob(?))", (cap * 2,))

    with pytest.raises(sqlite3.OperationalError, match="full"):
        publish_snapshot(third, new, oversize, "complete", max_bytes=cap)
    assert not first.exists() and not third.exists()
    with open_snapshot(second, current) as db:
        assert db.execute("SELECT name FROM fact").fetchone()[0] == "known"
    publish_snapshot(third, new, _populate, "complete", max_bytes=cap)
    assert second.exists() and third.exists()
