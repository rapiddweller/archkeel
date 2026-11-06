# ArchKeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The private fact-batch store preserves canonical records without claiming validation."""

import json

import pytest


def _batch(
    sequence: int = 0,
    *,
    snapshot_id: str = "snapshot-1",
    excerpt: str = "call()",
) -> bytes:
    from archkeel.ir.fact_batches import FactBatch
    from archkeel.ir.facts import EvidenceClass
    from archkeel.ir.facts_codec import encode_fact_batch, parse_evidence, parse_record

    evidence_id = f"EVIDENCE-{sequence + 1}"
    record_id = f"FACT-{sequence + 1}"
    evidence = parse_evidence(
        {
            "id": evidence_id,
            "file": "src/example.py",
            "line": 1,
            "end_line": 1,
            "column": 0,
            "excerpt": excerpt,
        }
    )
    record = parse_record(
        {
            "id": record_id,
            "evidence_class": EvidenceClass.UNKNOWN.value,
            "area": "source",
            "kind": "unresolved_import",
            "title": "Import target is unknown",
            "subjects": ["src/example.py"],
            "evidence_ids": [evidence_id],
            "rule_ids": [],
            "fact_ids": [],
            "provenance": ["collector"],
            "data": {"target": "optional_module"},
        }
    )
    return encode_fact_batch(FactBatch(snapshot_id, sequence, (record,), (evidence,)))


def _sqlite_artifact_bytes(path):
    return sum(
        candidate.stat().st_size
        for candidate in (
            path,
            path.with_name(f"{path.name}-journal"),
            path.with_name(f"{path.name}-wal"),
            path.with_name(f"{path.name}-shm"),
        )
        if candidate.exists()
    )


def test_valid_unknown_batch_roundtrips_through_incomplete_sqlite_snapshot(tmp_path):
    from archkeel.check.fact_batch_store import SnapshotStatus, SQLiteFactBatchStore
    from archkeel.ir.facts_codec import evidence_payload, record_payload

    store = SQLiteFactBatchStore(tmp_path / "facts.sqlite", max_frame_bytes=4096)
    transaction = store.begin(
        snapshot_id="snapshot-1",
        source_digest="a" * 64,
        contract_identity="contracts-v1",
    )
    transaction.append(_batch())

    assert transaction.finalize() is SnapshotStatus.INCOMPLETE
    assert store.snapshot_status("snapshot-1") is SnapshotStatus.INCOMPLETE

    batch = store.read_batch("snapshot-1", sequence=0)
    assert [record_payload(record) for record in batch.records] == [
        {
            "id": "FACT-1",
            "evidence_class": "UNKNOWN",
            "area": "source",
            "kind": "unresolved_import",
            "title": "Import target is unknown",
            "subjects": ["src/example.py"],
            "evidence_ids": ["EVIDENCE-1"],
            "rule_ids": [],
            "fact_ids": [],
            "provenance": ["collector"],
            "data": {"target": "optional_module"},
        }
    ]
    assert [evidence_payload(item) for item in batch.evidence] == [
        {
            "id": "EVIDENCE-1",
            "file": "src/example.py",
            "line": 1,
            "end_line": 1,
            "column": 0,
            "excerpt": "call()",
        }
    ]


def test_batch_store_rejects_frame_over_byte_budget(tmp_path):
    from archkeel.check.fact_batch_store import SQLiteFactBatchStore

    transaction = SQLiteFactBatchStore(tmp_path / "facts.sqlite", max_frame_bytes=256).begin(
        snapshot_id="snapshot-1",
        source_digest="a" * 64,
        contract_identity="contracts-v1",
    )
    with pytest.raises(ValueError, match="frame exceeds"):
        transaction.append(_batch(excerpt="x" * 512))
    transaction.abort()


def test_batch_store_rejects_global_id_collision_and_dangling_reference(tmp_path):
    from archkeel.check.fact_batch_store import SQLiteFactBatchStore
    from archkeel.ir.fact_batches import FactBatch
    from archkeel.ir.facts_codec import encode_fact_batch, parse_record

    store = SQLiteFactBatchStore(tmp_path / "facts.sqlite", max_frame_bytes=4096)
    invalid_payload = json.loads(_batch())
    invalid_payload["evidence"][0]["id"] = "FACT-1"
    invalid = json.dumps(invalid_payload).encode()
    transaction = store.begin(
        snapshot_id="snapshot-1",
        source_digest="a" * 64,
        contract_identity="contracts-v1",
    )
    with pytest.raises(ValueError, match="duplicate.*ID"):
        transaction.append(invalid)
    transaction.abort()

    missing_evidence = parse_record(
        {
            "id": "FACT-2",
            "evidence_class": "UNKNOWN",
            "area": "source",
            "kind": "unresolved_import",
            "title": "Import target is unknown",
            "subjects": ["src/example.py"],
            "evidence_ids": ["MISSING-EVIDENCE"],
            "rule_ids": [],
            "fact_ids": [],
            "provenance": ["collector"],
            "data": {},
        }
    )
    dangling = encode_fact_batch(FactBatch("snapshot-2", 0, (missing_evidence,), ()))
    transaction = store.begin(
        snapshot_id="snapshot-2",
        source_digest="b" * 64,
        contract_identity="contracts-v1",
    )
    transaction.append(dangling)
    with pytest.raises(ValueError, match="evidence reference"):
        transaction.finalize()
    transaction.abort()


def test_aborted_batch_does_not_replace_prior_snapshot(tmp_path):
    from archkeel.check.fact_batch_store import SnapshotStatus, SQLiteFactBatchStore

    store = SQLiteFactBatchStore(tmp_path / "facts.sqlite", max_frame_bytes=4096)
    first = store.begin(
        snapshot_id="snapshot-1",
        source_digest="a" * 64,
        contract_identity="contracts-v1",
    )
    first.append(_batch())
    assert first.finalize() is SnapshotStatus.INCOMPLETE

    second = store.begin(
        snapshot_id="snapshot-2",
        source_digest="b" * 64,
        contract_identity="contracts-v1",
    )
    second.append(_batch(snapshot_id="snapshot-2"))
    second.abort()

    assert store.snapshot_status("snapshot-1") is SnapshotStatus.INCOMPLETE
    assert store.snapshot_status("snapshot-2") is None
    assert len(store.read_batch("snapshot-1", sequence=0).records) == 1


def test_snapshot_frame_budget_rolls_back_without_replacing_previous_snapshot(tmp_path):
    from archkeel.check.fact_batch_store import SnapshotStatus, SQLiteFactBatchStore

    database_path = tmp_path / "facts.sqlite"
    store = SQLiteFactBatchStore(
        database_path,
        max_frame_bytes=16 * 1024,
        max_snapshot_frame_bytes=24 * 1024,
    )
    previous = store.begin(
        snapshot_id="snapshot-old",
        source_digest="b" * 64,
        contract_identity="contracts-v1",
    )
    previous.append(_batch(snapshot_id="snapshot-old"))
    previous.finalize()

    transaction = store.begin(
        snapshot_id="snapshot-1",
        source_digest="a" * 64,
        contract_identity="contracts-v1",
    )
    exceeded = False
    accepted_bytes = 0
    for sequence in range(64):
        try:
            frame = _batch(sequence, snapshot_id="snapshot-1", excerpt="x" * (8 * 1024))
            transaction.append(frame)
            accepted_bytes += len(frame)
            assert accepted_bytes <= store.max_snapshot_frame_bytes
        except ValueError as error:
            assert "snapshot frame budget exceeded" in str(error)
            exceeded = True
            break
    transaction.abort()
    assert exceeded
    assert store.snapshot_status("snapshot-old") is SnapshotStatus.INCOMPLETE
    assert len(store.read_batch("snapshot-old", sequence=0).records) == 1


def test_sqlite_page_limit_rolls_back_without_replacing_previous_snapshot(tmp_path):
    from archkeel.check.fact_batch_store import SnapshotStatus, SQLiteFactBatchStore

    database_path = tmp_path / "facts.sqlite"
    store = SQLiteFactBatchStore(
        database_path,
        max_frame_bytes=16 * 1024,
        max_database_bytes=128 * 1024,
        max_snapshot_frame_bytes=2 * 1024 * 1024,
    )
    previous = store.begin(
        snapshot_id="snapshot-old",
        source_digest="b" * 64,
        contract_identity="contracts-v1",
    )
    previous.append(_batch(snapshot_id="snapshot-old"))
    previous.finalize()

    transaction = store.begin(
        snapshot_id="snapshot-1",
        source_digest="a" * 64,
        contract_identity="contracts-v1",
    )
    exceeded = False
    for sequence in range(128):
        try:
            transaction.append(
                _batch(sequence, snapshot_id="snapshot-1", excerpt="x" * (8 * 1024))
            )
        except ValueError as error:
            assert "database size limit" in str(error)
            exceeded = True
            break
    assert exceeded
    assert database_path.stat().st_size <= store.max_database_bytes
    transaction.abort()
    assert store.snapshot_status("snapshot-old") is SnapshotStatus.INCOMPLETE
    assert len(store.read_batch("snapshot-old", sequence=0).records) == 1


def test_fact_batch_staging_modules_are_declared_in_architecture_contracts():
    from pathlib import Path

    root = Path(__file__).parents[1]
    root_contract = json.loads((root / "architecture-contract.json").read_text())
    ir_contract = json.loads((root / "docs/architecture/contracts/ir.json").read_text())
    check_contract = json.loads((root / "docs/architecture/contracts/check.json").read_text())

    root_ir = next(item for item in root_contract["components"] if item["label"] == "ir")
    root_check = next(item for item in root_contract["components"] if item["label"] == "check")
    ir_protocol = next(item for item in ir_contract["components"] if item["label"] == "protocol")
    ir_codec = next(item for item in ir_contract["components"] if item["label"] == "facts-codec")
    ir_facts = next(item for item in ir_contract["components"] if item["label"] == "facts")
    check_inputs = next(item for item in check_contract["components"] if item["label"] == "inputs")

    assert "archkeel.ir.fact_batches" in ir_protocol["packages"]
    assert "archkeel.ir.fact_batches:FactBatch" in ir_protocol["public"]
    assert "archkeel.ir.facts_codec:encode_fact_batch" in ir_codec["public"]
    assert "archkeel.ir.facts_codec:decode_fact_batch" in ir_codec["public"]
    assert "archkeel.ir.facts:SnapshotStatus" in ir_facts["public"]
    assert "archkeel.check.fact_batch_store" in check_inputs["packages"]
    assert "archkeel.check.fact_batch_store:SQLiteFactBatchStore" in check_inputs["public"]
    assert "archkeel.check.fact_batch_store:FactBatchTransaction" in check_inputs["public"]
    assert "archkeel.ir.fact_batches" in root_ir["public"]
    assert "archkeel.ir.fact_batches:FactBatch" in root_ir["public"]
    assert "archkeel.check.fact_batch_store:SQLiteFactBatchStore" in root_check["public"]
    assert "archkeel.check.fact_batch_store:FactBatchTransaction" in root_check["public"]
