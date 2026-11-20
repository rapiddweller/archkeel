# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The map retains actual ownership, layer and measured relationship boundaries."""

from pathlib import Path

import pytest

from archkeel.explorer_queries import populate, query
from archkeel.explorer_store import SnapshotIdentity, publish_snapshot


def test_map_hierarchy_paging_and_unknown_calls(tmp_path: Path) -> None:
    for file in ("src/a/main.py", "src/a/sub/util.py", "src/b/other.py"):
        path = tmp_path / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("def f(): pass\n")
    component = lambda id, name, parent, layer: {  # noqa: E731
        "id": id,
        "name": name,
        "parent": parent,
        "layer": layer,
    }
    symbol = {
        "id": "function",
        "kind": "function",
        "module": "a.main",
        "qualified_name": "a.main.f",
        "evidence_ids": [],
    }
    call = {
        "id": "unknown-call",
        "source_definition_id": "function",
        "source_module": "a.main",
        "expression": "dynamic()",
        "targets": [],
        "status": "unresolved",
        "candidates_truncated": False,
        "evidence_ids": [],
    }
    target_symbol = {
        "id": "target",
        "kind": "function",
        "module": "b.other",
        "qualified_name": "b.other.g",
        "evidence_ids": [],
    }
    resolved = {
        "id": "call-site",
        "source_definition_id": "function",
        "source_module": "a.main",
        "target_definition_id": "target",
        "expression": "g()",
        "targets": ["b.other.g"],
        "status": "resolved",
        "candidates_truncated": False,
        "evidence_ids": [],
    }
    topology = {
        "version": 1,
        "components": [
            component("part", "Part", None, None),
            component("A", "A", "part", "business"),
            component("B", "B", "part", "business"),
        ],
        "modules": [
            {"name": "a.main", "path": "src/a/main.py", "component": "A"},
            {"name": "a.util", "path": "src/a/sub/util.py", "component": "A"},
            {"name": "b.other", "path": "src/b/other.py", "component": "B"},
        ],
        "edges": [
            {
                "id": "import",
                "source": "a.main",
                "target": "b.other",
                "resolution": "resolved",
                "count": 1,
            }
        ],
        "component_edges": [
            {
                "id": "component-import",
                "source": "A",
                "target": "B",
                "resolution": "resolved",
                "count": 1,
            }
        ],
        "requires": [{"source": "A", "target": "B"}],
        "explorer": [
            {"language": "python", "symbols": [symbol, target_symbol], "calls": [call, resolved]}
        ],
    }
    path = tmp_path / "cache" / "sample.sqlite"
    publish_snapshot(
        path,
        SnapshotIdentity("rev", "contract", "source"),
        lambda db: populate(db, topology, tmp_path),
        "UNKNOWN",
    )
    root = query(path, tmp_path, "map", {"parent": "part", "view": "components"})
    assert root["total"] == 2
    assert len([g for g in root["groups"] if g["kind"] == "layer"]) == 1
    assert {e["kind"] for e in root["edges"]} == {"import", "requires", "call"}
    modules = query(path, tmp_path, "map", {"parent": "part", "view": "modules"})
    assert modules["total"] == 3
    assert any(g["kind"] == "directory" and g["path"] == "src/a/sub" for g in modules["groups"])
    assert (
        next(item for item in modules["items"] if item["id"] == "a.main")["unresolved_calls"] == 1
    )
    assert any(e["id"] == "import" for e in modules["edges"])
    projected = next(e for e in modules["edges"] if e.get("aggregate"))
    assert (projected["source"], projected["target"], projected["count"]) == (
        "a.main",
        "b.other",
        1,
    )
    assert projected["relation_id"] == "call-site"
    assert (
        query(path, tmp_path, "evidence", {"relation": projected["relation_id"]})["relation"][
            "expression"
        ]
        == "g()"
    )
    page = query(path, tmp_path, "map", {"parent": "part", "view": "modules", "limit": 1})
    assert page["total"] == 3 and page["next_cursor"] == "a.main"
    assert (
        query(path, tmp_path, "map", {"parent": "part", "view": "modules", "cursor": "a.main"})[
            "items"
        ][0]["id"]
        == "a.util"
    )
    functions = query(path, tmp_path, "map", {"parent": "a.main", "view": "modules"})
    assert functions["edges"][0]["target"] is None
    assert functions["edges"][0]["resolution"] == "unresolved"
    with pytest.raises(ValueError, match="unknown map parent"):
        query(path, tmp_path, "map", {"parent": "made-up"})
