# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290: start, reuse, stop and idle end of `archkeel studio`, through the real CLI."""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_explore import _repository

from archkeel.cli import _cache_folder, _root_digest, launcher
from archkeel.cli.arguments import Command
from archkeel.studio.api import ContractState
from archkeel.studio.server import is_studio, run_studio
from archkeel.studio.workspace import Workspace

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")

_WAIT = 60
_PREFIX = "ArchKeel Studio: "


class Launcher:
    """Runs `archkeel studio` as a child of the test, with its own cache folder."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.tmp_path = tmp_path
        self.cache = tmp_path / "cache"
        monkeypatch.setenv("XDG_CACHE_HOME", str(self.cache))
        self.root = _repository(tmp_path / "shop").resolve()
        self.folder = _cache_folder(Command.EXPLORE, _root_digest(self.root))
        self.state = self.folder / "studio.json"
        self.children: list[subprocess.Popen[str] | subprocess.Popen[bytes]] = []

    def _command(self, *options: str) -> list[str]:
        return [sys.executable, "-m", "archkeel.cli", "studio", "--root", str(self.root), *options]

    def start(self, *options: str) -> tuple[subprocess.Popen[str], str]:
        """Start a server in the background; return it with the URL that it printed."""
        child = subprocess.Popen(
            self._command("--no-open", *options),
            stdout=subprocess.PIPE,
            stderr=(self.tmp_path / f"stderr-{len(self.children)}.txt").open("w"),
            text=True,
        )
        self.children.append(child)
        assert child.stdout is not None
        line = child.stdout.readline()
        assert line.startswith(f"{_PREFIX}http://127.0.0.1:"), line
        return child, line.removeprefix(_PREFIX).strip()

    def run(self, *options: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self._command(*options), capture_output=True, text=True, timeout=_WAIT, check=False
        )

    def write_state(self, pid: int, url: str) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        process = launcher.StudioProcess(
            pid=pid, url=url, port=0, root=str(self.root), started="2026-11-03T00:00:00Z"
        )
        self.state.write_text(json.dumps(asdict(process)))


@pytest.fixture
def studio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Launcher]:
    handle = Launcher(tmp_path, monkeypatch)
    yield handle
    for child in handle.children:
        if child.poll() is None:
            child.kill()
        child.wait()
        if child.stdout is not None:
            child.stdout.close()


@pytest.fixture
def sleeper() -> Iterator[subprocess.Popen[bytes]]:
    """A live process that is not a Studio."""
    child = subprocess.Popen(["sleep", str(_WAIT)])
    yield child
    child.kill()
    child.wait()


@contextmanager
def _nothing_listens() -> Iterator[str]:
    yield "http://127.0.0.1:1/?token=gone"


@contextmanager
def _plain_http_service() -> Iterator[str]:
    """A local HTTP service that answers 200 to each request, like a reused port."""

    class Answer(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Answer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/?token=x"
    finally:
        server.shutdown()
        server.server_close()


def _dead_pid() -> int:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def test_the_state_file_holds_the_process_and_is_private(studio: Launcher) -> None:
    child, url = studio.start()
    state = json.loads(studio.state.read_text())
    assert state["pid"] == child.pid
    assert state["url"] == url
    assert state["url"].endswith(f":{state['port']}/?token=" + url.split("token=")[1])
    assert state["root"] == str(studio.root)
    assert state["started"].endswith("Z")
    assert studio.state.stat().st_mode & 0o777 == 0o600
    assert {item.name for item in studio.folder.iterdir() if item.name.startswith(".")} == {
        ".studio.lock"
    }


def test_a_second_start_prints_the_same_url_and_starts_no_second_server(studio: Launcher) -> None:
    child, url = studio.start()
    before = studio.state.read_bytes()
    runs = {item.name for item in studio.folder.glob("studio-*")}

    again = studio.run("--no-open")

    assert again.returncode == 0, again.stderr
    assert again.stdout == f"{_PREFIX}{url} (already running)\n"
    assert studio.state.read_bytes() == before
    assert {item.name for item in studio.folder.glob("studio-*")} == runs
    assert child.poll() is None


def test_a_stale_state_file_is_replaced_by_a_new_start(studio: Launcher) -> None:
    studio.write_state(_dead_pid(), "http://127.0.0.1:1/?token=gone")

    child, url = studio.start()

    state = json.loads(studio.state.read_text())
    assert (state["pid"], state["url"]) == (child.pid, url)


def test_stop_ends_the_server_and_removes_its_files(studio: Launcher) -> None:
    child, _ = studio.start()

    stopped = studio.run("--stop")

    assert stopped.returncode == 0, stopped.stderr
    assert stopped.stdout == f"{_PREFIX}stopped.\n"
    assert child.wait(_WAIT) == 0
    assert not studio.state.exists()
    assert list(studio.folder.glob("studio-*")) == []
    assert studio.run("--stop").stdout == f"{_PREFIX}not running.\n"


@pytest.mark.parametrize("serve", [_nothing_listens, _plain_http_service])
def test_stop_never_kills_a_live_process_that_is_not_a_studio(
    studio: Launcher,
    sleeper: subprocess.Popen[bytes],
    serve: Callable[[], AbstractContextManager[str]],
) -> None:
    with serve() as url:
        studio.write_state(sleeper.pid, url)

        stopped = studio.run("--stop")

    assert (stopped.returncode, stopped.stdout) == (0, f"{_PREFIX}not running.\n")
    assert sleeper.poll() is None
    assert not studio.state.exists()


def test_stop_never_kills_a_live_process_behind_the_port_of_another_studio(
    studio: Launcher, sleeper: subprocess.Popen[bytes]
) -> None:
    # The other Studio answers 403 to a wrong token: that is no proof for this pid.
    child, url = studio.start()
    studio.write_state(sleeper.pid, url.split("token=")[0] + "token=wrong")

    stopped = studio.run("--stop")

    assert (stopped.returncode, stopped.stdout) == (0, f"{_PREFIX}not running.\n")
    assert sleeper.poll() is None
    assert child.poll() is None


def test_a_stale_delete_keeps_the_file_of_a_run_that_replaced_it(
    studio: Launcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    studio.write_state(_dead_pid(), "http://127.0.0.1:1/?token=gone")

    def probe(url: str) -> bool:
        # Another start writes its file between our read and our delete.
        studio.write_state(os.getpid(), "http://127.0.0.1:2/?token=new")
        return False

    monkeypatch.setattr(launcher, "is_studio", probe)

    assert launcher.running_studio(studio.folder) is None
    assert json.loads(studio.state.read_text())["pid"] == os.getpid()


def test_stop_waits_for_a_posix_zombie_to_be_reaped_then_cleans_state(
    studio: Launcher,
    sleeper: subprocess.Popen[bytes],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    process = launcher.StudioProcess(
        pid=sleeper.pid,
        url="http://127.0.0.1:1234/?token=fake",
        port=1234,
        root=str(studio.root),
        started="2026-11-05T00:00:00Z",
        stopping=True,
    )
    studio.folder.mkdir(parents=True)
    launcher.write_state(studio.folder, process)
    monkeypatch.setattr(launcher, "is_studio", lambda _url: False)
    sleeper.kill()
    assert launcher._pid_is_alive(sleeper.pid)

    ticks = iter(range(100))
    monkeypatch.setattr(
        launcher,
        "time",
        SimpleNamespace(monotonic=lambda: next(ticks), sleep=lambda _seconds: None),
    )
    assert launcher.stop_studio(studio.folder) == 1
    assert "still stopping" in capsys.readouterr().out
    assert studio.state.exists()

    assert sleeper.wait(10) != 0
    assert launcher.stop_studio(studio.folder) == 0
    assert not studio.state.exists()


def test_the_negative_control_kills_when_the_http_check_is_skipped(
    studio: Launcher, sleeper: subprocess.Popen[bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A live pid alone proves nothing: without the HTTP check the same file ends the process.
    monkeypatch.setattr(launcher, "is_studio", lambda url: True)
    monkeypatch.setattr(launcher, "_STOP_SECONDS", 0.5)
    studio.write_state(sleeper.pid, "http://127.0.0.1:1/?token=gone")

    launcher.stop_studio(studio.folder)

    assert sleeper.wait(10) != 0


def test_an_idle_server_ends_by_itself(studio: Launcher) -> None:
    child, _ = studio.start("--idle-exit", "0.03")

    assert child.wait(_WAIT) == 0
    assert not studio.state.exists()
    assert list(studio.folder.glob("studio-*")) == []


def test_a_request_keeps_the_server_alive(tmp_path: Path) -> None:
    idle = 1.0
    workspace = Workspace(
        tmp_path,
        tmp_path / "run",
        (sys.executable, "-c", "pass"),
        lambda: ContractState.CONFIGURED,
        lambda _modules: [],
        lambda _raw: {},
    )
    urls: list[str] = []
    codes: list[int] = []
    service_started = threading.Event()
    serving = threading.Thread(
        target=lambda: codes.append(
            run_studio(
                workspace,
                ready=urls.append,
                serving=service_started.set,
                idle_seconds=idle,
            )
        )
    )
    serving.start()
    deadline = time.monotonic() + _WAIT
    while not urls and time.monotonic() < deadline:
        time.sleep(0.05)
    assert service_started.wait(_WAIT)
    for _ in range(4):
        time.sleep(0.4)
        assert is_studio(urls[0])
    assert serving.is_alive()
    serving.join(_WAIT)
    assert codes == [0]
    assert not is_studio(urls[0])


# A slow explore child that records how it ended: SIGINT lets it unwind.
_SLOW_EXPLORE = """
import pathlib, time
try:
    pathlib.Path({ready!r}).touch()
    time.sleep(60)
finally:
    pathlib.Path({unwound!r}).touch()
"""
# The server of a test with that child; the shell of a background job ignores SIGINT.
_SERVE = """
import sys, tempfile
from pathlib import Path
import archkeel.cli as cli
from archkeel.studio.api import ContractState
from archkeel.studio.workspace import Workspace

def workspace(args, cache):
    cache.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="studio-", dir=cache))
    explore = (sys.executable, "-c", {child!r})
    return Workspace(
        args.root.resolve(),
        folder,
        explore,
        lambda: ContractState.CONFIGURED,
        lambda modules: [],
        lambda raw: {{}},
    )

cli.studio_workspace = workspace
sys.exit(cli.main(["studio", "--root", {root!r}, "--no-open"]))
"""


def test_sigterm_ends_the_server_and_the_explore_child_unwinds_on_sigint(
    studio: Launcher, tmp_path: Path
) -> None:
    ready, unwound = tmp_path / "ready", tmp_path / "unwound"
    child_code = _SLOW_EXPLORE.format(ready=str(ready), unwound=str(unwound))
    script = _SERVE.format(child=child_code, root=str(studio.root))
    server = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.DEVNULL,
        preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN),
    )
    studio.children.append(server)
    deadline = time.monotonic() + _WAIT
    while not (ready.exists() and studio.state.exists()) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert ready.exists()
    folders = list(studio.folder.glob("studio-*"))
    assert len(folders) == 1

    started = time.monotonic()
    assert studio.run("--stop").stdout == f"{_PREFIX}stopped.\n"
    assert server.wait(_WAIT) == 0

    # Workspace.close waits 10 s for an explore child that ignores SIGINT, then kills it.
    assert time.monotonic() - started < 8
    assert unwound.exists()
    assert not folders[0].exists()
    assert not studio.state.exists()
