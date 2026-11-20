# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Explorer navigation and source evidence refer to the same scan."""

import sqlite3
from pathlib import Path

import pytest

from archkeel.explorer_queries import populate, query
from archkeel.explorer_store import SnapshotIdentity, publish_snapshot


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
    assert page["coverage"]["truncated"] and page["items"][0]["id"] == "a"
    assert (
        query(path, tmp_path, "children", {"cursor": page["next_cursor"]})["items"][0]["id"] == "b"
    )
    known = query(path, tmp_path, "relations", {"element": "a", "direction": "in"})
    missing = query(path, tmp_path, "relations", {"element": "missing"})
    assert known["element_status"] == "known" and known["items"] == []
    assert missing["element_status"] == "unknown" and missing["items"] == []
    ref = query(path, tmp_path, "evidence", {"relation": "edge"})["items"][0]["reference"]
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
                "files": [{"module": "m", "path": "f.ts"}],
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
    result = query(path, tmp_path, "story", {"id": "call"})
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
    classes = query(path, tmp_path, "children", {"parent": "m"})["items"]
    assert [(row["id"], row["member_coverage"]) for row in classes] == [
        ("a", {"method": "partial", "property": "complete"}),
        ("b", {"method": "unknown", "property": "unknown"}),
    ]
    method, prop = query(path, tmp_path, "children", {"parent": "a"})["items"]
    assert (method["id"], method["kind"], method["method_kind"]) == ("aw", "method", "instance")
    assert (prop["id"], prop["kind"], prop["annotation"]) == ("ax", "property", "int")
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
    first = query(path, tmp_path, "evidence", {"relation": "edge", "limit": 2})
    assert [row["line"] for row in first["items"]] == [1, 2]
    assert first["evidence_truncated"]
    assert (first["total"], first["evidence_total"]) == (3, 4)
    page = query(path, tmp_path, "evidence", {"relation": "edge", "cursor": first["next_cursor"]})
    assert [row["line"] for row in page["items"]] == [3]
    assert page["next_cursor"] is None
