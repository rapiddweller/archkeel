# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read-only SCIP call_resolution query projection across Explorer SQLite, HTTP, and MCP."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

import pytest
from test_cli_explorer_scip import _frame, _run_explore, _scip
from test_cli_explorer_scip import scip_project as scip_project

from archkeel import explorer_mcp
from archkeel.cli import core_explorer_http, core_explorer_scip
from archkeel.explorer_queries import populate, query
from archkeel.explorer_store import SnapshotIdentity, publish_snapshot


def test_call_resolution_query_filters_counts_and_items_without_scip_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "index.scip"
    path.write_bytes(b"index")
    source = tmp_path / "lib.rs"
    source.write_text("fn run() { f(); }\nfn f() {}\n")
    cargo = b'[package]\nname = "owner"\n'
    (tmp_path / "Cargo.toml").write_bytes(cargo)
    artifact = core_explorer_scip.ScipIndex.read(path)
    baseline = SnapshotIdentity("rev", "config", "source")
    identity = artifact.bind(baseline)

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

    def exchange(_worker, _operation, _payload, _stderr, *, arguments, output):
        assert arguments == (str(tmp_path), str(path))
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
    baseline_db = tmp_path / "cache" / "baseline.sqlite3"
    publish_snapshot(baseline_db, baseline, lambda db: populate(db, frame, tmp_path), "UNKNOWN")

    absent = query(baseline_db, tmp_path, "call_resolution", {})
    assert absent["available"] is False
    assert absent["artifacts"] == [] and absent["counts"] == [] and absent["items"] == []
    present = query(database, tmp_path, "call_resolution", {"limit": 2})
    assert present["available"] is True
    assert present["artifacts"] == [
        {
            "language": "rust",
            "index_sha256": artifact.index_sha256,
            "manifest_sha256": artifact.manifest_sha256,
        }
    ]
    assert sum(row["count"] for row in present["counts"]) == 7
    assert len(present["items"]) == 2
    assert present["next_cursor"] == present["items"][-1]["call_id"]
    filtered = query(
        database,
        tmp_path,
        "call_resolution",
        {"element": "module:app", "status": "external_dep", "provenance": "scip_verified"},
    )
    assert filtered["element_status"] == "known"
    assert [row["call_id"] for row in filtered["items"]] == ["dep"]
    assert filtered["counts"] == [
        {
            "language": "rust",
            "status": "external_dep",
            "provenance": "scip_verified",
            "reason": None,
            "count": 1,
        }
    ]
    assert filtered["items"][0]["crate_name"] == "dep"
    assert filtered["items"][0]["crate_version"] == "1.2.3"
    only_unresolved = query(database, tmp_path, "call_resolution", {"status": "unresolved"})
    assert {row["status"] for row in only_unresolved["counts"]} == {"unresolved"}
    assert sum(row["count"] for row in only_unresolved["counts"]) == len(only_unresolved["items"])
    assert len(only_unresolved["items"]) == 3
    with pytest.raises(ValueError, match="invalid call_resolution status"):
        query(database, tmp_path, "call_resolution", {"status": "bogus"})


def test_http_and_mcp_expose_separate_scip_call_resolution_equally(
    scip_project,
    capsys: pytest.CaptureFixture[str],  # noqa: F811
):
    source, artifact, _cache = scip_project
    root = source.parent.parent
    artifact.write_bytes(_scip(source.read_bytes()))
    assert _run_explore(source, artifact) == 0
    snapshot = Path(json.loads(capsys.readouterr().out)["snapshot"])

    registered = {}

    class Tools:
        def tool(self, operation) -> None:
            registered[operation.__name__] = operation

    explorer_mcp._resolution_tools(Tools(), snapshot, root)
    assert "call_resolution" in registered

    with core_explorer_http._ExplorerServer(snapshot, root, None, 0) as server:
        with ThreadPoolExecutor(max_workers=1) as pool:
            live = pool.submit(ThreadingHTTPServer.serve_forever, server, 0.01)
            client = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                params = {"status": "local_resolved", "provenance": "scip_verified"}
                client.request("GET", f"/api/v1/call_resolution?{urlencode(params)}")
                response = client.getresponse()
                assert response.status == 200
                http_payload = json.load(response)
                mcp_payload = registered["call_resolution"](**params)
                assert http_payload == mcp_payload
                assert http_payload["available"] is True
                assert len(http_payload["items"]) == 1
                assert http_payload["items"][0]["dispatch_kind"] == "direct"
                assert http_payload["items"][0]["target_element_id"].startswith("definition:")
            finally:
                client.close()
                server.shutdown()
                live.result(timeout=5)
