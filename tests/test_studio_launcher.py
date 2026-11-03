# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290: start, reuse, stop and idle end of `archkeel studio`, through the real CLI."""

import json
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from test_explore import _repository

from archkeel.cli import _cache_folder, _root_digest, build_parser, launcher, studio_workspace
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
        self.children: list[subprocess.Popen[str]] = []

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


@pytest.fixture
def plain_server() -> Iterator[str]:
    """A local HTTP service that answers 200 to each request, like a reused port."""

    class Answer(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Answer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/?token=x"
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
    assert studio.folder.stat().st_mode & 0o777 == 0o700
    assert [item.name for item in studio.folder.iterdir() if item.name.startswith(".")] == []


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


@pytest.mark.parametrize("answer", ["nothing listens", "a plain HTTP service"])
def test_stop_never_kills_a_live_process_that_is_not_a_studio(
    studio: Launcher,
    sleeper: subprocess.Popen[bytes],
    plain_server: str,
    answer: str,
) -> None:
    url = "http://127.0.0.1:1/?token=gone" if answer == "nothing listens" else plain_server
    studio.write_state(sleeper.pid, url)

    stopped = studio.run("--stop")

    assert (stopped.returncode, stopped.stdout) == (0, f"{_PREFIX}not running.\n")
    assert sleeper.poll() is None
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
        tmp_path, tmp_path / "run", (sys.executable, "-c", "pass"), lambda: ContractState.CONFIGURED
    )
    urls: list[str] = []
    codes: list[int] = []
    serving = threading.Thread(
        target=lambda: codes.append(run_studio(workspace, ready=urls.append, idle_seconds=idle))
    )
    serving.start()
    deadline = time.monotonic() + _WAIT
    while not urls and time.monotonic() < deadline:
        time.sleep(0.05)
    for _ in range(4):
        time.sleep(0.4)
        assert is_studio(urls[0])
    assert serving.is_alive()
    serving.join(_WAIT)
    assert codes == [0]
    assert not is_studio(urls[0])


def test_a_background_job_gets_a_working_sigint_for_the_explore_child(studio: Launcher) -> None:
    # A shell starts `cmd &` with SIGINT ignored, and the explore child inherits that.
    # Workspace.close then cannot unwind it and must wait for the kill.
    script = (
        "import signal, sys\n"
        "signal.signal(signal.SIGINT, signal.SIG_IGN)\n"
        "import archkeel.cli as cli\n"
        "def serve(*args, **kwargs):\n"
        "    print(signal.getsignal(signal.SIGINT) is signal.default_int_handler)\n"
        "    return 0\n"
        "cli.run_studio = serve\n"
        f"sys.exit(cli.main(['studio', '--root', {str(studio.root)!r}, '--no-open']))\n"
    )
    run = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=_WAIT, check=False
    )
    assert (run.returncode, run.stdout) == (0, "True\n"), run.stderr


def test_the_cache_folder_of_the_root_is_private_before_the_first_run(studio: Launcher) -> None:
    studio.folder.mkdir(parents=True, mode=0o755)
    arguments = build_parser().parse_cli_args(["studio", "--root", str(studio.root)])
    workspace = studio_workspace(arguments, studio.folder)
    try:
        assert studio.folder.stat().st_mode & 0o777 == 0o700
    finally:
        workspace.close()
