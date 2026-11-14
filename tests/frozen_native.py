# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A frozen copy of `native/` and its cited documents for each test that reads this checkout.

Consumer: each test that scans, walks or copies the live `native/` directory. A parallel worker
can run `cargo` there, and cargo creates and removes files in `native/target` and `native/.digests`
while the test reads. A scan then fails with `Unreadable source directory`, or two scans differ.

The fixture `frozen_root` copies the files of `native/` once for the whole session: the tracked
files and the new files that Git does not ignore, as they are now. A changed tracked file is
tested as it is. The copy also holds each document that the native contract cites, because
the core reads and binds it (AD-466). The copy is a Git repository with one commit. Its
directory name holds a digest of the files, so all workers of one session share one copy
through a lock file.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from corpus_support import commit_tree
from filelock import FileLock

ROOT = Path(__file__).resolve().parents[1]
LISTING = ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "native"]
SKIPPED = frozenset({"target", ".digests"})


def live_files(root: Path = ROOT) -> list[str]:
    """The files of `native/` that a checkout holds, by relative path: no build output."""
    done = subprocess.run(LISTING, cwd=root, capture_output=True, check=False)
    if done.returncode == 0:
        names = [name for name in done.stdout.decode().split("\0") if name]
    else:
        names = [
            path.relative_to(root).as_posix()
            for path in sorted((root / "native").rglob("*"))
            if path.is_file()
        ]
    files = {name for name in names if not SKIPPED.intersection(Path(name).parts[1:2])}
    return sorted(files | cited(root))


def cited(root: Path = ROOT) -> set[str]:
    """The provenance documents that the native contract cites: a scan reads them (AD-466)."""
    path = root / "native/architecture-contract.json"
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {
        name
        for item in [*contract["components"], *contract["rules"]]
        for name in item.get("provenance", [])
        if (root / name).is_file()
    }


def _read(root: Path, name: str) -> bytes | None:
    try:
        return (root / name).read_bytes()
    except OSError:
        # A tracked file that the working tree deleted is not part of the tree.
        return None


def _copy(root: Path, target: Path) -> None:
    staging = target.with_name(target.name + ".part")
    shutil.rmtree(staging, ignore_errors=True)
    for name in live_files(root):
        data = _read(root, name)
        if data is None:
            continue
        path = staging / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod((root / name).stat().st_mode & 0o777)
    commit_tree(staging)
    staging.rename(target)


def _digest(root: Path) -> str:
    digest = hashlib.sha256()
    for name in live_files(root):
        data = _read(root, name)
        if data is not None:
            digest.update(name.encode() + b"\0" + hashlib.sha256(data).digest())
    return digest.hexdigest()[:16]


@pytest.fixture(scope="session")
def frozen_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A Git repository that holds the files of `native/`; the path names no build output."""
    base = tmp_path_factory.getbasetemp()
    if os.environ.get("PYTEST_XDIST_WORKER"):
        base = base.parent
    shared = base / "frozen-native"
    shared.mkdir(exist_ok=True)
    target = shared / _digest(ROOT)
    with FileLock(str(shared / "lock")):
        if not target.is_dir():
            _copy(ROOT, target)
    return target.resolve()
