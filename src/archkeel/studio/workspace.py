# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290: the explore snapshot of one root, made on demand in the cache folder."""

import json
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path

from .answer import Snapshot
from .api import ContractState, ExploreState, StudioState

_SNAPSHOT = "architecture.json"

_NOTE_LIMIT = 2000
# Explore needs this long to stop its collector, which runs in a session of its own.
_UNWIND_SECONDS = 10


def _notes(stdout: bytes, stderr: bytes) -> tuple[str, ...]:
    """The diagnostics of a failed explore result, else the end of its stderr."""
    try:
        result = json.loads(stdout)
    except ValueError:
        result = None
    diagnostics = result.get("diagnostics") if isinstance(result, dict) else None
    notes = tuple(
        f"{item.get('unknown_claim', '')} {item.get('remedy', '')}".strip()
        for item in (diagnostics if isinstance(diagnostics, list) else ())
        if isinstance(item, dict)
    )
    return notes or (stderr.decode("utf-8", "replace").strip()[-_NOTE_LIMIT:],)


class Workspace:
    """One root and one explore run at a time; only the explore child writes, into `folder`."""

    def __init__(
        self,
        root: Path,
        folder: Path,
        explore: tuple[str, ...],
        contract: Callable[[], ContractState],
        decode: Callable[[bytes], Mapping[str, object]],
    ) -> None:
        self.root = root.resolve()
        self.folder = folder.resolve()
        self._explore = explore
        self._contract = contract
        self._decode = decode
        self._snapshot: Snapshot | None = None
        self._lock = threading.Lock()
        # The root of the file system has no name of its own.
        name = self.root.name or str(self.root)
        self._run = StudioState(root_name=name, contract=ContractState.NOT_CONFIGURED)
        self._started = 0.0
        self._child: subprocess.Popen[bytes] | None = None

    def state(self) -> StudioState:
        with self._lock:
            run = self._run
            if run.explore is ExploreState.RUNNING:
                run = replace(run, seconds=int(time.monotonic() - self._started))
        return replace(run, contract=self._contract())

    def start(self) -> None:
        """Start the explore run unless one runs; a crash of the child cannot stop the server."""
        with self._lock:
            if self._run.explore is ExploreState.RUNNING:
                return
            self._run = replace(
                self._run, explore=ExploreState.RUNNING, seconds=0, exit_code=None, notes=()
            )
            self._started = time.monotonic()
            self._child = subprocess.Popen(
                self._explore,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
            )
        threading.Thread(target=self._wait, args=(self._child,), daemon=True).start()

    def _wait(self, child: "subprocess.Popen[bytes]") -> None:
        stdout, stderr = child.communicate()
        failed = child.returncode != 0
        with self._lock:
            self._run = replace(
                self._run,
                explore=ExploreState.FAILED if failed else ExploreState.DONE,
                seconds=int(time.monotonic() - self._started),
                exit_code=child.returncode,
                notes=_notes(stdout, stderr) if failed else (),
            )

    def file(self, name: str) -> Path | None:
        """One file of the snapshot folder, by its exact name; never a path."""
        target = self.folder / name
        if not name or target.resolve().parent != self.folder or not target.is_file():
            return None
        return target

    def snapshot(self) -> Snapshot | None:
        """The index of the snapshot once explore is done, else None; built at the first call."""
        with self._lock:
            done = self._run.explore is ExploreState.DONE
        if self._snapshot is None and (path := self.file(_SNAPSHOT)) is not None and done:
            # `decode` is the canonical reader of the CLI: the format has one reader (AD-292).
            self._snapshot = Snapshot(self._decode(path.read_bytes()))
        return self._snapshot

    def close(self) -> None:
        """Stop the explore child within a bound and delete the folder of this run."""
        with self._lock:
            if self._child is not None and self._child.poll() is None:
                # Ctrl-C lets explore unwind; SIGKILL would leave its collector running (POSIX).
                try:
                    self._child.send_signal(signal.SIGINT)
                except ValueError:  # Windows cannot send SIGINT to a process
                    self._child.terminate()
                try:
                    self._child.wait(_UNWIND_SECONDS)
                except subprocess.TimeoutExpired:
                    self._child.kill()
                    self._child.wait()
        shutil.rmtree(self.folder, ignore_errors=True)
