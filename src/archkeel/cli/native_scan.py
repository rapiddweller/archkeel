# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The scan request of `archkeel-core`: the core selects and runs the collector (AD-406, AD-881).

The shell sends the scan identity only: the repository root, the configuration file, and the Git
head and dirty state that the shell read. It sends no facts. The core reads the configuration and
the contract, checks the Git claim against the repository, derives the collection request and runs
the collector. `read_frame` then binds the frame to the same identity (AD-432).

A dead core (an abort, a stack overflow, an allocation failure) has an exit code that
`read_frame` refuses, so the run has no verdict (exit 2), never a PASS. The shell stops the core
after `_TIMEOUT_SECONDS`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from time import monotonic
from typing import Final, TextIO

from .core_frame import read_refusal
from .core_json import CoreError, CoreExit

SCAN_PROTOCOL: Final = "archkeel-core-scan-1"
_TIMEOUT_SECONDS: Final = 600
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
            command, env=environment, capture_output=True, check=False, timeout=_TIMEOUT_SECONDS
        )
        lines = done.stdout.decode("utf-8").splitlines()
    except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError):
        return None
    heads = [line.removeprefix(_OID) for line in lines if line.startswith(_OID)]
    if done.returncode != 0 or len(heads) != 1:
        return None
    return heads[0], any(not line.startswith("# ") for line in lines)


def tracked_and_unignored(root: Path) -> set[Path]:
    """Name fingerprint inputs without running Git hooks or filesystem monitors."""
    command = [
        _GIT,
        "--no-optional-locks",
        "-c",
        "core.fsmonitor=false",
        "-C",
        str(root),
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    ]
    environment = {key: os.environ[key] for key in _GIT_ENVIRONMENT if key in os.environ}
    try:
        done = subprocess.run(
            command, env=environment, capture_output=True, check=False, timeout=_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired as error:
        raise CoreError("Git did not list the snapshot files in time") from error
    if done.returncode or len(done.stdout) > 16 << 20:
        raise CoreError("Git could not list the snapshot files within the Explorer limit")
    return {Path(os.fsdecode(name)) for name in done.stdout.split(b"\0") if name}


def prepare_disposable_git(root: Path) -> None:
    """Commit the files of a disposable scan copy without system config or Git hooks."""
    if (root / ".git").exists():
        raise CoreError("the disposable scan copy already has Git metadata")
    env = {key: os.environ[key] for key in _GIT_ENVIRONMENT if key in os.environ}
    env |= {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    for args in (
        ("init", "--template=", "--quiet"),
        ("add", "--force", "--all"),
        (
            "-c",
            "user.name=ArchKeel Explorer",
            "-c",
            "user.email=explorer@localhost",
            "-c",
            "commit.gpgSign=false",
            "commit",
            "--no-verify",
            "--quiet",
            "-m",
            "Explorer copy",
        ),
    ):
        try:
            done = subprocess.run(
                [_GIT, "--no-optional-locks", "-C", str(root), *args],
                env=env,
                capture_output=True,
                check=False,
                timeout=_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise CoreError("Git did not prepare the disposable copy in time") from error
        if done.returncode:
            raise CoreError("Git could not prepare the disposable Explorer copy")


def ignored_by(root: Path, paths: Sequence[str]) -> dict[str, str]:
    """For each path that a Git ignore rule covers: `FILE:LINE` of the rule (`git check-ignore`).

    A path that is not covered, and any failure of Git, gives no entry: the text then says less,
    never something false.
    """
    if not paths:
        return {}
    command = [_GIT, "--no-optional-locks", "-C", str(root), "check-ignore", "-v", "-z", "--stdin"]
    environment = {key: os.environ[key] for key in _GIT_ENVIRONMENT if key in os.environ}
    try:
        done = subprocess.run(
            command,
            env=environment,
            input="\0".join(paths).encode("utf-8"),
            capture_output=True,
            check=False,
            timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    fields = done.stdout.decode("utf-8", "replace").split("\0")
    found: dict[str, str] = {}
    for source, line, _pattern, path in zip(*[iter(fields)] * 4, strict=False):
        if source:
            found[path] = f"{source}:{line}"
    return found


def exchange(
    binary: str, kind: str, request: bytes, stderr_sink: list[bytes] | None = None
) -> tuple[bytes, int]:
    """Run the core with one encoded request and a time limit, and give its standard output and exit
    code. Exit 2 (no frame) is a `CoreError`. A caller that wants the standard error of a run that
    gave a frame (the timings of #659) passes a list; the bytes are appended to it."""
    try:
        with _progress(Path.cwd().name) if kind == "scan" else _quiet():
            done = subprocess.run(
                [binary, kind],
                input=request,
                capture_output=True,
                check=False,
                timeout=_TIMEOUT_SECONDS,
            )
    except subprocess.TimeoutExpired as error:
        raise CoreError(f"the core did not answer in {_TIMEOUT_SECONDS} s") from error
    except OSError as error:
        raise CoreError(f"the core could not execute: {error}") from error
    if stderr_sink is not None:
        stderr_sink.append(done.stderr)
    if done.returncode == CoreExit.REFUSED:
        if done.stdout:
            raise CoreError("the core wrote frame bytes with exit 2")
        gap = read_refusal(done.stderr)
        message = (
            gap.reason if gap else done.stderr.decode("utf-8", errors="replace").strip()[-2000:]
        )
        raise CoreError(f"the core refused the request (exit 2): {message}", gap=gap)
    return done.stdout, done.returncode


_PROGRESS_DELAY: Final = 3.0


@contextmanager
def _progress(
    where: str, stream: TextIO | None = None, delay: float = _PROGRESS_DELAY
) -> Iterator[None]:
    """A progress line on standard error for a scan that runs past `delay` seconds (#1621).

    The core answers with one frame, so the shell knows the time and not the steps. On a terminal
    the line is rewritten each second and removed at the end; on a pipe it is written once.
    Standard output is never touched.
    """
    out = stream if stream is not None else sys.stderr
    stop = threading.Event()
    started = monotonic()
    tty = out.isatty()
    shown = False

    def tick() -> None:
        nonlocal shown
        if stop.wait(delay):
            return
        while True:
            text = f"archkeel: scanning {where}, {int(monotonic() - started)} s so far..."
            out.write(f"\r{text}" if tty else f"{text}\n")
            out.flush()
            shown = True
            if not tty or stop.wait(1.0):
                return

    worker = threading.Thread(target=tick, daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join()
        if shown and tty:
            out.write("\r\033[K")
            out.flush()


@contextmanager
def _quiet() -> Iterator[None]:
    """No progress line for a command other than a scan."""
    yield
