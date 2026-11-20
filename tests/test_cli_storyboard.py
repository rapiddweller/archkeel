# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exercise the Studio chat boundary and the source identity used for playback."""

import json
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path

from corpus_support import commit_tree

from archkeel.cli import core_explorer_http
from archkeel.cli.core_binding import ProjectRoot
from archkeel.cli.core_explorer_identity import _fingerprint


def test_story_output_does_not_invalidate_its_source(tmp_path: Path) -> None:
    source = tmp_path / "example.py"
    source.write_text("answer = 42\n")
    commit_tree(tmp_path)
    project = ProjectRoot.top(tmp_path)
    binary = tmp_path / "unused"
    before = _fingerprint(project, binary)
    folder = tmp_path / ".archkeel" / "stories"
    folder.mkdir(parents=True)
    (folder / "example.story.json").write_text("{}")
    assert _fingerprint(project, binary) == before
    source.write_text("answer = 43\n")
    assert _fingerprint(project, binary)[0] != before[0]


def test_story_routes_require_local_origin_for_creation(tmp_path: Path, monkeypatch) -> None:
    result = {"id": "example", "title": "Create order"}
    calls = []

    def create(root, snapshot, prompt, element, story, *, confirm):
        assert confirm is not None
        confirm()
        calls.append(prompt)
        return result

    def confirm():
        calls.append("check")

    monkeypatch.setattr(core_explorer_http, "_create_story", create)
    monkeypatch.setattr(core_explorer_http, "list_stories", lambda root, db: [result])
    monkeypatch.setattr(core_explorer_http, "read_story", lambda root, db, key: result)
    with (
        core_explorer_http._ExplorerServer(tmp_path / "db", tmp_path, None, 0, confirm) as server,
        ThreadPoolExecutor() as pool,
    ):
        running = pool.submit(server.serve_forever)
        client = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        try:
            for url, expected in (
                ("/api/v1/stories", {"items": [result]}),
                ("/api/v1/stories?id=example", result),
            ):
                client.request("GET", url)
                response = client.getresponse()
                assert response.status == 200 and json.load(response) == expected
            for origin, expected in (
                (None, 403),
                ("https://example.org", 403),
                (
                    f"http://127.0.0.1:{server.server_port}",
                    201,
                ),
            ):
                headers = {"Content-Type": "application/json"}
                if origin:
                    headers["Origin"] = origin
                client.request("POST", "/api/v1/story-chat", '{"prompt":"create order"}', headers)
                response = client.getresponse()
                assert response.status == expected
                response.read()
            assert calls == ["check", "check", "create order"]
        finally:
            client.close()
            server.shutdown()
            running.result(timeout=5)
