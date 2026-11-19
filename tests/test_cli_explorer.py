# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exercise the Explorer through its public CLI and localhost HTTP surface."""

from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path

import pytest

from archkeel.cli import core_explorer, core_only
from archkeel.cli.core_arguments import parse
from archkeel.cli.core_frame import CoreCommand


def test_explorer_flags() -> None:
    options = parse(["explore", "--port", "9000", "--no-open", "--config", "system.json"])
    assert options.command is CoreCommand.EXPLORE
    assert options.port == 9000
    assert options.no_open and options.config_given
    with pytest.raises(ValueError, match="port"):
        parse(["explore", "--port", "65536"])


def test_explorer_does_not_draft_a_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: tmp_path / "unused")
    assert core_only.run(["explore", "--root", str(tmp_path), "--json"]) == 2
    assert "Git work tree" in capsys.readouterr().out
    assert not list(tmp_path.iterdir())


def test_explorer_http_is_read_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def query(
        path: Path, root: Path, operation: str, arguments: dict[str, object]
    ) -> dict[str, object]:
        assert path == tmp_path / "snapshot.sqlite3"
        assert root == tmp_path
        if operation == "source":
            raise ValueError("source changed since scan")
        assert operation == "children"
        return {"items": [arguments]}

    monkeypatch.setattr(core_explorer, "query", query)
    report = "<html><head><style>:root{--ink:black}</style></head><body>Report</body></html>"
    with (
        core_explorer._ExplorerServer(
            tmp_path / "snapshot.sqlite3", tmp_path, lambda: report, 0
        ) as server,
        ThreadPoolExecutor() as pool,
    ):
        running = pool.submit(server.serve_forever)
        try:
            client = HTTPConnection("127.0.0.1", server.server_port, timeout=3)

            def request(
                path: str, headers: dict[str, str] | None = None, method: str = "GET"
            ) -> tuple[int, bytes]:
                client.request(method, path, headers=headers or {})
                response = client.getresponse()
                return response.status, response.read()

            code, body = request("/")
            assert code == 200 and b'src="/explorer-story.js"' in body
            assert request("/explorer-story.js")[0] == 200
            assert request("/report")[0] == 200
            assert request("/report.css")[0] == 200
            assert b"--surface-0:" in request("/report.css")[1]
            code, body = request("/api/v1/children?parent=system")
            assert code == 200 and b'"parent": "system"' in body
            assert request("/api/children?parent=a&parent=b")[0] == 400
            code, body = request("/api/v1/source?reference=x")
            assert code == 409 and b"source changed since scan" in body
            assert request("/api/children", {"Host": "example.org"})[0] == 403
            assert request("/api/children", {"Origin": "https://example.org"})[0] == 403
            assert request("/api/children", {"Sec-Fetch-Site": "cross-site"})[0] == 403
            assert request("/api/children", method="POST")[0] == 501
            assert request("/api/anything")[0] == 404
        finally:
            server.shutdown()
            running.result(timeout=3)
