# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Optional SCIP evidence keeps its own provenance and cache identity."""

import hashlib
import json
import signal
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

import pytest
from corpus_support import commit_tree

from archkeel import explorer_mcp
from archkeel.cli import core_explorer_http, core_explorer_scip, core_only
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

    def exchange(worker, operation, payload, _stderr, *, arguments, output):
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
            "rust",
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

    # Separate read-only call_resolution projection works cleanly with and without SCIP tables.
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
    assert filtered["items"][0]["crate_name"] == "dep"
    assert filtered["items"][0]["crate_version"] == "1.2.3"
    with pytest.raises(ValueError, match="invalid call_resolution status"):
        query(database, tmp_path, "call_resolution", {"status": "bogus"})

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


def _varint(value: int) -> bytes:
    encoded = bytearray()
    while value > 127:
        encoded.append((value & 127) | 128)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def _bytes(field: int, value: bytes) -> bytes:
    return _varint(field << 3 | 2) + _varint(len(value)) + value


def _scip(
    source: bytes, *, malformed: bool = False, invalid_utf8: bool = False, with_text: bool = True
) -> bytes:
    definition = b"\xff\xfe" if invalid_utf8 else b"rust-analyzer cargo app 0.1.0 Thing#get()."
    document = _bytes(1, b"src/lib.rs") + b"\x30\x01"
    if with_text:
        document += _bytes(5, source)
    for line, text in enumerate(source.splitlines()):
        if b"get(" not in text:
            continue
        start = text.index(b"get(")
        roles = b"\x18\x01" if b"fn get" in text else b""
        position = _bytes(1, bytes([line, start, start + 3]))
        if malformed:
            position = _bytes(8, b"\x00\x00")
        document += _bytes(2, position + _bytes(2, definition) + roles)
    return _bytes(2, document)


@pytest.fixture
def scip_project(tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    source = root / "src" / "lib.rs"
    source.write_text(
        "pub struct Thing;\n"
        "impl Thing { fn get(&self) -> usize { 1 } }\n"
        "pub fn read(value: &Thing) -> usize { value.get() }\n",
        encoding="utf-8",
    )
    (root / "Cargo.toml").write_text('[package]\nname = "app"\nversion = "0.1.0"\n')
    commit_tree(root)
    cache = tmp_path / "cache"
    artifact = tmp_path / "example.scip"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    monkeypatch.setattr(core_explorer_http._ExplorerServer, "serve_forever", lambda self: None)
    return source, artifact, cache


def _run_explore(source: Path, artifact: Path | None = None) -> int:
    args = ["explore", "--root", str(source.parent.parent), "--no-open", "--json"]
    if artifact is not None:
        args.extend(("--scip", str(artifact)))
    return core_only.run(args)


@pytest.mark.parametrize("with_manifest", [False, True])
def test_real_scip_worker_publishes_current_and_refuses_stale_source(
    scip_project, capsys: pytest.CaptureFixture[str], with_manifest: bool
):
    source, artifact, cache = scip_project
    assert _run_explore(source) == 0
    no_index = json.loads(capsys.readouterr().out)
    data = _scip(source.read_bytes(), with_text=not with_manifest)
    artifact.write_bytes(data)
    if with_manifest:
        artifact.with_name(artifact.name + ".manifest.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "index_sha256": hashlib.sha256(data).hexdigest(),
                    "files": {"src/lib.rs": hashlib.sha256(source.read_bytes()).hexdigest()},
                }
            )
        )
    assert _run_explore(source, artifact) == 0
    indexed = json.loads(capsys.readouterr().out)
    assert indexed["snapshot"] != no_index["snapshot"]
    with sqlite3.connect(indexed["snapshot"]) as db:
        assert db.execute(
            "SELECT status, provenance, dispatch_kind FROM call_resolution"
        ).fetchall() == [("local_resolved", "scip_verified", "direct")]
        target = db.execute(
            "SELECT canonical_target_definition_id FROM call_resolution"
        ).fetchone()[0]
        assert db.execute(
            "SELECT 1 FROM element WHERE id=?", (f"definition:{target}",)
        ).fetchone() == (1,)
    with sqlite3.connect(no_index["snapshot"]) as db:
        assert (
            db.execute("SELECT name FROM sqlite_schema WHERE name='call_resolution'").fetchone()
            is None
        )
    before = sorted(cache.rglob("*.sqlite3"))
    source.write_bytes(source.read_bytes().replace(b"{ 1 }", b"{ 2 }"))
    assert _run_explore(source, artifact) == 2
    refusal = "stale SCIP source" if with_manifest else "SCIP document text differs from source"
    assert refusal in capsys.readouterr().out
    assert sorted(cache.rglob("*.sqlite3")) == before
    assert not list(cache.rglob(".building.sqlite3"))


@pytest.mark.parametrize("malformed", [False, True])
def test_real_scip_worker_refuses_unbound_or_malformed_document(
    scip_project, capsys: pytest.CaptureFixture[str], malformed: bool
):
    source, artifact, cache = scip_project
    artifact.write_bytes(_scip(source.read_bytes(), malformed=malformed, with_text=malformed))
    assert _run_explore(source, artifact) == 2
    refusal = capsys.readouterr()
    expected = "invalid SCIP field number" if malformed else "unbound or stale SCIP document"
    assert expected in refusal.out
    assert "panicked" not in refusal.out + refusal.err
    assert not list(cache.rglob("*.sqlite3"))


@pytest.mark.parametrize("interrupt", [False, True])
def test_real_scip_staging_rolls_back_on_signal_or_mid_launch_edit(
    scip_project,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    interrupt: bool,
):
    source, artifact, cache = scip_project
    artifact.write_bytes(_scip(source.read_bytes()))
    exchange = core_explorer_scip.exchange

    def after_worker(*args, **kwargs):
        result = exchange(*args, **kwargs)
        assert result == (b"", 0)
        assert len(list(cache.rglob(".building.sqlite3"))) == 1
        if interrupt:
            signal.raise_signal(signal.SIGINT)
        source.write_bytes(source.read_bytes().replace(b"{ 1 }", b"{ 2 }"))
        return result

    monkeypatch.setattr(core_explorer_scip, "exchange", after_worker)
    assert _run_explore(source, artifact) == (130 if interrupt else 2)
    result = capsys.readouterr()
    if interrupt:
        assert not result.out and "Traceback" not in result.err
    else:
        assert "the project changed during the Explorer scan" in result.out
    assert not list(cache.rglob("*.sqlite3"))


@pytest.mark.parametrize("with_manifest", [False, True])
def test_explore_auto_discovers_project_scip_and_falls_back_when_stale(
    scip_project, capsys: pytest.CaptureFixture[str], with_manifest: bool
):
    source, _artifact, cache = scip_project
    root = source.parent.parent
    assert _run_explore(source) == 0
    native_run = json.loads(capsys.readouterr().out)

    discovered = root / core_explorer_scip.DEFAULT_RUST_SCIP
    discovered.parent.mkdir(parents=True)
    data = _scip(source.read_bytes(), with_text=not with_manifest)
    discovered.write_bytes(data)
    if with_manifest:
        discovered.with_name(discovered.name + ".manifest.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "index_sha256": hashlib.sha256(data).hexdigest(),
                    "files": {"src/lib.rs": hashlib.sha256(source.read_bytes()).hexdigest()},
                }
            )
        )

    assert _run_explore(source) == 0
    auto_run = json.loads(capsys.readouterr().out)
    assert auto_run["snapshot"] != native_run["snapshot"]
    with sqlite3.connect(auto_run["snapshot"]) as db:
        assert db.execute("SELECT language, index_sha256 FROM scip_artifact").fetchall() == [
            ("rust", hashlib.sha256(data).hexdigest())
        ]
        assert db.execute("SELECT status, provenance FROM call_resolution").fetchall() == [
            ("local_resolved", "scip_verified")
        ]

    # --no-scip skips the discovered index and reuses the plain native snapshot.
    assert core_only.run(["explore", "--root", str(root), "--no-open", "--no-scip", "--json"]) == 0
    skipped = json.loads(capsys.readouterr().out)
    assert skipped["snapshot"] == native_run["snapshot"]

    # Mutual exclusion between --scip and --no-scip.
    with pytest.raises(ValueError, match="--scip or --no-scip"):
        parse(["explore", "--scip", str(discovered), "--no-scip"])

    # Editing source makes the auto-discovered index stale: warn and fall back to native scan.
    source.write_bytes(source.read_bytes().replace(b"{ 1 }", b"{ 2 }"))
    assert _run_explore(source) == 0
    captured = capsys.readouterr()
    fallback = json.loads(captured.out)
    assert "using native scan" in captured.err
    with sqlite3.connect(fallback["snapshot"]) as db:
        assert (
            db.execute("SELECT name FROM sqlite_schema WHERE name='call_resolution'").fetchone()
            is None
        )
    assert not list(cache.rglob(".building.sqlite3"))

    # Explicit --scip stays fail-closed on the same stale file.
    assert _run_explore(source, discovered) == 2
    refusal = "stale SCIP source" if with_manifest else "SCIP document text differs from source"
    assert refusal in capsys.readouterr().out

    # Invalid UTF-8 symbol in auto-discovered index (no "SCIP" substring in error) still degrades
    # gracefully to the native scan via the worker's structured scip_artifact_error tag, while
    # explicit --scip stays fail-closed.
    corrupt = _scip(source.read_bytes(), invalid_utf8=True, with_text=not with_manifest)
    discovered.write_bytes(corrupt)
    if with_manifest:
        discovered.with_name(discovered.name + ".manifest.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "index_sha256": hashlib.sha256(corrupt).hexdigest(),
                    "files": {"src/lib.rs": hashlib.sha256(source.read_bytes()).hexdigest()},
                }
            )
        )
    assert _run_explore(source) == 0
    utf8_fallback = capsys.readouterr()
    assert "invalid utf-8 sequence" in utf8_fallback.err
    assert "using native scan" in utf8_fallback.err
    assert "scip_artifact_error" not in utf8_fallback.err
    assert _run_explore(source, discovered) == 2
    assert "invalid utf-8 sequence" in capsys.readouterr().out


def test_auto_discovery_does_not_swallow_worker_infrastructure_failure(
    scip_project, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    source, _artifact, cache = scip_project
    root = source.parent.parent
    discovered = root / core_explorer_scip.DEFAULT_RUST_SCIP
    discovered.parent.mkdir(parents=True)
    discovered.write_bytes(_scip(source.read_bytes()))

    def crashed_worker(_worker, _op, _req, stderr, **_kwargs):
        stderr.append(b"segmentation fault")
        return b"", 139

    monkeypatch.setattr(core_explorer_scip, "exchange", crashed_worker)
    assert _run_explore(source) == 2
    captured = capsys.readouterr()
    assert "worker failed (exit 139)" in captured.out
    assert "using native scan" not in captured.err
    assert not list(cache.rglob("*.sqlite3"))


def test_http_and_mcp_expose_separate_scip_call_resolution_equally(
    scip_project, capsys: pytest.CaptureFixture[str]
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

    explorer_mcp._query_tools(Tools(), snapshot, root)
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
