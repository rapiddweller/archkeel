# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Optional SCIP evidence keeps its own provenance and cache identity."""

import json
from pathlib import Path

import pytest

from archkeel.cli import core_explorer_scip
from archkeel.cli.core_arguments import parse
from archkeel.cli.core_json import CoreError
from archkeel.explorer_queries import Row, populate, query
from archkeel.explorer_store import SnapshotIdentity, publish_snapshot


def _frame() -> Row:
    return {
        "version": 1,
        "components": [],
        "edges": [],
        "modules": [{"name": "app", "path": "lib.rs", "component": None}],
        "locations": {"call": {"path": "lib.rs", "line": 1}, "def": {"path": "lib.rs", "line": 2}},
        "explorer": [
            {
                "language": "rust",
                "symbols": [
                    {
                        "kind": "function",
                        "id": "f",
                        "qualified_name": "app.f",
                        "module": "app",
                        "evidence_ids": ["def"],
                    },
                ],
                "calls": [
                    {
                        "id": "c",
                        "source_module": "app",
                        "status": "unresolved",
                        "evidence_class": "FACT",
                        "expression": "f",
                        "targets": [],
                        "candidates_truncated": False,
                        "evidence_ids": ["call"],
                    }
                ],
            }
        ],
    }


def test_scip_binding_keeps_the_native_call_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "index.scip"
    path.write_bytes(b"index")
    path.with_name("index.scip.manifest.json").write_text("{}")
    source = tmp_path / "lib.rs"
    source.write_text("fn run() { f(); }\nfn f() {}\n")
    assert parse(["explore", "--scip", str(path)]).scip_index == path
    assert parse(["studio"]).scip_index is None
    artifact = core_explorer_scip.ScipIndex.read(path)
    baseline = SnapshotIdentity("rev", "config", "source")
    identity = artifact.bind(baseline)
    assert baseline.key() != identity.key()
    digest = "d" * 64
    reply = dict(
        index_sha256=artifact.index_sha256,
        manifest_sha256=artifact.manifest_sha256,
        manifest_files={"lib.rs": digest},
        bindings=[
            dict(call_id="c", target_definition_id="f", evidence_id="def", path="lib.rs", line=2)
        ],
    )

    def exchange(worker, operation, payload, *, arguments):
        assert worker.endswith("archkeel-rust-collector")
        assert operation == "scip-evidence"
        assert arguments == (str(tmp_path), str(path), str(artifact.manifest))
        assert json.loads(payload) == {
            "calls": [{"id": "c", "path": "lib.rs", "line": 1, "module": "app", "expression": "f"}],
            "definitions": [{"id": "f", "evidence_id": "def", "kind": "function"}],
        }
        return json.dumps(reply).encode(), 0

    monkeypatch.setattr(core_explorer_scip, "exchange", exchange)
    frame = _frame()
    core_explorer_scip.enrich(
        artifact, tmp_path / "archkeel-core", tmp_path, {"lib.rs": digest}, frame
    )
    database = tmp_path / "cache" / "view.sqlite3"
    publish_snapshot(database, identity, lambda db: populate(db, frame, tmp_path), "UNKNOWN")
    rows = query(
        database, tmp_path, "relations", {"element": "module:app", "scope": "unlinked_calls"}
    )
    assert rows["coverage"]["scip"]["matched_calls"] == 1
    (link,) = rows["items"]
    assert link["target"] is None and link["resolution"] == "unresolved"
    assert link["scip_binding"] == {"provenance": "scip", "target": "definition:f"}
    result = query(database, tmp_path, "evidence", {"relation": link["id"]})
    declaration = result["items"][1]
    assert declaration["role"] == "scip_declaration"
    assert query(database, tmp_path, "source", {"reference": declaration["reference"]})["line"] == 2
    assert query(database, tmp_path, "story", {"id": link["id"]})["status"] == "unresolved"
    path.write_bytes(b"edited")
    assert core_explorer_scip.ScipIndex.read(path).bind(baseline).key() != identity.key()
    with pytest.raises(CoreError, match="changed"):
        artifact.confirm()

    with pytest.raises(CoreError, match="source fingerprint"):
        core_explorer_scip.enrich(artifact, tmp_path / "archkeel-core", tmp_path, {}, _frame())

    reply["bindings"][0]["line"] = 1
    with pytest.raises(CoreError, match="outside the verified scan"):
        core_explorer_scip.enrich(
            artifact, tmp_path / "archkeel-core", tmp_path, {"lib.rs": digest}, _frame()
        )
