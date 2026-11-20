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
                "count": 3,
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
            {
                "language": "python",
                "symbols": [symbol, target_symbol],
                "calls": [call, resolved, dict(resolved, id="second-call")],
            }
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
    component_import = next(edge for edge in root["edges"] if edge["kind"] == "import")
    assert (component_import["source"], component_import["target"]) == ("A", "B")
    contributors = query(
        path, tmp_path, "relations", {"aggregate": component_import["aggregate_id"]}
    )
    assert [row["id"] for row in contributors["items"]] == ["import"]
    assert (contributors["total"], contributors["count"]) == (1, 3)
    system_modules = query(path, tmp_path, "map", {"view": "modules"})
    assert system_modules["module_overview"] and system_modules["module_total"] == 3
    assert [(item["id"], item["module_count"]) for item in system_modules["items"]] == [("part", 3)]
    modules = query(path, tmp_path, "map", {"parent": "part", "view": "modules"})
    assert modules["total"] == 3
    assert any(g["kind"] == "directory" and g["path"] == "src/a/sub" for g in modules["groups"])
    main = next(item for item in modules["items"] if item["id"] == "a.main")
    assert (main["unresolved_calls"], main["recorded_calls"]) == (1, 3)
    assert system_modules["items"][0]["recorded_calls"] == 3
    assert any(e["id"] == "import" for e in modules["edges"])
    projected = next(e for e in modules["edges"] if e.get("aggregate"))
    assert (projected["source"], projected["target"], projected["count"]) == (
        "a.main",
        "b.other",
        2,
    )
    assert projected["relation_id"] == "call-site"
    contributors = {"aggregate": projected["aggregate_id"], "limit": 1}
    first_call = query(path, tmp_path, "relations", contributors)
    assert [row["id"] for row in first_call["items"]] == ["call-site"]
    assert first_call["total"] == 2
    next_call = query(
        path, tmp_path, "relations", contributors | {"cursor": first_call["next_cursor"]}
    )
    assert [row["id"] for row in next_call["items"]] == ["second-call"]
    assert next_call["next_cursor"] is None
    assert main["open_target"] == "map"
    assert (
        next(item for item in modules["items"] if item["id"] == "a.util")["open_target"] == "source"
    )
    symbol_map = query(path, tmp_path, "map", {"parent": "a.main", "view": "hierarchy"})
    assert [item["id"] for item in symbol_map["items"]] == ["function"]
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
    topology["modules"].extend(
        {"name": f"a.extra{index}", "path": "src/a/main.py", "component": "A"}
        for index in range(36)
    )
    topology["components"][2]["layer"] = "storage"
    dense_path = tmp_path / "cache" / "dense.sqlite"
    publish_snapshot(
        dense_path,
        SnapshotIdentity("rev", "contract", "dense"),
        lambda db: populate(db, topology, tmp_path),
        "UNKNOWN",
    )
    first = query(dense_path, tmp_path, "map", {"parent": "part", "view": "modules", "limit": 1})
    assert first["module_overview"] and first["module_total"] == 39
    assert first["items"][0]["module_count"] == 38 and first["next_cursor"] == "A"
    second = query(
        dense_path,
        tmp_path,
        "map",
        {"parent": "part", "view": "modules", "limit": 1, "cursor": "A"},
    )
    assert second["items"][0]["id"] == "B" and second["next_cursor"] is None
    leaf = query(dense_path, tmp_path, "map", {"parent": "A", "view": "modules", "limit": 1})
    assert not leaf["module_overview"] and leaf["module_total"] == 38
    assert leaf["items"][0]["kind"] == "module" and leaf["next_cursor"] is not None
    hierarchy = query(dense_path, tmp_path, "map", {"parent": "part", "view": "hierarchy"})
    assert hierarchy["module_total"] == 39 and hierarchy["next_cursor"] is None
    business = next(item for item in hierarchy["items"] if item["name"] == "business")
    assert business["collapsed"] and business["module_count"] == 38
    storage = next(item for item in hierarchy["groups"] if item["name"] == "storage")
    focused = query(
        dense_path,
        tmp_path,
        "map",
        {"parent": "part", "view": "hierarchy", "focus": storage["id"]},
    )
    assert {edge["target"] for edge in focused["edges"]} == {storage["id"]}
    focus_import = next(edge for edge in focused["edges"] if edge["kind"] == "import")
    stored = query(dense_path, tmp_path, "relations", {"aggregate": focus_import["aggregate_id"]})
    assert [row["id"] for row in stored["items"]] == ["import"]
    related = [edge for edge in hierarchy["edges"] if edge["source"] == business["id"]]
    assert {(edge["kind"], edge["relation_id"]) for edge in related} == {
        ("call", "call-site"),
        ("import", "import"),
    }
    imported = next(edge for edge in related if edge["kind"] == "import")
    contributors = query(dense_path, tmp_path, "relations", {"aggregate": imported["aggregate_id"]})
    assert [(row["source"], row["target"]) for row in contributors["items"]] == [
        ("a.main", "b.other")
    ]
    drill = query(dense_path, tmp_path, "map", {"parent": business["id"], "view": "hierarchy"})
    assert drill["module_total"] == 38 and drill["next_cursor"] is None
    assert [item["id"] for item in drill["items"]] == ["A"]
    root_shape = query(path, tmp_path, "map", {"parent": "part", "view": "hierarchy"})
    assert {item["id"] for item in root_shape["items"]} == {"A", "B"}
    with pytest.raises(ValueError, match="unknown map parent"):
        query(path, tmp_path, "map", {"parent": "made-up"})


def test_large_flat_hierarchy_has_a_scoped_find_for_every_module(tmp_path: Path) -> None:
    topology = {
        "version": 1,
        "components": [{"id": "one", "name": "Owner", "parent": None}],
        "modules": [
            {"name": f"app.m{i:04d}", "path": "src/same.py", "component": "one"}
            for i in range(8200)
        ],
        "edges": [],
    }
    path = tmp_path / "cache" / "flat.sqlite"
    publish_snapshot(
        path,
        SnapshotIdentity("rev", "contract", "flat"),
        lambda db: populate(db, topology, tmp_path),
        "UNKNOWN",
    )
    system = query(path, tmp_path, "map", {"view": "hierarchy"})
    assert system["module_total"] == 8200 and not system["scope_truncated"]
    assert [(item["id"], item["module_count"]) for item in system["items"]] == [("one", 8200)]
    leaf = query(path, tmp_path, "map", {"parent": "one", "view": "hierarchy"})
    assert not leaf["scope_truncated"] and leaf["next_cursor"] is None
    assert len(leaf["items"]) == 36
    assert all(item["kind"] == "file_group" for item in leaf["items"])
    assert sum(item["module_count"] for item in leaf["items"]) == 8200
    last = leaf["items"][-1]
    assert last["open_target"] == "map"
    nested = query(path, tmp_path, "map", {"parent": last["id"], "view": "hierarchy"})
    assert nested["items"][-1]["name"].endswith("m8199")
    assert nested["next_cursor"] is None
    from_group = query(path, tmp_path, "search", {"parent": last["id"], "text": "m8199"})
    assert [item["name"] for item in from_group["items"]] == ["app.m8199"]
    found = query(path, tmp_path, "search", {"parent": "one", "text": "m8199"})
    assert [item["name"] for item in found["items"]] == ["app.m8199"]


def test_system_modules_keeps_both_languages_before_leaf_paging(tmp_path: Path) -> None:
    parts = [("shell", "python", "py", 40), ("core", "rust", "rs", 2)]
    topology = {
        "version": 1,
        "edges": [],
        "components": [
            {"id": owner, "name": owner, "language": lang, "parent": None}
            for owner, lang, _, _ in parts
        ],
        "modules": [
            {
                "name": f"{lang}.module{index}",
                "component": owner,
                "language": lang,
                "path": f"{owner}/module{index}.{ext}",
            }
            for owner, lang, ext, count in parts
            for index in range(count)
        ],
    }
    path = tmp_path / "cache" / "mixed.sqlite"
    publish_snapshot(
        path,
        SnapshotIdentity("rev", "contract", "source"),
        lambda db: populate(db, topology, tmp_path),
        "UNKNOWN",
    )
    result = query(path, tmp_path, "map", {"parent": "system", "view": "modules"})
    assert {item["id"]: item["module_count"] for item in result["items"]} == {
        "shell": 40,
        "core": 2,
    }
    assert result["next_cursor"] is None
    rust = query(path, tmp_path, "map", {"parent": "core", "view": "modules"})
    assert [item["name"] for item in rust["items"]] == ["rust.module0", "rust.module1"]


def test_large_branch_uses_existing_directories_before_file_groups(tmp_path: Path) -> None:
    topology = {
        "version": 1,
        "components": [{"id": "owner", "name": "Owner", "parent": None}],
        "edges": [],
        "modules": [
            {
                "name": f"app.part{directory:02}.file{index}",
                "path": f"src/part{directory:02}/file{index}.py",
                "component": "owner",
            }
            for directory in range(20)
            for index in range(2)
        ],
    }
    path = tmp_path / "cache" / "folders.sqlite"
    publish_snapshot(
        path,
        SnapshotIdentity("rev", "contract", "folders"),
        lambda db: populate(db, topology, tmp_path),
        "UNKNOWN",
    )
    result = query(path, tmp_path, "map", {"parent": "owner", "view": "hierarchy"})
    assert result["module_total"] == 40
    assert len(result["items"]) == 36
    assert {item["kind"] for item in result["items"]} == {"directory", "module"}
    assert result["groups"]
    collapsed = next(item for item in result["items"] if item["kind"] == "directory")
    drill = query(path, tmp_path, "map", {"parent": collapsed["id"], "view": "hierarchy"})
    assert len(drill["items"]) == collapsed["module_count"] == 2
