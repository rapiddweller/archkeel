# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A contract-free scan exposes the same import in the browser and the MCP tools."""

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pytest
from corpus_support import commit_tree

from archkeel import explorer_mcp
from archkeel.cli import core_explorer, core_only


@pytest.mark.parametrize(
    ("folder", "caller", "library"),
    [("src", "orders", "ledger"), ("packages", "garden", "seeds")],
)
def test_follow_package_import_from_map_to_source(
    tmp_path: Path,
    built: Path,
    monkeypatch: pytest.MonkeyPatch,
    folder: str,
    caller: str,
    library: str,
) -> None:
    repo = tmp_path / "sample"
    for package in (caller, library):
        directory = repo / folder / package
        directory.mkdir(parents=True)
        (directory / "__init__.py").write_text("")
    statement = f"from {library}.values import value"
    module = Path(folder, caller, "start.py")
    (repo / module).write_text(f"# start\n{statement}\n")
    (repo / folder / library / "values.py").write_text("value = 1\n")
    (repo / "pyproject.toml").write_text(f'[tool.setuptools.packages.find]\nwhere = ["{folder}"]\n')
    commit_tree(repo)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(core_only, "locate_core", lambda: built / "archkeel-core")

    snapshots = []
    serve = core_explorer._ExplorerServer.serve_forever

    def probe(server):
        registered = {}

        class Tools:
            def tool(self, operation: Callable) -> None:
                registered[operation.__name__] = operation

        explorer_mcp._query_tools(Tools(), server.snapshot, repo)

        def both(operation, **arguments):
            with urlopen(
                f"http://127.0.0.1:{server.server_port}/api/v1/{operation}?{urlencode(arguments)}",
                timeout=5,
            ) as response:
                result = json.load(response)
            assert result == registered[operation](**arguments)
            return result

        with ThreadPoolExecutor() as pool:
            live = pool.submit(serve, server, 0.01)
            try:
                board = both("map", parent="system", view="components")
                groups = {item["name"]: item["id"] for item in board["items"]}
                (edge,) = [
                    e
                    for e in board["edges"]
                    if e["kind"] == "import"
                    and (e["source"], e["target"]) == (groups[caller], groups[library])
                ]
                rows = both("relations", aggregate=edge["aggregate_id"])["items"]
                (relation,) = [
                    r
                    for r in rows
                    if r["source"] == f"{caller}.start" and r["target"] == f"{library}.values"
                ]
                (site,) = both("evidence", relation=relation["id"])["items"]
                excerpt = both("source", reference=site["reference"], start=2, limit=1)
                assert (excerpt["path"], excerpt["line"], excerpt["lines"]) == (
                    module.as_posix(),
                    2,
                    [statement],
                )
                snapshots.append((server.snapshot, server.snapshot.stat().st_mtime_ns, board, site))
            finally:
                server.shutdown()
                live.result(timeout=3)

    monkeypatch.setattr(core_explorer._ExplorerServer, "serve_forever", probe)
    for _ in range(2):
        assert core_only.run(["explore", str(repo), "--no-open", "--json"]) == 0
    assert len(snapshots) == 2 and snapshots[0] == snapshots[1]
    assert not (repo / "archkeel.toml").exists()
