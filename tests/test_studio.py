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

from archkeel.cli import main, studio_workspace
from archkeel.studio.api import API_VERSION
from archkeel.studio.server import Studio

_SCHEMA = json.loads((Path(__file__).parents[1] / "schema/studio-api-1.0.schema.json").read_bytes())
_EXPLORE_SECONDS = 120


def _start(root: Path) -> Studio:
    server = Studio(studio_workspace(root))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _stop(server: Studio) -> None:
    server.shutdown()
    server.server_close()


@pytest.fixture
def studio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Studio]:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    server = _start(_repository(tmp_path / "shop"))
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


def state(server: Studio, cookie: str) -> dict:
    response, body = request(server, "/api/v1/state", cookie=cookie)
    assert response.status == 200
    assert response.getheader("Content-Type") == "application/json"
    payload = json.loads(body)
    Draft202012Validator(_SCHEMA).validate(payload)
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


def test_the_contract_state_comes_from_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    configured = _repository(tmp_path / "configured")
    assert main(["init", "--root", str(configured), "--json"]) == 0
    invalid = tmp_path / "invalid"
    invalid.mkdir()
    (invalid / "archkeel.toml").write_text("[scan\n")
    for folder, expected in (
        (_repository(tmp_path / "shop"), "not_configured"),
        (configured, "configured"),
        (invalid, "invalid"),
    ):
        server = _start(folder)
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


def test_a_failed_explore_shows_its_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    # No commit: explore exits 2 and names the reason.
    server = _start(_repository(tmp_path / "shop", commit=False))
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
    studio.workspace.folder.mkdir(parents=True)
    assert request(studio, f"/files/{name}", cookie=login(studio))[0].status == 404


def test_the_studio_package_does_not_import_the_cli() -> None:
    loaded = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, archkeel.studio.server; "
            "print(sorted(m for m in sys.modules if m.startswith('archkeel.')))",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "archkeel.studio.server" in loaded
    assert "archkeel.cli" not in loaded
