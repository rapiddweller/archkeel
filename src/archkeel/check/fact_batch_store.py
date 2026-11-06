# ArchKeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Private SQLite staging for bounded canonical source-fact batches."""

from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path
from typing import Final

from archkeel.ir.fact_batches import MAX_FACT_BATCH_FRAME_BYTES, FactBatch
from archkeel.ir.facts import SnapshotStatus
from archkeel.ir.facts_codec import (
    DEFAULT_RESPONSE_LIMIT_BYTES,
    decode_fact_batch,
)

DEFAULT_MAX_FRAME_BYTES: Final = MAX_FACT_BATCH_FRAME_BYTES
DEFAULT_MAX_DATABASE_BYTES: Final = 4 * DEFAULT_RESPONSE_LIMIT_BYTES
DEFAULT_MAX_SNAPSHOT_FRAME_BYTES: Final = 4 * DEFAULT_RESPONSE_LIMIT_BYTES
_DATABASE_APPLICATION_ID: Final = 0x414B5354
_DATABASE_VERSION: Final = 1


def _primary_error_code(error: sqlite3.Error) -> int | None:
    code = error.sqlite_errorcode
    return None if code is None else code & 0xFF


class _DatabaseSizeExceeded(Exception):
    pass


class SQLiteFactBatchStore:
    """Store untrusted batches separately until full SourceFacts validation exists."""

    def __init__(
        self,
        path: Path,
        *,
        max_frame_bytes: int = DEFAULT_MAX_FRAME_BYTES,
        max_database_bytes: int = DEFAULT_MAX_DATABASE_BYTES,
        max_snapshot_frame_bytes: int = DEFAULT_MAX_SNAPSHOT_FRAME_BYTES,
    ) -> None:
        if not isinstance(max_frame_bytes, int) or isinstance(max_frame_bytes, bool):
            raise ValueError("max_frame_bytes must be a positive integer")
        if max_frame_bytes <= 0:
            raise ValueError("max_frame_bytes must be a positive integer")
        if not isinstance(max_database_bytes, int) or isinstance(max_database_bytes, bool):
            raise ValueError("max_database_bytes must be a positive integer")
        if max_database_bytes < 64 * 1024:
            raise ValueError("max_database_bytes must be at least 65536")
        if max_database_bytes > (1 << 63) - 1:
            raise ValueError("max_database_bytes is outside the supported range")
        if (
            not isinstance(max_snapshot_frame_bytes, int)
            or isinstance(max_snapshot_frame_bytes, bool)
            or max_snapshot_frame_bytes <= 0
        ):
            raise ValueError("max_snapshot_frame_bytes must be a positive integer")
        if max_snapshot_frame_bytes > (1 << 63) - 1:
            raise ValueError("max_snapshot_frame_bytes is outside the supported range")
        self.path = Path(os.path.abspath(path))
        self.max_frame_bytes = max_frame_bytes
        self.max_database_bytes = max_database_bytes
        self.max_snapshot_frame_bytes = max_snapshot_frame_bytes
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._create_private_file()
        self._initialize()

    def _create_private_file(self) -> None:
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as error:
            file_mode = self.path.lstat().st_mode
            if not stat.S_ISREG(file_mode):
                raise ValueError("fact batch database path must be a regular file") from error
            if stat.S_IMODE(file_mode) & 0o077:
                raise ValueError(
                    "fact batch database file must not be group or world accessible"
                ) from error
            return
        os.close(descriptor)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute("PRAGMA journal_size_limit = 0")
        try:
            self._apply_page_limit(connection)
        except (sqlite3.Error, ValueError):
            connection.close()
            raise
        return connection

    def _max_page_count(self, page_size: int) -> int:
        # SQLite enforces this on the database file. It does not cap live journals.
        pages = self.max_database_bytes // page_size
        if pages < 1:
            raise ValueError("max_database_bytes is too small for a SQLite transaction")
        return pages

    def _apply_page_limit(self, connection: sqlite3.Connection) -> None:
        config = connection.execute(
            "SELECT max_database_bytes FROM store_config WHERE singleton = 1"
        ).fetchone()
        if config is None or config["max_database_bytes"] != self.max_database_bytes:
            raise ValueError("fact batch database size limit does not match stored configuration")
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        max_pages = self._max_page_count(page_size)
        accepted = int(connection.execute(f"PRAGMA max_page_count = {max_pages}").fetchone()[0])
        current_pages = int(connection.execute("PRAGMA page_count").fetchone()[0])
        if accepted > max_pages or current_pages > max_pages:
            raise ValueError("fact batch database exceeds configured size limit")

    def _initialize(self) -> None:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute("PRAGMA journal_size_limit = 0")
        try:
            application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if application_id == 0 and version == 0:
                tables = connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                if tables:
                    raise ValueError("database is not an empty fact batch store")
                journal_mode = connection.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
                if journal_mode.lower() != "delete":
                    raise ValueError("fact batch store requires SQLite delete journaling")
                page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
                max_pages = self._max_page_count(page_size)
                connection.execute(f"PRAGMA max_page_count = {max_pages}")
                connection.executescript(
                    f"""
                    BEGIN IMMEDIATE;
                    CREATE TABLE store_config (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        max_database_bytes INTEGER NOT NULL
                    );
                    INSERT INTO store_config (singleton, max_database_bytes)
                        VALUES (1, {self.max_database_bytes});
                    CREATE TABLE snapshots (
                        snapshot_id TEXT PRIMARY KEY,
                        source_digest TEXT NOT NULL,
                        contract_identity TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('BUILDING', 'INCOMPLETE'))
                    );
                    CREATE TABLE batches (
                        snapshot_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL CHECK (sequence >= 0),
                        frame BLOB NOT NULL,
                        PRIMARY KEY (snapshot_id, sequence),
                        FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id)
                    );
                    CREATE TABLE identities (
                        snapshot_id TEXT NOT NULL,
                        record_id TEXT NOT NULL,
                        PRIMARY KEY (snapshot_id, record_id),
                        FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id)
                    );
                    CREATE TABLE records (
                        snapshot_id TEXT NOT NULL,
                        record_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        ordinal INTEGER NOT NULL,
                        PRIMARY KEY (snapshot_id, record_id),
                        UNIQUE (snapshot_id, sequence, ordinal),
                        FOREIGN KEY (snapshot_id, record_id)
                            REFERENCES identities(snapshot_id, record_id)
                    );
                    CREATE TABLE evidence (
                        snapshot_id TEXT NOT NULL,
                        evidence_id TEXT NOT NULL,
                        PRIMARY KEY (snapshot_id, evidence_id),
                        FOREIGN KEY (snapshot_id, evidence_id)
                            REFERENCES identities(snapshot_id, record_id)
                    );
                    CREATE TABLE record_evidence (
                        snapshot_id TEXT NOT NULL,
                        record_id TEXT NOT NULL,
                        evidence_id TEXT NOT NULL,
                        PRIMARY KEY (snapshot_id, record_id, evidence_id),
                        FOREIGN KEY (snapshot_id, record_id)
                            REFERENCES records(snapshot_id, record_id)
                    );
                    PRAGMA application_id = {_DATABASE_APPLICATION_ID};
                    PRAGMA user_version = {_DATABASE_VERSION};
                    COMMIT;
                    """
                )
                connection.commit()
            elif application_id != _DATABASE_APPLICATION_ID or version != _DATABASE_VERSION:
                raise ValueError("unsupported fact batch database identity or version")
            elif connection.execute("PRAGMA journal_mode").fetchone()[0].lower() != "delete":
                raise ValueError("fact batch store requires SQLite delete journaling")
            self._apply_page_limit(connection)
            if self.path.stat().st_size > self.max_database_bytes:
                raise ValueError("fact batch database exceeds configured size limit")
        except sqlite3.Error:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def _database_artifact_bytes(self) -> int:
        size = 0
        for suffix in ("", "-journal", "-wal", "-shm"):
            path = Path(f"{self.path}{suffix}")
            try:
                file_mode = path.lstat().st_mode
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(file_mode):
                raise ValueError("fact batch database sidecars must be regular files")
            size += path.lstat().st_size
        return size

    def begin(
        self, *, snapshot_id: str, source_digest: str, contract_identity: str
    ) -> FactBatchTransaction:
        for label, value in (
            ("snapshot_id", snapshot_id),
            ("source_digest", source_digest),
            ("contract_identity", contract_identity),
        ):
            if not isinstance(value, str) or not value or "\x00" in value:
                raise ValueError(f"{label} must be a nonempty string")
        if len(source_digest) != 64 or any(
            char not in "0123456789abcdef" for char in source_digest
        ):
            raise ValueError("source_digest must be a lowercase SHA-256 digest")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO snapshots (snapshot_id, source_digest, contract_identity, status) "
                "VALUES (?, ?, ?, 'BUILDING')",
                (snapshot_id, source_digest, contract_identity),
            )
        except sqlite3.IntegrityError as error:
            connection.rollback()
            connection.close()
            raise ValueError("snapshot identity already exists") from error
        except sqlite3.Error as error:
            connection.rollback()
            connection.close()
            if _primary_error_code(error) == sqlite3.SQLITE_FULL:
                raise ValueError("fact batch database size limit exceeded; transaction rolled back") from error
            if _primary_error_code(error) == sqlite3.SQLITE_IOERR:
                raise ValueError("fact batch database write failed; transaction rolled back") from error
            raise
        return FactBatchTransaction(self, connection, snapshot_id)

    def snapshot_status(self, snapshot_id: str) -> SnapshotStatus | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT status FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)
            ).fetchone()
            if row is None or row["status"] != SnapshotStatus.INCOMPLETE.value:
                return None
            return SnapshotStatus.INCOMPLETE
        finally:
            connection.close()

    def read_batch(self, snapshot_id: str, *, sequence: int) -> FactBatch:
        if (
            not isinstance(sequence, int)
            or isinstance(sequence, bool)
            or not 0 <= sequence <= (1 << 63) - 1
        ):
            raise ValueError("sequence is outside the supported range")
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            where = (
                "FROM batches AS b JOIN snapshots AS s USING (snapshot_id) "
                "WHERE b.snapshot_id = ? AND b.sequence = ? AND s.status = 'INCOMPLETE'"
            )
            row = connection.execute(
                "SELECT length(b.frame) AS frame_bytes " + where, (snapshot_id, sequence)
            ).fetchone()
            if row is None:
                raise KeyError("incomplete snapshot batch not found")
            if row["frame_bytes"] > self.max_frame_bytes:
                raise ValueError("stored fact batch frame exceeds byte limit")
            row = connection.execute("SELECT b.frame " + where, (snapshot_id, sequence)).fetchone()
            if row is None:
                raise KeyError("incomplete snapshot batch not found")
            frame = bytes(row["frame"])
            batch = decode_fact_batch(frame, max_bytes=self.max_frame_bytes)
            if batch.snapshot_id != snapshot_id or batch.sequence != sequence:
                raise ValueError("stored fact batch identity mismatch")
            return batch
        finally:
            connection.close()


class FactBatchTransaction:
    def __init__(
        self, store: SQLiteFactBatchStore, connection: sqlite3.Connection, snapshot_id: str
    ) -> None:
        self._store = store
        self._connection = connection
        self._snapshot_id = snapshot_id
        self._next_sequence = 0
        self._accepted_frame_bytes = 0
        self._closed = False

    def append(self, frame: bytes) -> None:
        self._ensure_open()
        if len(frame) > self._store.max_frame_bytes:
            raise ValueError("fact batch frame exceeds byte limit")
        if self._accepted_frame_bytes + len(frame) > self._store.max_snapshot_frame_bytes:
            self._rollback_and_close()
            raise ValueError("snapshot frame budget exceeded")
        batch = decode_fact_batch(frame, max_bytes=self._store.max_frame_bytes)
        if batch.snapshot_id != self._snapshot_id:
            raise ValueError("fact batch snapshot identity mismatch")
        if batch.sequence != self._next_sequence:
            raise ValueError("fact batch sequence is not contiguous")
        connection = self._connection
        try:
            connection.execute(
                "INSERT INTO batches (snapshot_id, sequence, frame) VALUES (?, ?, ?)",
                (self._snapshot_id, batch.sequence, frame),
            )
            for record in batch.records:
                connection.execute(
                    "INSERT INTO identities (snapshot_id, record_id) VALUES (?, ?)",
                    (self._snapshot_id, record.id),
                )
            for evidence in batch.evidence:
                connection.execute(
                    "INSERT INTO identities (snapshot_id, record_id) VALUES (?, ?)",
                    (self._snapshot_id, evidence.id),
                )
            for ordinal, record in enumerate(batch.records):
                connection.execute(
                    "INSERT INTO records (snapshot_id, record_id, sequence, ordinal) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        self._snapshot_id,
                        record.id,
                        batch.sequence,
                        ordinal,
                    ),
                )
                connection.executemany(
                    "INSERT INTO record_evidence (snapshot_id, record_id, evidence_id) "
                    "VALUES (?, ?, ?)",
                    (
                        (self._snapshot_id, record.id, evidence_id)
                        for evidence_id in record.evidence_ids
                    ),
                )
            for evidence in batch.evidence:
                connection.execute(
                    "INSERT INTO evidence (snapshot_id, evidence_id) VALUES (?, ?)",
                    (self._snapshot_id, evidence.id),
                )
            if self._store._database_artifact_bytes() > self._store.max_database_bytes:
                raise _DatabaseSizeExceeded
        except _DatabaseSizeExceeded as error:
            self._rollback_and_close()
            raise ValueError("fact batch database size limit exceeded") from error
        except sqlite3.IntegrityError as error:
            self._rollback_and_close()
            raise ValueError(f"duplicate global ID or invalid batch reference: {error}") from error
        except sqlite3.Error as error:
            self._rollback_and_close()
            if _primary_error_code(error) == sqlite3.SQLITE_FULL:
                raise ValueError("fact batch database size limit exceeded; snapshot rolled back") from error
            if _primary_error_code(error) == sqlite3.SQLITE_IOERR:
                raise ValueError("fact batch database write failed; snapshot rolled back") from error
            raise
        except ValueError:
            self._rollback_and_close()
            raise
        else:
            self._next_sequence += 1
            self._accepted_frame_bytes += len(frame)

    def finalize(self) -> SnapshotStatus:
        self._ensure_open()
        missing = self._connection.execute(
            "SELECT r.record_id, r.evidence_id FROM record_evidence AS r "
            "LEFT JOIN evidence AS e USING (snapshot_id, evidence_id) "
            "WHERE r.snapshot_id = ? AND e.evidence_id IS NULL LIMIT 1",
            (self._snapshot_id,),
        ).fetchone()
        if missing is not None:
            raise ValueError(
                f"evidence reference {missing['evidence_id']} from "
                f"{missing['record_id']} is missing"
            )
        self._connection.execute(
            "UPDATE snapshots SET status = 'INCOMPLETE' WHERE snapshot_id = ?",
            (self._snapshot_id,),
        )
        if self._store._database_artifact_bytes() > self._store.max_database_bytes:
            self._rollback_and_close()
            raise ValueError("fact batch database size limit exceeded")
        try:
            self._connection.commit()
        except sqlite3.Error as error:
            self._rollback_and_close()
            if _primary_error_code(error) == sqlite3.SQLITE_FULL:
                raise ValueError("fact batch database size limit exceeded; snapshot rolled back") from error
            if _primary_error_code(error) == sqlite3.SQLITE_IOERR:
                raise ValueError("fact batch database write failed; snapshot rolled back") from error
            raise
        self._close()
        return SnapshotStatus.INCOMPLETE

    def abort(self) -> None:
        if self._closed:
            return
        self._ensure_open()
        self._rollback_and_close()

    def _rollback_and_close(self) -> None:
        if self._closed:
            return
        try:
            self._connection.rollback()
        finally:
            self._close()

    def _close(self) -> None:
        self._connection.close()
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("fact batch transaction is closed")
