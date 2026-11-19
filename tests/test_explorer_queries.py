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
