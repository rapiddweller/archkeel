# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290: the state file of a running Studio, and the reuse and stop of that server."""

import json
import os
import signal
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from ..studio.server import is_studio

_STATE: Final = "studio.json"
_STOP_SECONDS = 15


@dataclass(frozen=True)
class StudioProcess:
    pid: int
    url: str
    port: int | None  # `urlsplit` types it so; a Studio URL always has one
    root: str
    started: str


def _path(folder: Path) -> Path:
    return folder / _STATE


def write_state(folder: Path, process: StudioProcess) -> None:
    """Write the file atomically; `mkstemp` makes it readable by the owner only (mode 0600)."""
    handle, temporary = tempfile.mkstemp(dir=folder, prefix=".studio-")
    with os.fdopen(handle, "w") as stream:
        json.dump(asdict(process), stream)
    os.replace(temporary, _path(folder))


def forget_state(folder: Path, pid: int) -> None:
    """Remove the file of this process; a newer server may have replaced it."""
    if (process := _read(folder)) is not None and process.pid == pid:
        _path(folder).unlink(missing_ok=True)


def _read(folder: Path) -> StudioProcess | None:
    try:
        process = StudioProcess(**json.loads(_path(folder).read_text()))
    except (OSError, ValueError, TypeError):
        return None
    # `os.kill` with 0 or a negative pid signals a whole group.
    return process if type(process.pid) is int and process.pid > 1 else None


def running_studio(folder: Path) -> StudioProcess | None:
    """The server of the state file when it answers as a Studio; else delete the stale file."""
    process = _read(folder)
    if process is not None and is_studio(process.url):
        return process
    if process is None:
        _path(folder).unlink(missing_ok=True)
    else:
        forget_state(folder, process.pid)
    return None


def stop_studio(folder: Path) -> int:
    """Send SIGTERM to a verified Studio and wait until its URL stops answering."""
    process = running_studio(folder)
    if process is None:
        print("ArchKeel Studio: not running.")
        return 0
    try:
        os.kill(process.pid, signal.SIGTERM)
    except OSError:
        pass  # The wait below decides from the HTTP answer.
    deadline = time.monotonic() + _STOP_SECONDS
    while is_studio(process.url) and time.monotonic() < deadline:
        time.sleep(0.1)
    if is_studio(process.url):
        print(f"ArchKeel Studio: still running after {_STOP_SECONDS} s.")
        return 1
    # Windows ends the process without its cleanup, so the file can stay behind.
    forget_state(folder, process.pid)
    print("ArchKeel Studio: stopped.")
    return 0
