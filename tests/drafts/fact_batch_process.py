# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Draft RED tests for the not-yet-implemented process batch transport."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from archkeel.analyzer.process import ProcessCollector
from archkeel.check.fact_batch_store import FactBatchTransaction, SQLiteFactBatchStore
from archkeel.ir.facts import EvidenceClass, SnapshotStatus
from archkeel.ir.facts_codec import encode_fact_batch, parse_evidence, parse_record
from archkeel.ir.fact_batches import FactBatch
from archkeel.ir.protocol import (
    CollectionError,
    CollectionErrorKind,
    CollectionRequest,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
)


def _collection_request(root: Path) -> CollectionRequest:
    return CollectionRequest(
        SnapshotInput(str(root), "a" * 40, False),
        SourceScope(("src",), "app"),
        TypeScriptSettings(),
    )


def _batch_request(root: Path, snapshot_id: str):
    from archkeel.ir.fact_batches import FactBatchRequest

    return FactBatchRequest(_collection_request(root), snapshot_id)


def _batch_bytes(snapshot_id: str, sequence: int = 0) -> bytes:
    evidence_id = f"EVIDENCE-{sequence}"
    record_id = f"FACT-{sequence}"
    evidence = parse_evidence(
        {
            "id": evidence_id,
            "file": "src/main.ts",
            "line": 1,
            "end_line": 1,
            "column": 0,
            "excerpt": "export const value = 1;",
        }
    )
    record = parse_record(
        {
            "id": record_id,
            "evidence_class": EvidenceClass.UNKNOWN.value,
            "area": "source",
            "kind": "unresolved_import",
            "title": "Import resolution is incomplete",
            "subjects": ["src/main.ts"],
            "evidence_ids": [evidence_id],
            "rule_ids": [],
            "fact_ids": [],
            "provenance": ["collector"],
            "data": {"target": "pending"},
        }
    )
    return encode_fact_batch(FactBatch(snapshot_id, sequence, (record,), (evidence,)))


def _length_prefixed(payload: bytes) -> bytes:
    return len(payload).to_bytes(4, "big") + payload


def _store(tmp_path: Path) -> tuple[SQLiteFactBatchStore, FactBatchTransaction]:
    store = SQLiteFactBatchStore(tmp_path / "facts.sqlite", max_frame_bytes=4096)
    previous = store.begin(
        snapshot_id="snapshot-previous",
        source_digest="b" * 64,
        contract_identity="contracts-v1",
    )
    previous.append(_batch_bytes("snapshot-previous"))
    previous.finalize()
    transaction = store.begin(
        snapshot_id="snapshot-new",
        source_digest="c" * 64,
        contract_identity="contracts-v1",
    )
    return store, transaction


def _assert_previous_snapshot(store: SQLiteFactBatchStore) -> None:
    assert store.snapshot_status("snapshot-previous") is SnapshotStatus.INCOMPLETE
    assert len(store.read_batch("snapshot-previous", sequence=0).records) == 1
    assert store.snapshot_status("snapshot-new") is None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    if sys.platform.startswith("linux"):
        try:
            state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except (FileNotFoundError, ProcessLookupError):
            return False
        return state != "Z"
    return True


def _wait_for_stop(pid: int) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and _alive(pid):
        time.sleep(0.02)
    assert not _alive(pid), f"collector descendant {pid} remained alive after cleanup"


def test_typescript_process_streams_canonical_frames_to_incomplete_snapshot(tmp_path: Path):
    root = tmp_path / "public-fixture"
    root.mkdir()
    (root / "tsconfig.json").write_text(
        '{"compilerOptions":{"module":"NodeNext","moduleResolution":"NodeNext"},'
        '"include":["src"]}'
    )
    (root / "src/main.ts").parent.mkdir(parents=True)
    (root / "src/main.ts").write_text(
        'import { answer } from "./answer.js";\nexport function main() { return answer(); }\n'
    )
    (root / "src/answer.ts").write_text("export function answer() { return 42; }\n")
    request = _batch_request(root, "snapshot-stream")
    source_digest = hashlib.sha256(b"public typescript fixture v1").hexdigest()
    store = SQLiteFactBatchStore(tmp_path / "facts.sqlite")
    transaction = store.begin(
        snapshot_id=request.snapshot_id,
        source_digest=source_digest,
        contract_identity="contracts-v1",
    )
    child = (
        "from archkeel.analyzer.typescript.collect import _Collection\n"
        "def forbidden(*args, **kwargs): raise RuntimeError('full SourceFacts path used')\n"
        "_Collection.facts = forbidden\n"
        "from archkeel.analyzer.typescript.entry import main\n"
        "raise SystemExit(main())\n"
    )
    collector = ProcessCollector((sys.executable, "-I", "-B", "-c", child))

    error = collector.collect_batches(request, transaction.append)
    assert error is None
    assert transaction.finalize() is SnapshotStatus.INCOMPLETE

    batches = []
    for sequence in range(32):
        try:
            batches.append(store.read_batch(request.snapshot_id, sequence=sequence))
        except KeyError:
            break
    assert batches
    assert [batch.sequence for batch in batches] == list(range(len(batches)))
    assert all(batch.snapshot_id == request.snapshot_id for batch in batches)
    assert any(batch.records and batch.evidence for batch in batches)
    assert store.snapshot_status(request.snapshot_id) is SnapshotStatus.INCOMPLETE


def test_typescript_batch_producer_does_not_build_complete_source_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from archkeel.analyzer.typescript import collect as collector_module

    root = tmp_path / "public-fixture"
    root.mkdir()
    (root / "tsconfig.json").write_text(
        '{"compilerOptions":{"module":"NodeNext","moduleResolution":"NodeNext"},'
        '"include":["src"]}'
    )
    (root / "src").mkdir()
    (root / "src/main.ts").write_text("export const value = 1;\n")

    def forbidden_full_facts(*_args, **_kwargs):
        pytest.fail("batch producer called _Collection.facts() and materialized SourceFacts")

    monkeypatch.setattr(collector_module._Collection, "facts", forbidden_full_facts)
    batches = tuple(collector_module.iter_fact_batches(_collection_request(root), "snapshot-test"))

    assert batches
    assert all(batch.snapshot_id == "snapshot-test" for batch in batches)
    assert [batch.sequence for batch in batches] == list(range(len(batches)))


@pytest.mark.parametrize("failure", ["oversized", "truncated"])
def test_bad_process_frame_aborts_new_snapshot_and_preserves_previous(
    tmp_path: Path, failure: str
):
    snapshot_id = "snapshot-new"
    valid = _length_prefixed(_batch_bytes(snapshot_id))
    if failure == "oversized":
        tail = (4097).to_bytes(4, "big")
    else:
        tail = (20).to_bytes(4, "big") + b"short"
    child = (
        "import sys; sys.stdin.buffer.read(); "
        f"sys.stdout.buffer.write({valid + tail!r}); sys.stdout.buffer.flush()"
    )
    store, transaction = _store(tmp_path)
    request = _batch_request(tmp_path, snapshot_id)
    result = ProcessCollector((sys.executable, "-B", "-c", child)).collect_batches(
        request, transaction.append
    )

    assert isinstance(result, CollectionError)
    assert result.kind is CollectionErrorKind.PROTOCOL_ERROR
    transaction.abort()
    _assert_previous_snapshot(store)


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX process-group cleanup proof")
def test_batch_process_timeout_aborts_snapshot_and_stops_descendant(tmp_path: Path):
    snapshot_id = "snapshot-new"
    frame = _length_prefixed(_batch_bytes(snapshot_id))
    pid_path = tmp_path / "descendant.pid"
    child = (
        "import pathlib, subprocess, sys, time; sys.stdin.buffer.read(); "
        "descendant = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
        f"pathlib.Path({str(pid_path)!r}).write_text(str(descendant.pid)); "
        f"sys.stdout.buffer.write({frame!r}); sys.stdout.buffer.flush(); time.sleep(30)"
    )
    store, transaction = _store(tmp_path)
    request = _batch_request(tmp_path, snapshot_id)
    result = ProcessCollector(
        (sys.executable, "-B", "-c", child), timeout_seconds=0.2
    ).collect_batches(request, transaction.append)

    assert isinstance(result, CollectionError)
    assert result.kind is CollectionErrorKind.TIMEOUT
    assert pid_path.is_file()
    transaction.abort()
    _assert_previous_snapshot(store)
    _wait_for_stop(int(pid_path.read_text()))
