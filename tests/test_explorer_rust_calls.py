# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check Rust call evidence in the real Explorer snapshot and its public tools."""

import json
import shutil
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlencode

import pytest
from core_support import ROOT
from corpus_support import commit_tree

from archkeel import explorer_mcp
from archkeel.cli import core_explorer, core_only


def test_checked_rust_call_path(
    tmp_path: Path, core_binary: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "inventory"
    shutil.copytree(ROOT / "fixtures/P-rust-story", repo)
    commit_tree(repo)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(core_only, "locate_core", lambda: core_binary)
    serve = core_explorer._ExplorerServer.serve_forever

    def probe(server):
        registered = {}

        class Tools:
            def tool(self, operation: Callable) -> None:
                registered[operation.__name__] = operation

        explorer_mcp._query_tools(Tools(), server.snapshot, repo)
        explorer_mcp._story_tools(Tools(), server.snapshot, repo)

        with ThreadPoolExecutor() as pool:
            live = pool.submit(serve, server, 0.01)
            client = HTTPConnection("127.0.0.1", server.server_port, timeout=5)

            def both(operation, **arguments):
                endpoint = "stories" if operation == "story_read" else operation
                client.request("GET", f"/api/v1/{endpoint}?{urlencode(arguments)}")
                response = client.getresponse()
                assert response.status == 200
                result = json.load(response)
                assert result == registered[operation](**arguments)
                return result

            try:
                overview = both("map", view="components")
                (inventory,) = overview["items"]
                board = both("map", parent=inventory["id"], view="modules")
                modules = {item["name"]: item for item in board["items"]}
                root = modules["inventory.inventory"]["id"]
                reservation = modules["inventory.inventory.reservation"]["id"]
                stock = modules["inventory.inventory.stock"]
                edges = {
                    (edge["source"], edge["target"])
                    for edge in board["edges"]
                    if edge["kind"] == "call"
                }
                assert edges == {
                    (root, reservation),
                    (reservation, stock["id"]),
                    (stock["id"], root),
                }
                assert (stock["recorded_calls"], stock["unresolved_calls"]) == (2, 1)
                (available,) = both("children", parent=stock["id"])["items"]
                rows = both("relations", element=available["id"], direction="out", kind="call")[
                    "items"
                ]
                (macro,) = [row for row in rows if row["target"] is None]
                assert macro["expression"] == "debug_assert_eq!"
                assert "Macro expansion" in macro["reason"]

                story = both("story_read", id="reserve-an-item")
                steps = story["steps"]
                assert [step["status"] for step in steps] == ["proven"] * 5
                assert [
                    (step["evidence"][0]["path"], step["evidence"][0]["line"]) for step in steps[1:]
                ] == [
                    ("src/lib.rs", 9),
                    ("src/reservation.rs", 8),
                    ("src/reservation.rs", 12),
                    ("src/stock.rs", 6),
                ]
            finally:
                client.close()
                server.shutdown()
                live.result(timeout=5)

    monkeypatch.setattr(core_explorer._ExplorerServer, "serve_forever", probe)
    assert core_only.run(["explore", str(repo), "--no-open", "--json"]) == 0
