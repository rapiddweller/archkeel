# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290: the Studio API on a real server: 127.0.0.1, one token, read-only, versioned."""

import http.client
import json
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from jsonschema import Draft202012Validator
from test_explore import _repository, _tree_digest

from archkeel.cli import build_parser, main, studio_workspace
from archkeel.cli.config import load_config
from archkeel.studio.api import API_VERSION, ContractState
from archkeel.studio.server import Studio
from archkeel.studio.workspace import Workspace
from fixtures.demo_catalog_typescript import VARIANTS as TYPESCRIPT_VARIANTS
from fixtures.reproduce_typescript import repository as typescript_repository

_SCHEMA = json.loads((Path(__file__).parents[1] / "schema/studio-api-1.1.schema.json").read_bytes())
_EXPLORE_SECONDS = 120


def _workspace(root: Path, cache: Path, *options: str) -> Workspace:
    """The workspace that `archkeel studio --root ROOT OPTIONS` makes, with its cache in `cache`."""
    return studio_workspace(
        build_parser().parse_cli_args(["studio", "--root", str(root), *options]), cache
    )


def _start(root: Path, cache: Path, *options: str) -> Studio:
    server = Studio(_workspace(root, cache, *options))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _stop(server: Studio) -> None:
    server.shutdown()
    server.server_close()


@pytest.fixture
def studio(tmp_path: Path) -> Iterator[Studio]:
    server = _start(_repository(tmp_path / "shop"), tmp_path / "cache")
    yield server
    _stop(server)


def request(
    server: Studio,
    path: str,
    *,
    method: str = "GET",
    cookie: str | None = None,
    host: str | None = None,
) -> tuple[http.client.HTTPResponse, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
    headers = {"Host": host or f"127.0.0.1:{server.port}"}
    if cookie is not None:
        headers["Cookie"] = cookie
    connection.request(method, path, headers=headers)
    response = connection.getresponse()
    return response, response.read()


def login(server: Studio) -> str:
    """Follow the start URL once and return the cookie that the browser keeps."""
    start = urlsplit(server.url)
    response, _ = request(server, f"{start.path}?{start.query}")
    assert response.status == 303
    assert response.getheader("Location") == "/"
    cookie = response.getheader("Set-Cookie")
    assert cookie is not None
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    return cookie.split(";", 1)[0]


def validate(payload: object, name: str) -> None:
    """Check a JSON body against one definition of the API schema."""
    schema = {"$schema": _SCHEMA["$schema"], "$defs": _SCHEMA["$defs"], "$ref": f"#/$defs/{name}"}
    Draft202012Validator(schema).validate(payload)


def state(server: Studio, cookie: str) -> dict:
    response, body = request(server, "/api/v1/state", cookie=cookie)
    assert response.status == 200
    assert response.getheader("Content-Type") == "application/json"
    payload = json.loads(body)
    validate(payload, "state")
    return payload


def explore(server: Studio, cookie: str) -> dict:
    """Start the explore run of the workspace and wait until it ends."""
    server.workspace.start()
    deadline = time.monotonic() + _EXPLORE_SECONDS
    while (current := state(server, cookie))["explore"] == "running":
        assert time.monotonic() < deadline, current
        time.sleep(0.2)
    return current


def test_the_schema_has_the_version_of_the_server() -> None:
    Draft202012Validator.check_schema(_SCHEMA)
    assert {
        _SCHEMA["$defs"][name]["properties"]["api_version"]["const"]
        for name in ("state", "chat_response", "chat_error")
    } == {API_VERSION}
    assert _SCHEMA["$id"] == f"urn:archkeel:studio-api:{API_VERSION}"


def test_the_server_listens_on_127_0_0_1_on_a_free_port(studio: Studio) -> None:
    host, port = studio.server_address[:2]
    assert (host, port) == ("127.0.0.1", studio.port)
    assert port != 0
    assert studio.url.startswith(f"http://127.0.0.1:{port}/?token=")


@pytest.mark.parametrize(
    "path", ["/", "/api/v1/state", "/ui/studio.js", "/files/architecture.json"]
)
def test_a_request_without_the_token_gets_403(studio: Studio, path: str) -> None:
    assert request(studio, path)[0].status == 403
    assert request(studio, path, cookie=f"{studio.cookie}=wrong")[0].status == 403


def test_a_wrong_token_in_the_start_url_gets_403(studio: Studio) -> None:
    response, _ = request(studio, "/?token=wrong")
    assert response.status == 403
    assert response.getheader("Set-Cookie") is None


def test_another_host_header_gets_403_also_with_the_cookie(studio: Studio) -> None:
    cookie = login(studio)
    for host in (f"evil.test:{studio.port}", f"localhost:{studio.port}"):
        assert request(studio, "/", cookie=cookie, host=host)[0].status == 403


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_the_api_is_read_only(studio: Studio, method: str) -> None:
    cookie = login(studio)
    assert request(studio, "/api/v1/state", method=method, cookie=cookie)[0].status == 405


def test_the_start_url_opens_the_shell_and_its_assets(studio: Studio) -> None:
    cookie = login(studio)
    response, body = request(studio, "/", cookie=cookie)
    assert response.status == 200
    assert "default-src 'none'" in response.getheader("Content-Security-Policy", "")
    assert b'<script src="/ui/studio.js"' in body
    for name in ("studio.js", "tokens.css", "studio.css"):
        assert request(studio, f"/ui/{name}", cookie=cookie)[0].status == 200, name
    for path in ("/ui/AGENTS.md", "/ui/main.tsx", "/unknown", "/api/v2/state"):
        assert request(studio, path, cookie=cookie)[0].status == 404, path


def test_two_servers_do_not_share_a_cookie(studio: Studio) -> None:
    other = Studio(studio.workspace)
    try:
        assert studio.cookie != other.cookie
    finally:
        other.server_close()


def test_the_contract_state_comes_from_the_root(tmp_path: Path) -> None:
    configured = _repository(tmp_path / "configured")
    assert main(["init", "--root", str(configured), "--json"]) == 0
    invalid = tmp_path / "invalid"
    invalid.mkdir()
    (invalid / "archkeel.toml").write_text("[scan\n")
    # A valid archkeel.toml with a contract that does not parse, or that the parser refuses.
    broken = {}
    for name, text in (("json", "{not json"), ("schema", '{"schema_version": "2.2.0"}')):
        broken[name] = _repository(tmp_path / f"broken-{name}")
        assert main(["init", "--root", str(broken[name]), "--json"]) == 0
        (broken[name] / load_config(broken[name]).contract).write_text(text)
    for folder, expected in (
        (_repository(tmp_path / "shop"), "not_configured"),
        (configured, "configured"),
        (invalid, "invalid"),
        (broken["json"], "invalid"),
        (broken["schema"], "invalid"),
    ):
        server = _start(folder, tmp_path / "cache")
        try:
            assert state(server, login(server))["contract"] == expected
        finally:
            _stop(server)


def test_explore_writes_only_the_cache_and_the_repository_stays_unchanged(
    studio: Studio, tmp_path: Path
) -> None:
    cookie = login(studio)
    before = _tree_digest(studio.workspace.root)
    outside = set(tmp_path.iterdir())
    assert state(studio, cookie)["explore"] == "idle"

    result = explore(studio, cookie)

    assert result["explore"] == "done", result
    assert result["exit_code"] == 0
    assert result["root_name"] == "shop"
    assert _tree_digest(studio.workspace.root) == before
    assert set(tmp_path.iterdir()) == outside | {tmp_path / "cache"}
    assert studio.workspace.folder.is_relative_to(tmp_path / "cache")
    response, body = request(studio, "/files/architecture.report.html", cookie=cookie)
    assert response.status == 200
    assert response.getheader("Content-Type") == "text/html"
    assert b"ArchKeel" in body


def test_a_failed_explore_shows_its_diagnostic(tmp_path: Path) -> None:
    # No commit: explore exits 2 and names the reason.
    server = _start(_repository(tmp_path / "shop", commit=False), tmp_path / "cache")
    try:
        result = explore(server, login(server))
    finally:
        _stop(server)
    assert result["explore"] == "failed"
    assert result["exit_code"] == 2
    assert result["notes"], result


@pytest.mark.parametrize(
    "name", ["../shop/pyproject.toml", "..%2Fshop%2Fpyproject.toml", "nothing.html", ""]
)
def test_files_serves_only_a_file_of_the_snapshot_folder(studio: Studio, name: str) -> None:
    assert request(studio, f"/files/{name}", cookie=login(studio))[0].status == 404


def test_the_studio_package_does_not_import_the_cli() -> None:
    loaded = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, archkeel.studio.server; "
            "print(sorted(m for m in sys.modules"
            " if m.startswith('archkeel.') or m == 'webbrowser'))",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "archkeel.studio.server" in loaded
    assert "archkeel.cli" not in loaded
    # The CLI opens the browser; the server starts no process.
    assert "'webbrowser'" not in loaded


def test_the_root_of_the_file_system_has_a_name() -> None:
    workspace = Workspace(
        Path("/"), Path("/nothing"), (), lambda: ContractState.NOT_CONFIGURED, lambda _raw: {}
    )
    assert workspace.state().root_name == "/"


def test_each_studio_run_has_its_own_private_cache_folder(tmp_path: Path) -> None:
    root = _repository(tmp_path / "shop")
    first, second = _workspace(root, tmp_path / "cache"), _workspace(root, tmp_path / "cache")
    assert first.folder != second.folder
    assert first.folder.parent == second.folder.parent
    assert first.folder.is_relative_to(tmp_path / "cache")
    assert first.folder.stat().st_mode & 0o777 == 0o700
    first.close()
    assert not first.folder.exists()
    assert second.folder.is_dir()


def test_studio_forwards_the_scope_options_to_explore(tmp_path: Path) -> None:
    clean = next(item for item in TYPESCRIPT_VARIANTS if item.id == "typescript-clean")
    root = typescript_repository(tmp_path, clean)
    options = ("--language", "typescript", "--source", "src", "--namespace", "shop")
    server = _start(root, tmp_path / "cache", *options, "--tsconfig", "tsconfig.json")
    try:
        cookie = login(server)
        result = explore(server, cookie)
        page, _ = request(server, "/files/architecture.report.html", cookie=cookie)
    finally:
        _stop(server)
    assert result["explore"] == "done", result
    assert page.status == 200


def _running_child(tmp_path: Path, script: str) -> Workspace:
    """A workspace whose explore child runs `script` and touches `ready` when it is set up."""
    workspace = Workspace(
        tmp_path,
        tmp_path / "run",
        (sys.executable, "-c", script),
        lambda: ContractState.CONFIGURED,
        lambda _raw: {},
    )
    workspace.start()
    deadline = time.monotonic() + 30
    while not (tmp_path / "ready").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert (tmp_path / "ready").exists()
    return workspace


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_close_lets_explore_unwind_before_it_kills(tmp_path: Path) -> None:
    unwound = tmp_path / "unwound"
    workspace = _running_child(
        tmp_path,
        "import pathlib, time\n"
        "try:\n"
        f"    pathlib.Path({str(tmp_path / 'ready')!r}).touch()\n"
        "    time.sleep(60)\n"
        "finally:\n"
        f"    pathlib.Path({str(unwound)!r}).touch()\n",
    )
    workspace.close()
    assert unwound.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_close_kills_an_explore_that_ignores_the_interrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("archkeel.studio.workspace._UNWIND_SECONDS", 0.5)
    workspace = _running_child(
        tmp_path,
        "import pathlib, signal, time\n"
        "signal.signal(signal.SIGINT, signal.SIG_IGN)\n"
        f"pathlib.Path({str(tmp_path / 'ready')!r}).touch()\n"
        "time.sleep(60)\n",
    )
    child = workspace._child
    assert child is not None
    workspace.close()
    assert child.poll() is not None
