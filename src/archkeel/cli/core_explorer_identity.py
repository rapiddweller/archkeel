# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Bind an Explorer snapshot to its source files and executables."""

import hashlib
import json
import os
import stat
import sys
from pathlib import Path

from archkeel.explorer_store import SnapshotIdentity

from .core_binary import collector_workers
from .core_binding import ProjectRoot
from .core_frame import CoreError
from .native_scan import identity, tracked_and_unignored


def _file_digest(file: Path, info: os.stat_result | None = None) -> str:
    expected = info or file.lstat()
    flags = os.O_RDONLY
    if sys.platform != "win32":
        flags |= os.O_NOFOLLOW | os.O_NONBLOCK
    descriptor = os.open(file, flags)
    with os.fdopen(descriptor, "rb") as opened:
        before = os.fstat(opened.fileno())
        if not stat.S_ISREG(before.st_mode) or (
            before.st_dev,
            before.st_ino,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (expected.st_dev, expected.st_ino, expected.st_mtime_ns, expected.st_ctime_ns):
            raise CoreError("a fingerprint input was replaced or is not a regular file")
        digest = hashlib.file_digest(opened, "sha256").hexdigest()
        after = os.fstat(opened.fileno())
        if (before.st_mtime_ns, before.st_ctime_ns) != (after.st_mtime_ns, after.st_ctime_ns):
            raise CoreError("a fingerprint input changed during the read")
        return digest


def _fingerprint(project: ProjectRoot, binary: Path) -> tuple[SnapshotIdentity, dict[str, str]]:
    # Saving a checked story does not change the architecture that it describes.
    inputs = ("--", ".", ":(exclude,glob,top).archkeel/stories/*.story.json")
    state = identity(project.path, pathspec=inputs)
    if state is None:
        raise CoreError("the Explorer needs a Git work tree with a commit")
    files = tracked_and_unignored(project.path, pathspec=inputs) | {Path(project.config)}
    digests: dict[str, str] = {}
    total = 0
    for name in sorted(files):
        file = project.path / name
        if name.is_absolute() or ".." in name.parts:
            raise CoreError("an Explorer snapshot path leaves the project root")
        if file.parent.resolve() != file.parent:
            raise CoreError("an Explorer snapshot path has a linked parent")
        try:
            info = file.lstat()
        except FileNotFoundError:
            digests[name.as_posix()] = "missing"
            continue
        if stat.S_ISLNK(info.st_mode):
            digests[name.as_posix()] = "link:" + os.readlink(file)
        elif stat.S_ISREG(info.st_mode):
            total += info.st_size
            if total > 2 << 30:
                raise CoreError("the Explorer snapshot exceeds the 2 GiB fingerprint limit")
            digests[name.as_posix()] = _file_digest(file, info)
        elif stat.S_ISDIR(info.st_mode):
            digests[name.as_posix()] = "directory"
        else:
            raise CoreError("the Explorer snapshot contains an unsupported file")
    source = hashlib.sha256(json.dumps([state[1], digests], sort_keys=True).encode()).hexdigest()
    executables = [
        (_file_digest(path) if path.exists() else "missing")
        for path in (binary, *collector_workers(binary))
    ]
    contract = hashlib.sha256(json.dumps([project.config, executables]).encode()).hexdigest()
    return SnapshotIdentity(state[0], contract, source), digests
