# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Explorer navigation and source evidence refer to the same scan."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from archkeel.explorer_queries import populate, query
from archkeel.explorer_store import SnapshotIdentity, cache_path, publish_snapshot


def test_bounded_navigation_and_stale_evidence(tmp_path: Path) -> None:
    """A second page is stable and editing the source invalidates its proof."""
    source = tmp_path / "a.py"
    source.write_text("import b\n")
    topology = {
        "version": 1,
        "complete": False,
        "truncated": True,
        "gaps": [],
        "components": [],
        "modules": [{"name": name, "component": None, "path": "a.py"} for name in ("a", "b")],
        "edges": [
            {
                "id": "edge",
                "source": "a",
                "target": "b",
                "resolution": "resolved",
                "evidence": [{"path": "a.py", "line": 1}],
            }
        ],
    }

    def write(db: sqlite3.Connection) -> None:
        populate(db, topology, tmp_path)

    identity = SnapshotIdentity("rev", "contract", "tree")
    path = tmp_path / "cache" / "sample.sqlite"
    publish_snapshot(path, identity, write, "partial")
    page = query(path, tmp_path, "children", {"limit": 1})
    assert page["coverage"]["truncated"] and page["items"][0]["id"] == "module:a"
    assert (
        query(path, tmp_path, "children", {"cursor": page["next_cursor"]})["items"][0]["id"]
        == "module:b"
    )
    known = query(path, tmp_path, "relations", {"element": "module:a", "direction": "in"})
    missing = query(path, tmp_path, "relations", {"element": "missing"})
    assert known["element_status"] == "known" and known["items"] == []
    assert missing["element_status"] == "unknown" and missing["items"] == []
    ref = query(path, tmp_path, "evidence", {"relation": "relation:module_import:edge"})["items"][
        0
    ]["reference"]
    assert query(path, tmp_path, "source", {"reference": ref})["lines"] == ["import b"]
    source.write_text("import c\n")
    with pytest.raises(ValueError, match="changed"):
        query(path, tmp_path, "source", {"reference": ref})


def test_call_step_uses_the_collectors_evidence(tmp_path: Path) -> None:
    """A candidate never becomes a resolved story handoff."""
    (tmp_path / "f.ts").write_text("f()\n")
    symbol = {
        "id": "sym",
        "kind": "function",
        "module": "m",
        "qualified_name": "m.f",
        "evidence_ids": ["here"],
    }
    call = {
        "id": "call",
        "source_definition_id": "sym",
        "expression": "f",
        "source_module": "m",
        "targets": ["m.f"],
        "status": "partial",
        "candidates_truncated": False,
        "evidence_ids": ["here"],
    }
    topology = {
        "version": 1,
        "components": [],
        "modules": [],
        "edges": [],
        "locations": {"here": {"path": "f.ts", "line": 1}},
        "explorer": [
            {
                "part": None,
                "language": "typescript",
                "files": [{"module": "m", "path": "f.ts"}, {"module": "n", "path": "n.ts"}],
                "symbols": [symbol],
                "calls": [call],
            }
        ],
    }
    path = tmp_path / "cache" / "sample.sqlite"
    publish_snapshot(
        path,
        SnapshotIdentity("r", "c", "s"),
        lambda db: populate(db, topology, tmp_path),
        "partial",
    )
    result = query(path, tmp_path, "story", {"id": "relation:call:call"})
    assert result["coverage"]["parts"][0] == {
        "part": None,
        "language": "typescript",
        "facts": {"symbols": 1, "calls": 1, "imports": None},
        "files_indexed": 2,
        "files_with_symbols": 1,
        "files_with_calls": 1,
    }
    assert result["status"] == "unresolved"
    assert result["items"][0]["target"] is None
    assert result["items"][0]["evidence"][0]["line"] == 1


def test_overview_lists_only_proved_external_import_packages(tmp_path: Path) -> None:
    packages = [f"package-{index:02}" for index in range(14)]
    rows = [
        {
            "id": f"import-{index}",
            "source_module": "m",
            "target_module": package,
            "resolution": "external",
            "evidence_class": "FACT",
            "evidence_ids": [],
        }
        for index, package in enumerate([*reversed(packages), packages[0]])
    ]
    for name, fields in (
        ("local", {"resolution": "local"}),
        ("builtin", {"resolution": "builtin"}),
        ("unresolved", {"resolution": "unresolved"}),
        ("unknown", {"evidence_class": "UNKNOWN"}),
        ("receiver", {"inferred_receiver": True}),
    ):
        rows.append(dict(rows[0], id=name, target_module=name, **fields))
    topology = {
        "version": 1,
        "components": [],
        "modules": [],
        "edges": [],
        "explorer": [{"language": "typescript", "imports": rows}],
    }
    path = tmp_path / "cache" / "sample.sqlite"
    publish_snapshot(
        path,
        SnapshotIdentity("r", "c", "s"),
        lambda db: populate(db, topology, tmp_path),
        "partial",
    )
    coverage = query(path, tmp_path, "overview", {})["coverage"]
    assert coverage["external_imports"] == {"packages": packages[:12], "total": 14}
    assert coverage["parts"][0]["files_indexed"] is None
    assert coverage["parts"][0]["files_with_symbols"] is None
    assert coverage["parts"][0]["files_with_calls"] is None


def test_class_members_use_definition_ids_and_keep_inventory_coverage(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("class A:\n    x: int\n    def work(self): pass\n")
    symbol = {"module": "m", "evidence_ids": ["class"]}
    a = dict(
        symbol,
        id="a",
        kind="class",
        qualified_name="m.A",
        attributes=[
            {"definition_id": "ax", "name": "x", "annotation": "int", "evidence_ids": ["field"]}
        ],
        member_inventories=[
            {"kind": "attribute", "status": "complete", "definition_ids": ["ax"]},
            {"kind": "method", "status": "partial", "definition_ids": ["aw"]},
        ],
    )
    symbols = [
        a,
        dict(
            symbol,
            id="aw",
            kind="function",
            qualified_name="m.A.work",
            lexical_parent_id="a",
            method_kind="instance",
        ),
        dict(symbol, id="b", kind="class", qualified_name="m.B"),
        dict(symbol, id="bw", kind="method", qualified_name="m.B.work", lexical_parent_id="b"),
    ]
    topology = {
        "version": 1,
        "components": [],
        "modules": [],
        "edges": [],
        "locations": {"class": {"path": "m.py", "line": 1}, "field": {"path": "m.py", "line": 2}},
        "explorer": [
            {"language": "python", "symbols": symbols, "files": [{"module": "m", "path": "m.py"}]}
        ],
    }
    path = tmp_path / "cache" / "sample.sqlite"
    publish_snapshot(
        path,
        SnapshotIdentity("r", "c", "s"),
        lambda db: populate(db, topology, tmp_path),
        "partial",
    )
    classes = query(path, tmp_path, "children", {"parent": "module:m"})["items"]
    assert [(row["id"], row["member_coverage"]) for row in classes] == [
        ("definition:a", {"method": "partial", "property": "complete"}),
        ("definition:b", {"method": "unknown", "property": "unknown"}),
    ]
    method, prop = query(path, tmp_path, "children", {"parent": "definition:a"})["items"]
    assert (method["id"], method["kind"], method["method_kind"]) == (
        "definition:aw",
        "method",
        "instance",
    )
    assert (prop["id"], prop["kind"], prop["annotation"]) == ("definition:ax", "property", "int")
    assert query(path, tmp_path, "source", {"reference": prop["source"]})["line"] == 2


def test_import_evidence_pages_indexed_locations_beyond_the_report_sample(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("import b\nimport b\nimport b\n")
    imports = [
        {
            "id": f"site-{line}",
            "source_module": "a",
            "target_module": "b",
            "resolution": "local",
            "evidence_class": "FACT",
            "evidence_ids": [str(line)],
        }
        for line in range(1, 4)
    ]
    locations = {str(line): {"path": "a.py", "line": line} for line in range(1, 4)}
    topology = {
        "version": 1,
        "components": [{"id": name, "name": name, "parent": None} for name in ("from", "to")],
        "modules": [
            {"name": "a", "component": "from", "path": "a.py"},
            {"name": "b", "component": "to", "path": "b.py"},
        ],
        "edges": [],
        "component_edges": [
            {
                "id": "edge",
                "source": "from",
                "target": "to",
                "resolution": "resolved",
                "evidence_total": 4,
                "evidence": [locations["1"]],
            }
        ],
        "locations": locations,
        "explorer": [{"language": "python", "imports": imports}],
    }
    path = tmp_path / "cache" / "sample.sqlite"
    publish_snapshot(
        path,
        SnapshotIdentity("rev", "contract", "tree"),
        lambda db: populate(db, topology, tmp_path),
        "partial",
    )
    first = query(
        path, tmp_path, "evidence", {"relation": "relation:component_import:edge", "limit": 2}
    )
    assert [row["line"] for row in first["items"]] == [1, 2]
    assert first["evidence_truncated"]
    assert (first["total"], first["evidence_total"]) == (3, 4)
    page = query(
        path,
        tmp_path,
        "evidence",
        {"relation": "relation:component_import:edge", "cursor": first["next_cursor"]},
    )
    assert [row["line"] for row in page["items"]] == [3]
    assert page["next_cursor"] is None


def test_source_candidate_links_both_sites_without_becoming_a_story_call(tmp_path: Path) -> None:
    (tmp_path / "entry.py").write_text("from model import build\nbuild()\n")
    (tmp_path / "model.py").write_text("def build(): pass\n")
    parts = [{"name": m, "component": None, "path": m + ".py"} for m in ("entry", "model")]
    topology = {
        "version": 1,
        "components": [],
        "modules": parts,
        "edges": [],
        "locations": {
            "site": {"path": "entry.py", "line": 2},
            "decl": {"path": "model.py", "line": 1},
        },
        "explorer": [
            {
                "language": "python",
                "source_call_candidates": [
                    {
                        "source_module": "entry",
                        "target_module": "model",
                        "target": "model.build",
                        "expression": "build",
                        "call_evidence": "site",
                        "declaration_evidence": "decl",
                    }
                ],
            }
        ],
    }
    path = tmp_path / "cache" / "sample.sqlite"
    publish_snapshot(
        path,
        SnapshotIdentity("rev", "contract", "tree"),
        lambda db: populate(db, topology, tmp_path),
        "partial",
    )
    (edge,) = query(path, tmp_path, "map", {"view": "modules"})["edges"]
    assert (edge["source"], edge["target"], edge["kind"], edge["resolution"]) == (
        "module:entry",
        "module:model",
        "source_call",
        "candidate",
    )
    (site,) = query(path, tmp_path, "relations", {"aggregate": edge["aggregate_id"]})["items"]
    assert site["declaration"] == "model.build"
    locations = query(path, tmp_path, "evidence", {"relation": site["id"]})["items"]
    assert [(loc["role"], loc["path"], loc["line"]) for loc in locations] == [
        ("call_site", "entry.py", 2),
        ("declaration", "model.py", 1),
    ]
    assert query(path, tmp_path, "source", {"reference": locations[1]["reference"]})["line"] == 1
    assert query(path, tmp_path, "story", {"id": site["id"]})["status"] == "UNKNOWN"


def test_snapshot_ids_separate_elements_and_relations_with_the_same_names(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def work(): pass\n")
    identity = SnapshotIdentity("rev", "contract", "tree")
    path = tmp_path / "snapshot.sqlite"
    local_edge = {"id": "same", "source": "app", "target": "system", "resolution": "resolved"}
    topology = {
        "version": 1,
        "components": [
            {"id": "app", "name": "app", "parent": None},
            {"id": "system", "name": "system", "parent": "app"},
        ],
        "modules": [
            {"name": "app", "component": "app", "path": "app.py"},
            {"name": "system", "component": "system", "path": "system.py"},
        ],
        "edges": [local_edge, dict(local_edge, id="external", resolution="external")],
        "component_edges": [local_edge],
        "explorer": [
            {
                "symbols": [
                    {
                        "id": "app",
                        "kind": "function",
                        "module": "app",
                        "qualified_name": "app.work",
                        "evidence_ids": [],
                    }
                ],
                "calls": [
                    {
                        "id": "same",
                        "source_module": "app",
                        "source_definition_id": "app",
                        "target_definition_id": "app",
                        "expression": "work",
                        "targets": ["app.work"],
                        "status": "resolved",
                        "candidates_truncated": False,
                        "evidence_ids": [],
                    }
                ],
            }
        ],
    }
    publish_snapshot(path, identity, lambda db: populate(db, topology, tmp_path), "complete")

    def read(operation: str, **args: object) -> dict[str, object]:
        return query(path, tmp_path, operation, args)

    (app,) = read("overview")["items"]
    children = {item["kind"]: item for item in read("children", parent=app["id"])["items"]}
    module, component = children["module"], children["component"]
    (system_module,) = read("children", parent=component["id"])["items"]
    (definition,) = read("children", parent=module["id"])["items"]
    assert len({app["id"], module["id"], definition["id"], component["id"], "system"}) == 5
    assert module["component"] == app["id"]
    assert read("source", reference=module["source"])["lines"] == ["def work(): pass"]
    (component_edge,) = read("relations", element=app["id"], direction="out")["items"]
    assert component_edge["target"] == component["id"]
    (module_edge,) = read("relations", element=system_module["id"], direction="in")["items"]
    assert module_edge["source"] == module["id"]
    outbound = read("relations", element=module["id"], direction="out")["items"]
    external = next(edge for edge in outbound if edge["resolution"] == "external")
    assert external["target_name"] == system_module["name"]
    assert external["target"] != system_module["id"]
    (call,) = read("relations", element=definition["id"], direction="out")["items"]
    assert call["target"] == definition["id"]
    assert call["candidates"] == [definition["id"]]
    assert call["source_owner"] == module["id"]
    assert read("story", id=call["id"])["items"] == [call]
    assert read("story", id=module_edge["id"])["status"] == "UNKNOWN"
    for edge in (module_edge, component_edge):
        assert read("evidence", relation=edge["id"])["relation"] == edge
    assert read("relations", element="app")["element_status"] == "unknown"


def test_query_preserves_ids_in_a_legacy_snapshot(tmp_path: Path) -> None:
    identity = SnapshotIdentity("rev", "contract", "tree")
    current = cache_path(tmp_path / "cache", tmp_path, identity)
    legacy = current.with_name(identity.key(4) + ".sqlite3")
    topology = {"version": 1, "components": [], "modules": [], "edges": []}
    publish_snapshot(current, identity, lambda db: populate(db, topology, tmp_path), "partial")
    item = {"id": "app", "name": "app", "parent": "system", "kind": "module"}
    with closing(sqlite3.connect(current)) as db, db:
        db.execute("PRAGMA user_version=4")
        db.execute(
            "INSERT INTO element VALUES ('app','app','module','system',?)", (json.dumps(item),)
        )
    current.rename(legacy)
    assert query(legacy, tmp_path, "overview", {})["items"] == [item]
    assert query(legacy, tmp_path, "relations", {"element": "app"})["element_status"] == "known"
