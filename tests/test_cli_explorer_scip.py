# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Optional SCIP evidence keeps its own provenance and cache identity."""

import hashlib
import json
import sqlite3
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


@pytest.mark.parametrize("manifest", [False, True])
def test_scip_stores_pointwise_evidence_without_an_explorer_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, manifest: bool
):
    path = tmp_path / "index.scip"
    path.write_bytes(b"index")
    sidecar = path.with_name("index.scip.manifest.json")
    if manifest:
        sidecar.write_text("{}")
    source = tmp_path / "lib.rs"
    source.write_text("fn run() { f(); }\nfn f() {}\n")
    cargo = b'[package]\nname = "owner"\n'
    (tmp_path / "Cargo.toml").write_bytes(cargo)
    assert parse(["explore", "--scip", str(path)]).scip_index == path
    assert parse(["studio"]).scip_index is None
    artifact = core_explorer_scip.ScipIndex.read(path)
    baseline = SnapshotIdentity("rev", "config", "source")
    identity = artifact.bind(baseline)
    assert baseline.key() != identity.key()

    frame = _frame()
    calls = frame["explorer"][0]["calls"]
    original = calls[0]
    calls.extend(
        [original | {"id": name} for name in ("std", "dep", "unmapped", "missing", "macro")]
    )
    calls[-1]["reason"] = "Macro expansion can contain calls that are not read"
    calls.append(original | {"id": "native", "status": "resolved", "targets": ["app.f"]})
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    fingerprint = {"lib.rs": digest, "Cargo.toml": hashlib.sha256(cargo).hexdigest()}
    header = dict(
        index_sha256=artifact.index_sha256,
        manifest_sha256=artifact.manifest_sha256,
        source_files={"lib.rs": digest},
    )
    reference = dict(path="lib.rs", start_line=0, start_column=11, end_line=0, end_column=12)
    rows = [
        dict(
            call_id="c",
            status="local_resolved",
            provenance="scip_verified",
            dispatch_kind="trait_dispatch",
            target_definition_id="f",
            evidence_id="def",
            path="lib.rs",
            line=2,
            reference=reference,
        ),
        dict(
            call_id="std",
            status="external_std",
            provenance="scip_verified",
            crate_name="core",
            crate_version=None,
            symbol_path="option/Option#map().",
            reference=reference,
        ),
        dict(
            call_id="dep",
            status="external_dep",
            provenance="scip_verified",
            crate_name="dep",
            crate_version="1.2.3",
            symbol_path="Codec#run().",
            reference=reference,
        ),
        dict(
            call_id="unmapped",
            status="unresolved",
            provenance="scip_verified",
            reason="unmapped_scip_ref",
            reference=reference,
        ),
        dict(call_id="missing", status="unresolved", provenance=None, reason="no_scip_ref"),
        dict(call_id="macro", status="unresolved", provenance="ast_exact", reason="macro_call"),
    ]

    def exchange(worker, operation, payload, *, arguments, output):
        assert worker.endswith("archkeel-rust-collector")
        assert operation == "scip-evidence"
        assert arguments == (str(tmp_path), str(path)) + ((str(sidecar),) if manifest else ())
        request = json.loads(payload)
        assert request["local_packages"] == ["owner"]
        assert request["definitions"] == [{"id": "f", "evidence_id": "def", "kind": "function"}]
        assert request["calls"] == [
            {
                "id": name,
                "path": "lib.rs",
                "line": 1,
                "module": "app",
                "expression": "f",
                "macro_call": name == "macro",
            }
            for name in ("c", "std", "dep", "unmapped", "missing", "macro")
        ]
        for row in [header, *rows]:
            output.write(json.dumps(row).encode() + b"\n")
        return b"", 0

    def build(db):
        populate(db, frame, tmp_path)
        core_explorer_scip._store_resolution(
            db, artifact, tmp_path / "archkeel-core", tmp_path, fingerprint, frame
        )

    monkeypatch.setattr(core_explorer_scip, "exchange", exchange)
    database = tmp_path / "cache" / "view.sqlite3"
    publish_snapshot(database, identity, build, "UNKNOWN")
    with sqlite3.connect(database) as db:
        assert db.execute(
            "SELECT status, provenance, reason, COUNT(*) FROM call_resolution "
            "GROUP BY status, provenance, reason ORDER BY status, provenance, reason"
        ).fetchall() == [
            ("external_dep", "scip_verified", None, 1),
            ("external_std", "scip_verified", None, 1),
            ("local_resolved", "ast_exact", None, 1),
            ("local_resolved", "scip_verified", None, 1),
            ("unresolved", None, "no_scip_ref", 1),
            ("unresolved", "ast_exact", "macro_call", 1),
            ("unresolved", "scip_verified", "unmapped_scip_ref", 1),
        ]
        assert db.execute("SELECT sum(count) FROM call_resolution_count").fetchone() == (7,)
        assert db.execute("SELECT * FROM scip_artifact").fetchone() == (
            artifact.index_sha256,
            artifact.manifest_sha256,
        )
        assert db.execute(
            "SELECT canonical_target_definition_id, dispatch_kind, reference_start_column "
            "FROM call_resolution WHERE call_id IN ('c', 'native') ORDER BY call_id"
        ).fetchall() == [("f", "trait_dispatch", 11), ("f", "direct", None)]
        assert db.execute(
            "SELECT crate_name, crate_version, symbol_path FROM call_resolution WHERE call_id='dep'"
        ).fetchone() == ("dep", "1.2.3", "Codec#run().")
    baseline_db = tmp_path / "cache" / "baseline.sqlite3"
    publish_snapshot(baseline_db, baseline, lambda db: populate(db, frame, tmp_path), "UNKNOWN")
    for section, args in (
        ("relations", {"element": "module:app", "scope": "unlinked_calls"}),
        ("evidence", {"relation": "relation:call:c"}),
        ("story", {"id": "relation:call:c"}),
    ):
        actual = query(database, tmp_path, section, args)
        expected = query(baseline_db, tmp_path, section, args)
        assert actual.keys() == expected.keys()
        assert all(actual[key] == expected[key] for key in actual if key != "snapshot")

    header["source_files"] = {"lib.rs": "a" * 64}
    with pytest.raises(CoreError, match="source fingerprint"):
        publish_snapshot(tmp_path / "cache" / "stale.sqlite3", identity, build, "UNKNOWN")
    header["source_files"] = {"lib.rs": digest}

    rows[0]["line"] = 1
    with pytest.raises(CoreError, match="outside the verified scan"):
        publish_snapshot(tmp_path / "cache" / "invalid.sqlite3", identity, build, "UNKNOWN")
    assert not (tmp_path / "cache" / "invalid.sqlite3").exists()
    rows[0]["line"] = 2

    rows.pop()
    with pytest.raises(CoreError, match="omitted native call IDs"):
        publish_snapshot(tmp_path / "cache" / "incomplete.sqlite3", identity, build, "UNKNOWN")
    path.write_bytes(b"edited")
    assert core_explorer_scip.ScipIndex.read(path).bind(baseline).key() != identity.key()
    with pytest.raises(CoreError, match="changed"):
        artifact.confirm()
