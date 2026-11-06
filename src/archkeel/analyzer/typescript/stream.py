# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Experimental SQLite snapshot of canonical TypeScript symbols and explicit UNKNOWN gaps."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import tempfile
from enum import StrEnum
from pathlib import Path

from archkeel.ir.facts import Evidence, Record, ResolutionRole
from archkeel.ir.facts_codec import (
    RawEvidence,
    RawRecord,
    evidence_payload,
    parse_evidence,
    parse_record,
    record_payload,
)
from archkeel.ir.protocol import CollectionRequest, TypeScriptSettings

from .collect import _Collection, _GapKind

_VERSION = 2
_INCOMPLETE_REASON = (
    "Symbols use the canonical collector builder. Calls, references, import bindings, "
    "re-exports and full source validation are not part of this snapshot."
)
_MAX_PAGE_BYTES = 1_000_000
_PAGE_SECTIONS = {"symbols", "unknowns"}


class StreamSnapshotError(ValueError):
    """The experimental snapshot cannot be read or published."""


class StreamCoverage(StrEnum):
    INCOMPLETE = "INCOMPLETE"


class StreamContractEvaluation(StrEnum):
    NOT_EVALUATED = "NOT_EVALUATED"


def build_snapshot(request: CollectionRequest, output: Path) -> dict[str, object]:
    """Write canonical symbol records and evidence without building SourceFacts."""
    if not isinstance(request.resolver, TypeScriptSettings):
        raise StreamSnapshotError("TypeScript stream requires TypeScript settings")
    root = Path(request.snapshot.root).resolve()
    destination = output.resolve()
    if destination.is_relative_to(root):
        raise StreamSnapshotError("snapshot output must be outside the analyzed source root")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent, prefix=f".{destination.name}.", suffix=".building"
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(temporary)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE snapshot (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                schema_version INTEGER NOT NULL,
                snapshot_id TEXT NOT NULL UNIQUE,
                source_git_head TEXT NOT NULL,
                source_dirty TEXT NOT NULL,
                source_digest TEXT NOT NULL,
                namespace TEXT NOT NULL,
                roots_json TEXT NOT NULL,
                selected_files_json TEXT NOT NULL,
                selected_file_count INTEGER NOT NULL,
                coverage TEXT NOT NULL CHECK(coverage = 'INCOMPLETE'),
                coverage_reason TEXT NOT NULL,
                files_read INTEGER NOT NULL,
                files_parsed INTEGER NOT NULL,
                symbol_count INTEGER NOT NULL,
                unknown_count INTEGER NOT NULL,
                contract_identity TEXT NOT NULL
            );
            CREATE TABLE inputs (
                path TEXT PRIMARY KEY,
                digest TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('selected', 'resolution'))
            );
            CREATE TABLE evidence (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );
            CREATE TABLE identities (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL CHECK(kind IN ('file', 'symbol', 'unknown'))
            );
            CREATE TABLE records (
                section TEXT NOT NULL CHECK(section IN ('symbols', 'unknowns')),
                sequence INTEGER NOT NULL,
                id TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY(section, sequence),
                UNIQUE(section, id)
            );
            CREATE TABLE record_evidence (
                section TEXT NOT NULL,
                record_id TEXT NOT NULL,
                evidence_id TEXT NOT NULL REFERENCES evidence(id),
                ordinal INTEGER NOT NULL,
                PRIMARY KEY(section, record_id, evidence_id),
                FOREIGN KEY(section, record_id) REFERENCES records(section, id)
            );
            CREATE INDEX records_by_id ON records(section, id);
            """
        )
        connection.execute("BEGIN IMMEDIATE")
        collection = _Collection(request, request.resolver)
        if (
            collection.requested_bundler
            and not collection.bundler
            and collection.resolver.blocked is None
        ):
            collection._gap(
                "Bundler mode requires moduleResolution bundler", kind=_GapKind.RESOLUTION
            )
        collection._scan_files()
        collection._gap(_INCOMPLETE_REASON, kind=_GapKind.COLLECTION)
        for item in collection.imports:
            data = item["data"]
            if isinstance(data, dict):
                collection._gap(
                    "Import target symbol binding is not resolved by the streaming slice",
                    tuple(item["evidence_ids"]),
                    str(data.get("source_module", "")),
                    kind=_GapKind.RESOLUTION,
                )
        for problem in sorted(collection.snapshot.problems):
            collection._gap(problem)

        source_digest = _source_digest(collection.snapshot.inputs)
        selected_files = tuple(sorted(collection.queue))
        identity = _snapshot_identity(request, request.resolver, source_digest, selected_files)
        for path, (digest, role) in sorted(collection.snapshot.inputs.items()):
            connection.execute("INSERT INTO inputs VALUES (?, ?, ?)", (path, digest, role.value))
        for file in collection.files:
            connection.execute("INSERT INTO identities VALUES (?, 'file')", (file.id,))

        _write_evidence(connection, collection.evidence)
        collection.evidence.clear()
        definitions, ids, by_qualified, scope_ids = collection._inner_index()
        symbol_sequence = 0
        for raw_record in collection._inner_symbols(definitions, ids, by_qualified, scope_ids):
            _write_evidence(connection, collection.evidence)
            collection.evidence.clear()
            _write_record(connection, "symbols", symbol_sequence, raw_record)
            symbol_sequence += 1

        _write_evidence(connection, collection.evidence)
        unknown_count = 0
        for sequence, key in enumerate(sorted(collection.gaps)):
            _write_record(connection, "unknowns", sequence, collection.gaps[key])
            unknown_count += 1

        connection.execute(
            "INSERT INTO snapshot (singleton, schema_version, snapshot_id, source_git_head, "
            "source_dirty, source_digest, namespace, roots_json, selected_files_json, "
            "selected_file_count, coverage, coverage_reason, files_read, files_parsed, "
            "symbol_count, unknown_count, contract_identity) "
            "VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _VERSION,
                identity,
                request.snapshot.git_head,
                _dirty_text(request.snapshot.dirty),
                source_digest,
                request.scope.namespace,
                _json(list(request.scope.roots)),
                _json(list(selected_files)),
                len(selected_files),
                StreamCoverage.INCOMPLETE.value,
                _INCOMPLETE_REASON,
                collection.read,
                len(collection.files),
                symbol_sequence,
                unknown_count,
                StreamContractEvaluation.NOT_EVALUATED.value,
            ),
        )
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise StreamSnapshotError("SQLite snapshot has invalid evidence references")
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise StreamSnapshotError("SQLite snapshot failed its integrity check")
        connection.commit()
        connection.close()
        connection = None
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        return {
            "snapshot_id": identity,
            "coverage": StreamCoverage.INCOMPLETE,
            "coverage_reason": _INCOMPLETE_REASON,
            "source_revision": request.snapshot.git_head,
            "source_digest": source_digest,
            "contract_identity": StreamContractEvaluation.NOT_EVALUATED,
            "selected_file_count": len(selected_files),
            "files_read": collection.read,
            "files_parsed": len(collection.files),
            "symbol_count": symbol_sequence,
            "unknown_count": unknown_count,
            "output": str(destination),
        }
    except BaseException:
        if connection is not None:
            connection.rollback()
            connection.close()
        temporary.unlink(missing_ok=True)
        raise


def page(
    snapshot_path: Path,
    *,
    section: str,
    limit: int,
    cursor: str | None = None,
) -> dict[str, object]:
    """Read one bounded page of canonical records from an INCOMPLETE snapshot."""
    if section not in _PAGE_SECTIONS:
        raise StreamSnapshotError("section must be symbols or unknowns")
    if type(limit) is not int or not 1 <= limit <= 500:
        raise StreamSnapshotError("page limit must be between 1 and 500")
    snapshot_path = snapshot_path.resolve(strict=True)
    connection = sqlite3.connect(f"{snapshot_path.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        snapshot = connection.execute(
            "SELECT schema_version, selected_file_count, files_read, files_parsed, "
            "symbol_count, unknown_count, "
            "length(CAST(coverage AS BLOB)) AS coverage_bytes, "
            "CASE WHEN coverage = ? THEN 1 ELSE 0 END AS coverage_valid, "
            "length(CAST(snapshot_id AS BLOB)) AS snapshot_id_bytes, "
            "CASE WHEN length(snapshot_id) = 64 AND snapshot_id NOT GLOB '*[^0-9a-f]*' "
            "THEN 1 ELSE 0 END AS snapshot_id_valid, "
            "length(CAST(source_git_head AS BLOB)) AS source_git_head_bytes, "
            "CASE WHEN source_git_head = 'unknown' OR (length(source_git_head) IN (40, 64) "
            "AND source_git_head NOT GLOB '*[^0-9a-f]*') THEN 1 ELSE 0 END "
            "AS source_git_head_valid, "
            "length(CAST(source_dirty AS BLOB)) AS source_dirty_bytes, "
            "CASE WHEN source_dirty IN ('true', 'false', 'unknown') THEN 1 ELSE 0 END "
            "AS source_dirty_valid, "
            "length(CAST(source_digest AS BLOB)) AS source_digest_bytes, "
            "CASE WHEN length(source_digest) = 64 AND source_digest NOT GLOB '*[^0-9a-f]*' "
            "THEN 1 ELSE 0 END AS source_digest_valid, "
            "length(CAST(contract_identity AS BLOB)) AS contract_identity_bytes, "
            "CASE WHEN contract_identity = ? THEN 1 ELSE 0 END "
            "AS contract_identity_valid, "
            "length(CAST(namespace AS BLOB)) AS namespace_bytes, "
            "length(CAST(roots_json AS BLOB)) AS roots_bytes, "
            "length(CAST(coverage_reason AS BLOB)) AS reason_bytes "
            "FROM snapshot WHERE singleton = 1",
            (
                StreamCoverage.INCOMPLETE.value,
                StreamContractEvaluation.NOT_EVALUATED.value,
            ),
        ).fetchone()
        if snapshot is None or snapshot["schema_version"] != _VERSION:
            raise StreamSnapshotError("unsupported TypeScript stream snapshot version")
        if snapshot["coverage_valid"] != 1:
            raise StreamSnapshotError("snapshot is not an experimental incomplete result")
        if any(
            snapshot[field] != 1
            for field in (
                "snapshot_id_valid",
                "source_git_head_valid",
                "source_dirty_valid",
                "source_digest_valid",
                "contract_identity_valid",
            )
        ):
            raise StreamSnapshotError("snapshot metadata has an invalid identity field")
        metadata_budget = (
            snapshot["snapshot_id_bytes"]
            + snapshot["source_git_head_bytes"]
            + snapshot["source_dirty_bytes"]
            + snapshot["source_digest_bytes"]
            + snapshot["contract_identity_bytes"]
            + snapshot["coverage_bytes"]
            + snapshot["roots_bytes"]
            + snapshot["reason_bytes"]
            + snapshot["namespace_bytes"]
            + 1024
        )
        if metadata_budget > _MAX_PAGE_BYTES:
            raise StreamSnapshotError(
                f"snapshot metadata exceeds the {_MAX_PAGE_BYTES} byte page limit"
            )
        metadata_text = connection.execute(
            "SELECT snapshot_id, source_git_head, source_dirty, source_digest, namespace, "
            "contract_identity, coverage, roots_json, coverage_reason "
            "FROM snapshot WHERE singleton = 1"
        ).fetchone()
        after = -1
        if cursor is not None:
            token = _decode_cursor(cursor)
            cursor_after = token.get("after")
            if (
                token.get("snapshot_id") != metadata_text["snapshot_id"]
                or token.get("section") != section
                or token.get("limit") != limit
                or type(cursor_after) is not int
                or cursor_after < -1
                or cursor_after > (1 << 63) - 1
                or cursor_after
                >= (snapshot["symbol_count"] if section == "symbols" else snapshot["unknown_count"])
            ):
                raise StreamSnapshotError("invalid or stale cursor")
            after = cursor_after
        candidates = connection.execute(
            "SELECT r.sequence, r.id, length(CAST(r.payload AS BLOB)) AS record_bytes, "
            "COUNT(re.evidence_id) AS evidence_count, "
            "COALESCE(SUM(length(CAST(e.payload AS BLOB))), 0) AS evidence_bytes "
            "FROM records AS r LEFT JOIN record_evidence AS re "
            "ON re.section = r.section AND re.record_id = r.id "
            "LEFT JOIN evidence AS e ON e.id = re.evidence_id "
            "WHERE r.section = ? AND r.sequence > ? "
            "GROUP BY r.sequence, r.id ORDER BY r.sequence LIMIT ?",
            (section, after, limit + 1),
        ).fetchall()
        metadata = {
            "snapshot_id": metadata_text["snapshot_id"],
            "source_git_head": metadata_text["source_git_head"],
            "source_dirty": metadata_text["source_dirty"],
            "source_digest": metadata_text["source_digest"],
            "contract_identity": StreamContractEvaluation(metadata_text["contract_identity"]),
            "namespace": metadata_text["namespace"],
            "roots": json.loads(metadata_text["roots_json"]),
            "selected_file_count": snapshot["selected_file_count"],
            "files_read": snapshot["files_read"],
            "files_parsed": snapshot["files_parsed"],
            "symbol_count": snapshot["symbol_count"],
            "unknown_count": snapshot["unknown_count"],
            "coverage": StreamCoverage(metadata_text["coverage"]),
            "coverage_reason": metadata_text["coverage_reason"],
            "record_counts": {
                "symbols": snapshot["symbol_count"],
                "unknowns": snapshot["unknown_count"],
            },
        }
        selected_meta: list[tuple[sqlite3.Row, int]] = []
        page_budget = metadata_budget
        for candidate in candidates[:limit]:
            sequence = _sqlite_int(candidate["sequence"])
            record_budget = (
                candidate["record_bytes"]
                + candidate["evidence_bytes"]
                + candidate["evidence_count"] * 8
                + 512
            )
            if page_budget + record_budget > _MAX_PAGE_BYTES:
                if not selected_meta:
                    raise StreamSnapshotError(
                        f"one {section} record exceeds the {_MAX_PAGE_BYTES} byte page limit"
                    )
                break
            selected_meta.append((candidate, sequence))
            page_budget += record_budget
        selected: list[dict[str, object]] = []
        for candidate, sequence in selected_meta:
            record_row = connection.execute(
                "SELECT payload FROM records WHERE section = ? AND sequence = ?",
                (section, sequence),
            ).fetchone()
            record = json.loads(record_row["payload"])
            evidence = [
                json.loads(item["payload"])
                for item in connection.execute(
                    "SELECT e.payload FROM record_evidence AS re "
                    "JOIN evidence AS e ON e.id = re.evidence_id "
                    "WHERE re.section = ? AND re.record_id = ? ORDER BY re.ordinal",
                    (section, candidate["id"]),
                )
            ]
            selected.append(
                {
                    "sequence": sequence,
                    "record": record,
                    "evidence": evidence,
                }
            )
        has_more = len(candidates) > len(selected_meta) or len(candidates) == limit + 1
        response: dict[str, object] = {
            "snapshot": metadata,
            "section": section,
            "rows": selected,
            "next_cursor": (
                _encode_cursor(metadata_text["snapshot_id"], section, limit, selected_meta[-1][1])
                if has_more and selected_meta
                else None
            ),
        }
        if len(_json(response).encode("utf-8")) > _MAX_PAGE_BYTES:
            raise StreamSnapshotError(f"page exceeds the {_MAX_PAGE_BYTES} byte page limit")
        return response
    finally:
        connection.close()


def _write_record(
    connection: sqlite3.Connection, section: str, sequence: int, raw_record: RawRecord
) -> None:
    record: Record = parse_record(raw_record)
    payload = record_payload(record)
    kind = "symbol" if section == "symbols" else "unknown"
    try:
        connection.execute("INSERT INTO identities VALUES (?, ?)", (record.id, kind))
    except sqlite3.IntegrityError as error:
        raise StreamSnapshotError("global record identity collision") from error
    connection.execute(
        "INSERT INTO records VALUES (?, ?, ?, ?)",
        (section, sequence, record.id, _json(payload)),
    )
    for ordinal, evidence_id in enumerate(_ordered_evidence_ids(payload)):
        connection.execute(
            "INSERT INTO record_evidence VALUES (?, ?, ?, ?)",
            (section, record.id, evidence_id, ordinal),
        )


def _write_evidence(connection: sqlite3.Connection, raw_evidence: dict[str, RawEvidence]) -> None:
    for identity, raw in sorted(raw_evidence.items()):
        evidence: Evidence = parse_evidence(raw)
        if identity != evidence.id:
            raise StreamSnapshotError("evidence identity does not match its dictionary key")
        payload = _json(evidence_payload(evidence))
        connection.execute(
            "INSERT INTO evidence VALUES (?, ?) ON CONFLICT(id) DO NOTHING", (identity, payload)
        )
        existing = connection.execute(
            "SELECT payload FROM evidence WHERE id = ?", (identity,)
        ).fetchone()
        if existing is None or existing[0] != payload:
            raise StreamSnapshotError("evidence identity has conflicting payloads")


def _ordered_evidence_ids(value: object) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def visit(item: object) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key.endswith("evidence_id") and isinstance(child, str):
                    if child not in seen:
                        found.append(child)
                        seen.add(child)
                elif key.endswith("evidence_ids") and isinstance(child, list):
                    for identity in child:
                        if isinstance(identity, str) and identity not in seen:
                            found.append(identity)
                            seen.add(identity)
                else:
                    visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return found


def _source_digest(inputs: dict[str, tuple[str, ResolutionRole]]) -> str:
    listing = [
        {"path": path, "digest": digest, "role": role.value}
        for path, (digest, role) in sorted(inputs.items())
    ]
    return hashlib.sha256(_json(listing, ensure_ascii=False).encode("utf-8")).hexdigest()


def _snapshot_identity(
    request: CollectionRequest,
    settings: TypeScriptSettings,
    source_digest: str,
    selected_files: tuple[str, ...],
) -> str:
    identity = {
        "schema_version": _VERSION,
        "source_git_head": request.snapshot.git_head,
        "source_dirty": _dirty_text(request.snapshot.dirty),
        "source_digest": source_digest,
        "namespace": request.scope.namespace,
        "roots": list(request.scope.roots),
        "tsconfig": settings.tsconfig,
        "selected_files": list(selected_files),
    }
    return hashlib.sha256(_json(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _dirty_text(dirty: bool | str) -> str:
    return "unknown" if dirty == "unknown" else "true" if dirty else "false"


def _sqlite_int(value: object) -> int:
    if type(value) is not int:
        raise StreamSnapshotError("snapshot contains a non-integer sequence")
    return value


def _json(value: object, *, ensure_ascii: bool = False, sort_keys: bool = False) -> str:
    return json.dumps(value, ensure_ascii=ensure_ascii, sort_keys=sort_keys, separators=(",", ":"))


def _encode_cursor(snapshot_id: str, section: str, limit: int, after: int) -> str:
    token = _json(
        {"snapshot_id": snapshot_id, "section": section, "limit": limit, "after": after},
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(token).rstrip(b"=").decode("ascii")


def _decode_cursor(value: str) -> dict[str, object]:
    try:
        if not value or len(value) > 2048:
            raise ValueError
        payload = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        token = json.loads(payload)
    except (ValueError, json.JSONDecodeError) as error:
        raise StreamSnapshotError("invalid or stale cursor") from error
    if not isinstance(token, dict) or set(token) != {"snapshot_id", "section", "limit", "after"}:
        raise StreamSnapshotError("invalid or stale cursor")
    return token
