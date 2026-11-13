# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The scan request of `archkeel-core`: the core runs the collector in its own process (AD-406).

The shell sends the scan identity only: the repository root, the configuration file, and the Git
head and dirty state that the shell read. It sends no facts. The core reads the configuration and
the contract, checks the Git claim against the repository, derives the collection request and runs
the linked collector. `read_frame` then binds the frame to the same identity (AD-430).

A dead core (an abort, a stack overflow, an allocation failure) has an exit code that
`read_frame` refuses, so the run has no verdict (exit 2), never a PASS. The shell stops the core
after `TIMEOUT_SECONDS`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Final

from .core_frame import CoreError, read_refusal

SCAN_PROTOCOL: Final = "archkeel-core-scan-1"
TIMEOUT_SECONDS: Final = 600
# The exit code of a request that the core cannot read: it writes no frame.
_REFUSED_EXIT: Final = 2
# The fixed executable and the environment names of `native/collect/src/git.rs`, never `PATH`.
_GIT: Final = "C:/Program Files/Git/cmd/git.exe" if sys.platform == "win32" else "/usr/bin/git"
_GIT_ENVIRONMENT: Final = ("HOME", "USERPROFILE", "XDG_CONFIG_HOME", "SystemRoot", "SYSTEMROOT")
_OID: Final = "# branch.oid "


def identity(root: Path) -> tuple[str, bool] | None:
    """The commit of `HEAD` and the dirty state as the shell reads them, or `None`.

    `None` sends no claim: the core then refuses the repository itself and names the cause, or
    `read_frame` refuses a frame that names a commit the shell did not read.
    """
    command = [
        _GIT,
        "--no-optional-locks",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "-C",
        str(root),
        "status",
        "--porcelain=v2",
        "--branch",
        "--untracked-files=normal",
    ]
    environment = {key: os.environ[key] for key in _GIT_ENVIRONMENT if key in os.environ}
    try:
        done = subprocess.run(
            command, env=environment, capture_output=True, check=False, timeout=TIMEOUT_SECONDS
        )
        lines = done.stdout.decode("utf-8").splitlines()
    except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError):
        return None
    heads = [line.removeprefix(_OID) for line in lines if line.startswith(_OID)]
    if done.returncode != 0 or len(heads) != 1:
        return None
    return heads[0], any(not line.startswith("# ") for line in lines)


def exchange(binary: str, kind: str, request: bytes) -> tuple[bytes, int]:
    """Run the core with one encoded request and a time limit, and give its standard output and exit
    code. Exit 2 (no frame) is a `CoreError`."""
    try:
        done = subprocess.run(
            [binary, kind],
            input=request,
            capture_output=True,
            check=False,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise CoreError(f"the core did not answer in {TIMEOUT_SECONDS} s") from error
    except OSError as error:
        raise CoreError(f"the core could not execute: {error}") from error
    if done.returncode == _REFUSED_EXIT:
        if done.stdout:
            raise CoreError("the core wrote frame bytes with exit 2")
        gap = read_refusal(done.stderr)
        message = (
            gap.reason if gap else done.stderr.decode("utf-8", errors="replace").strip()[-2000:]
        )
        raise CoreError(f"the core refused the request (exit 2): {message}", gap=gap)
    return done.stdout, done.returncode
