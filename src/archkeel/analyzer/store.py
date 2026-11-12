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
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import IO

from archkeel.analyzer.memory_limit import limit_memory
from archkeel.analyzer.reply_checks import check_reply
from archkeel.ir.facts import SourceFacts
from archkeel.ir.facts_codec import ProtocolError
from archkeel.ir.protocol import CollectionRequest, CollectionResponse, ProtocolVersion
from archkeel.ir.readset_codec import decode_read_set
from archkeel.ir.state_facts import VerifiedBinary
from archkeel.ir.store_seam import StoreEntry, close_store, open_store
from archkeel.ir.validated_facts import accept_store_facts

# The factor of `facts_codec.decode_response`: a reply may inflate to 16 times its bytes.
_INFLATE_FACTOR = 16
# The longest answer: the frame limit of the store (`session.rs:FRAME_LIMIT`).
_ANSWER_LIMIT = 1 << 40


class _StoreError(Exception):
    """The store refused a frame or ended."""


def _read(stream: IO[bytes], size: int) -> bytes:
    """One frame body: a buffered read of `size` fills one bytes object, so it is held once."""
    if size > _ANSWER_LIMIT:
        raise _StoreError("the store answer is too long")
    data = stream.read(size)
    if len(data) != size:
        raise _StoreError("the store process ended")
    return data


# The rows of a long list are encoded in slices of this many items (AD-346).
_SLICE = 10_000
# A JSON value of the frame.
_Json = Mapping[str, object] | list[object] | str | float | None


def _json(value: _Json) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def _pieces(value: Mapping[str, object]) -> Iterator[bytes]:
    """The compact JSON of `value` in pieces: an object by its entries, a long list by slices.

    The bytes equal one `json.dumps` call, and no piece holds a whole section.
    """
    yield b"{"
    for index, (key, item) in enumerate(value.items()):
        if not isinstance(key, str):
            raise TypeError(f"the frame holds a key that is not a text: {key}")
        yield (b"," if index else b"") + _json(key) + b":"
        if isinstance(item, Mapping):
            yield from _pieces(item)
        elif isinstance(item, list) and len(item) > _SLICE:
            yield b"["
            for start in range(0, len(item), _SLICE):
                yield (b"," if start else b"") + _json(item[start : start + _SLICE])[1:-1]
            yield b"]"
        elif isinstance(item, str | int | float | list) or item is None:
            yield _json(item)
        else:
            raise TypeError(f"the frame holds a value that is not JSON: {key}")
    yield b"}"


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

    def ingest(
        self, reply: bytes, verified_binary: VerifiedBinary | None = None
    ) -> CollectionResponse:
        response = decode_read_set(self._ask(b"R", reply))
        if verified_binary is not None:
            response = replace(
                response, facts=replace(response.facts, verified_binary=verified_binary)
            )
            accept_store_facts(response.facts)
        facts: SourceFacts = response.facts
        records = [record for section in facts.sections for record in section.records]
        self._records = frozenset(record.id for record in (*records, *facts.coverage.gaps))
        self._evidence = frozenset(entry.id for entry in facts.evidence)
        return response

    def _ask(self, tag: bytes, payload: bytes) -> bytes:
        return self._ask_pieces(tag, len(payload), (payload,))

    def _ask_pieces(self, tag: bytes, size: int, pieces: Iterable[bytes]) -> bytes:
        """Send one frame from its pieces; the payload is never joined into one copy."""
        process = self._process
        if process is None or process.stdin is None or process.stdout is None:
            raise _StoreError("the store process is not running")
        try:
            process.stdin.write(tag + size.to_bytes(8, "big"))
            for piece in pieces:
                process.stdin.write(piece)
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
        # The frame goes in pieces, written twice: once to count its length, once to send.
        size = sum(len(piece) for piece in _pieces(model))
        return self._ask_pieces(b"W", size, _pieces(model))

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
    verified_binary: VerifiedBinary | None = None,
) -> CollectionResponse:
    """Open a store session for `reply` and return its read-set facts (`ProcessCollector`)."""
    try:
        inflate = max(len(reply), limits.output_limit_bytes) * _INFLATE_FACTOR
        close_store()  # One store process at a time: the previous one ends before this one starts.
        session = StoreSession(limits.binary, inflate, limits.memory_limit_bytes)
        opened = False
        try:
            response = session.ingest(reply, verified_binary)
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
