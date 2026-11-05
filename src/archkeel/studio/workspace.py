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
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from .answer import Snapshot
from .api import ContractState, Declare, Decode, ExploreState, Graph, StudioState
from .graph import build_graph
from .stories import Stories

_SNAPSHOT = "architecture.json"
_NOTE_LIMIT = 2000
_SNAPSHOT_INVALID = "Explore did not write a readable architecture.json snapshot."
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
        ". ".join(
            f"{item.get(field, '')}".strip()
            for field in ("subject", "unknown_claim", "remedy")
            if item.get(field)
        )
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
        declare: Declare,
        decode: Decode,
        stories: Stories | None = None,
    ) -> None:
        self.root = root.resolve()
        self.folder = folder.resolve()
        self._explore = explore
        self._contract = contract
        self._declare = declare
        self._decode = decode
        self.stories = stories
        self._snapshot: Snapshot | None = None
        self._lock = threading.Lock()
        # A build takes seconds on a large repository; it must not hold up the state polls.
        self._graph_lock = threading.Lock()
        self._graph: Graph | None = None
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
        # The two locks in the order of `graph`: the graph of an earlier run must not outlive it.
        with self._graph_lock, self._lock:
            if self._run.explore is ExploreState.RUNNING:
                return
            if self.stories is not None:
                self.stories.invalidate_check()
            self._run = replace(
                self._run, explore=ExploreState.RUNNING, seconds=0, exit_code=None, notes=()
            )
            self._started = time.monotonic()
            self._graph = None
            # The folder is reused on restart; an older valid snapshot cannot prove this run.
            snapshot_path: Path = self.folder / _SNAPSHOT
            snapshot_path.unlink(missing_ok=True)
            self._snapshot = None
            self._child = subprocess.Popen(
                self._explore,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
            )
        threading.Thread(target=self._wait, args=(self._child,), daemon=True).start()

    def _wait(self, child: "subprocess.Popen[bytes]") -> None:
        stdout, stderr = child.communicate()
        graph = None
        snapshot_error = False
        if child.returncode in (0, 2):
            try:
                snapshot_path: Path = self.folder / _SNAPSHOT
                graph = build_graph(self._decode(snapshot_path.read_bytes()), self._declare)
            except (OSError, ValueError):
                snapshot_error = True
        failed = child.returncode not in (0, 2) or graph is None
        with self._graph_lock, self._lock:
            # A new run reuses the snapshot path; discard any session built before it replaced it.
            if self.stories is not None:
                self.stories.invalidate_check()
            self._graph = graph if not failed else None
            state = (
                ExploreState.FAILED
                if failed
                else ExploreState.INCOMPLETE
                if child.returncode == 2
                else ExploreState.DONE
            )
            notes = _notes(stdout, stderr) if failed or state is ExploreState.INCOMPLETE else ()
            if snapshot_error:
                notes = (*notes, _SNAPSHOT_INVALID)
            self._run = replace(
                self._run,
                explore=state,
                seconds=int(time.monotonic() - self._started),
                exit_code=child.returncode,
                notes=notes,
            )

    def graph(self) -> Graph | None:
        """The call graph of a valid snapshot; None until the run finishes."""
        with self._graph_lock:
            with self._lock:
                done = self._run.explore in (ExploreState.DONE, ExploreState.INCOMPLETE)
            if self._graph is None and done:
                snapshot = self.folder / _SNAPSHOT
                self._graph = build_graph(self._decode(snapshot.read_bytes()), self._declare)
            return self._graph

    def file(self, name: str) -> Path | None:
        """One file of the snapshot folder, by its exact name; never a path."""
        target = self.folder / name
        if not name or target.resolve().parent != self.folder or not target.is_file():
            return None
        return target

    def snapshot(self) -> Snapshot | None:
        """The index of a complete snapshot, else None; chat cannot label partial evidence."""
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
