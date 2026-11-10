# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Send a collector reply through the Rust store (AD-346, opt-in: `ARCHKEEL_NATIVE_STORE`).

The collector process runs as before. Only the decode of `ProcessCollector` differs: the reply
bytes go to one `archkeel-store` process, which validates them once and answers with the
read-set document. The
process stays open for the collection: it gives the receipt digests and writes
`architecture.json` (`ir.store_seam`). A frame is one tag byte, the payload length as 8 bytes
big-endian, and the payload.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import IO

from archkeel.analyzer.memory_limit import limit_memory
from archkeel.analyzer.reply_checks import check_reply
from archkeel.ir.facts import SourceFacts
from archkeel.ir.facts_codec import ProtocolError
from archkeel.ir.protocol import CollectionRequest, CollectionResponse, ProtocolVersion
from archkeel.ir.readset_codec import decode_read_set
from archkeel.ir.store_seam import StoreEntry, close_store, open_store

# The factor of `facts_codec.decode_response`: a reply may inflate to 16 times its bytes.
_INFLATE_FACTOR = 16


class _StoreError(Exception):
    """The store refused a frame or ended."""


# A frame body is read in pieces of this size into one buffer, so it is held once (AD-346).
_PIECE = 1 << 20


def _read(stream: IO[bytes], size: int) -> bytearray:
    data = bytearray(size)
    position = 0
    while position < size:
        piece = stream.read(min(_PIECE, size - position))
        if not piece:
            raise _StoreError("the store process ended")
        data[position : position + len(piece)] = piece
        position += len(piece)
    return data


class StoreSession:
    """One `archkeel-store` process that holds one reply (`ir.store_seam.StoreSeam`)."""

    def __init__(self, binary: str, inflate_limit: int, memory_limit: int) -> None:
        self._process: subprocess.Popen[bytes] | None = subprocess.Popen(
            [binary, "--inflate-limit", str(inflate_limit)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._records: frozenset[str] = frozenset()
        self._evidence: frozenset[str] = frozenset()
        if refused := limit_memory(self._process.pid, memory_limit):
            self.close()
            raise _StoreError(refused)

    def ingest(self, reply: bytes) -> CollectionResponse:
        response = decode_read_set(self._ask(b"R", reply))
        facts: SourceFacts = response.facts
        records = [record for section in facts.sections for record in section.records]
        self._records = frozenset(record.id for record in (*records, *facts.coverage.gaps))
        self._evidence = frozenset(entry.id for entry in facts.evidence)
        return response

    def _ask(self, tag: bytes, payload: bytes) -> bytearray:
        process = self._process
        if process is None or process.stdin is None or process.stdout is None:
            raise _StoreError("the store process is not running")
        try:
            process.stdin.write(tag + len(payload).to_bytes(8, "big") + payload)
            process.stdin.flush()
        except BrokenPipeError as error:
            raise _StoreError("the store process ended") from error
        answer = _read(process.stdout, 9)
        body = _read(process.stdout, int.from_bytes(answer[1:], "big"))
        if answer[:1] != b"O":
            raise _StoreError(body.decode("utf-8", errors="replace"))
        return body

    def holds_record(self, identifier: str) -> bool:
        return identifier in self._records

    def holds_evidence(self, identifier: str) -> bool:
        return identifier in self._evidence

    def bind(self, records: Sequence[StoreEntry], evidence: Sequence[StoreEntry]) -> str:
        request = {"records": list(records), "evidence": list(evidence)}
        return self._ask(b"B", json.dumps(request, ensure_ascii=False).encode()).decode()

    def digest(self, value: Mapping[str, object]) -> str:
        return self._ask(b"D", json.dumps(value, ensure_ascii=False).encode()).decode()

    def write(self, model: Mapping[str, object]) -> bytes:
        payload = json.dumps(
            model, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode()
        return bytes(self._ask(b"W", payload))

    def close(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        if process.stdin is not None:
            process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        if process.stdout is not None:
            process.stdout.close()


@dataclass(frozen=True, slots=True)
class StoreLimits:
    """The store binary and the limits of the collector that it inherits."""

    binary: str
    output_limit_bytes: int
    memory_limit_bytes: int


def store_response(
    reply: bytes,
    request: CollectionRequest,
    limits: StoreLimits,
    *,
    protocol_version: ProtocolVersion | None,
    adapter_version: str | None,
) -> CollectionResponse:
    """Open a store session for `reply` and return its read-set facts (`ProcessCollector`)."""
    try:
        inflate = max(len(reply), limits.output_limit_bytes) * _INFLATE_FACTOR
        close_store()  # One store process at a time: the previous one ends before this one starts.
        session = StoreSession(limits.binary, inflate, limits.memory_limit_bytes)
        opened = False
        try:
            response = session.ingest(reply)
            open_store(session, response.facts)
            opened = True
        finally:
            if not opened:
                session.close()
    except (_StoreError, OSError, ValueError) as error:
        raise ProtocolError(str(error)) from error
    check_reply(
        response,
        request,
        protocol_version=protocol_version,
        adapter_version=adapter_version,
    )
    return response
