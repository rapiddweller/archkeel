# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290: the state file of a running Studio, and the reuse and stop of that server."""

import json
import os
import signal
import tempfile
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Final

from filelock import FileLock
from filelock import Timeout as StudioLockTimeout

from ..analyzer.process import is_process_alive, is_safe_process_id
from ..studio.api import AgentKind
from ..studio.server import is_studio

__all__ = ["StudioLockTimeout"]

_STATE: Final = "studio.json"
_STOP_SECONDS = 15
STUDIO_LOCK_WAIT_SECONDS = 60


@dataclass(frozen=True)
class StudioProcess:
    pid: int
    url: str
    port: int | None  # `urlsplit` types it so; a Studio URL always has one
    root: str
    started: str
    scope: "StudioScope | None" = None
    stopping: bool = False


@dataclass(frozen=True)
class StudioScope:
    language: str
    sources: tuple[str, ...]
    namespace: str | None
    tsconfig: str | None
    agent: AgentKind
    collector_output_limit_bytes: int | None = None


def studio_lock(folder: Path) -> FileLock:
    """Serialize start and stop for one root; keep a stable lock file and bound the wait."""
    folder.mkdir(parents=True, exist_ok=True)
    return FileLock(str(folder / ".studio.lock"), timeout=STUDIO_LOCK_WAIT_SECONDS)


def _path(folder: Path) -> Path:
    return folder / _STATE


def _recovery_hint(folder: Path) -> str:
    """Explain safe manual recovery when a persisted stop marker outlives its process."""
    return (
        "If this remains stuck, first verify no ArchKeel Studio or Explore process for this root "
        f"is running; then remove the stale state file at {_path(folder)}."
    )


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
        value = json.loads(_path(folder).read_text())
        if not isinstance(value, dict):
            return None
        try:
            raw_scope = value["scope"]
        except KeyError:
            raw_scope = None
        scope = None
        if (
            isinstance(raw_scope, dict)
            and set(raw_scope)
            == {
                "language",
                "sources",
                "namespace",
                "tsconfig",
                "agent",
                "collector_output_limit_bytes",
            }
            and isinstance(raw_scope["language"], str)
            and isinstance(raw_scope["sources"], list)
            and all(isinstance(source, str) for source in raw_scope["sources"])
            and (raw_scope["namespace"] is None or isinstance(raw_scope["namespace"], str))
            and (raw_scope["tsconfig"] is None or isinstance(raw_scope["tsconfig"], str))
            and isinstance(raw_scope["agent"], str)
            and raw_scope["agent"] in {agent.value for agent in AgentKind}
            and (
                raw_scope["collector_output_limit_bytes"] is None
                or (
                    type(raw_scope["collector_output_limit_bytes"]) is int
                    and raw_scope["collector_output_limit_bytes"] > 0
                )
            )
        ):
            scope = StudioScope(
                raw_scope["language"],
                tuple(raw_scope["sources"]),
                raw_scope["namespace"],
                raw_scope["tsconfig"],
                AgentKind(raw_scope["agent"]),
                raw_scope["collector_output_limit_bytes"],
            )
        process = StudioProcess(
            pid=value["pid"],
            url=value["url"],
            port=value["port"],
            root=value["root"],
            started=value["started"],
            scope=scope,
            stopping=value.get("stopping", False),
        )
        if type(process.stopping) is not bool:
            return None
    except (OSError, ValueError, TypeError, KeyError):
        return None
    if type(process.pid) is not int or process.pid <= 1:
        return None
    if not is_safe_process_id(process.pid):
        # Preserve an UNKNOWN cleanup barrier without exposing an out-of-range PID to the OS.
        return replace(process, stopping=True)
    return process


def running_studio(folder: Path) -> StudioProcess | None:
    """Return an HTTP-verified server or preserve an HTTP-verified stop in progress."""
    process = _read(folder)
    if process is not None:
        if is_studio(process.url) or (process.stopping and is_process_alive(process.pid)):
            return process
    if process is None:
        _path(folder).unlink(missing_ok=True)
    else:
        forget_state(folder, process.pid)
    return None


def stop_studio(folder: Path) -> int:
    """Send SIGTERM to a verified Studio and wait until its URL stops answering."""
    try:
        with studio_lock(folder):
            return _stop_studio(folder)
    except StudioLockTimeout:
        print(
            "ArchKeel Studio: another start or stop has held the session lock for "
            f"{STUDIO_LOCK_WAIT_SECONDS} seconds; no stop was sent. Retry when it finishes, or "
            "interrupt the stuck CLI process."
        )
        return 1


def _stop_studio(folder: Path) -> int:
    process = _read(folder)
    if process is None:
        _path(folder).unlink(missing_ok=True)
        print("ArchKeel Studio: not running.")
        return 0

    if not is_safe_process_id(process.pid):
        print(
            "ArchKeel Studio: saved PID is outside this platform's process-ID range; no signal "
            f"was sent. {_recovery_hint(folder)}"
        )
        return 1

    if is_studio(process.url):
        if not process.stopping:
            process = replace(process, stopping=True)
            write_state(folder, process)
        try:
            os.kill(process.pid, signal.SIGTERM)
        except OSError:
            pass  # State removal or process exit below decides whether stop completed.
    elif not process.stopping:
        forget_state(folder, process.pid)
        print("ArchKeel Studio: not running.")
        return 0
    elif not is_process_alive(process.pid):
        forget_state(folder, process.pid)
        print("ArchKeel Studio: not running.")
        return 0

    deadline = time.monotonic() + _STOP_SECONDS
    while time.monotonic() < deadline:
        current = _read(folder)
        if current is None or current.pid != process.pid:
            print("ArchKeel Studio: stopped.")
            return 0
        if not is_process_alive(process.pid):
            forget_state(folder, process.pid)
            print("ArchKeel Studio: stopped.")
            return 0
        time.sleep(0.1)
    print(
        f"ArchKeel Studio: still stopping after {_STOP_SECONDS} s; no new session can start "
        f"until the cleanup finishes. Retry later. {_recovery_hint(folder)}"
    )
    return 1
