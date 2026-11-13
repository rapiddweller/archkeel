# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A collector process that replays another collector and damages its reply (AD-340).

Usage: `replay_collector.py INNER MODE [SECTION]`. `INNER` is `python` (the unmodified Python
collector) or the path of the native collector. `MODE` is `plain` (no change), `drop` (remove the
records section `SECTION` and keep the capability that declares it), `claim` (declare a section
that the reply does not hold), `empty` (keep the section and remove its records) or `version` (give
the reply a protocol version that the request did not ask for). The host must fail closed on every
damaged reply.
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
from pathlib import Path

from archkeel.ir.facts import FactSection, SourceSectionName
from archkeel.ir.facts_codec import decode_request, decode_response, encode_response
from archkeel.ir.protocol import CollectionResponse, ProtocolVersion


def _reply(inner: str, payload: bytes) -> bytes:
    request = decode_request(payload)
    if inner.startswith("recorded-file:"):
        facts = decode_response(Path(inner.removeprefix("recorded-file:")).read_bytes()).facts
        facts = dataclasses.replace(
            facts,
            source=dataclasses.replace(
                facts.source, git_head=request.snapshot.git_head, dirty=request.snapshot.dirty
            ),
        )
        return encode_response(CollectionResponse(facts, request.protocol_version))
    return subprocess.run([inner], input=payload, capture_output=True, check=True).stdout


def main() -> int:
    inner, mode = sys.argv[1], sys.argv[2]
    section = SourceSectionName(sys.argv[3]) if len(sys.argv) > 3 else None
    payload = sys.stdin.buffer.read()
    reply = _reply(inner, payload)
    if mode == "plain":
        sys.stdout.buffer.write(reply)
        return 0
    response = decode_response(reply)
    facts = response.facts
    sections = facts.sections
    capabilities = facts.capabilities
    if mode == "drop":
        sections = tuple(item for item in sections if item.name is not section)
    elif mode == "empty":
        sections = tuple(
            FactSection(item.name, ()) if item.name is section else item for item in sections
        )
    elif mode == "claim":
        capabilities = dataclasses.replace(
            capabilities,
            sections=(*capabilities.sections, section),  # type: ignore[arg-type]
        )
    version = response.protocol_version
    if mode == "version":
        version = ProtocolVersion.V9 if version is ProtocolVersion.V8 else ProtocolVersion.V8
    damaged = dataclasses.replace(facts, sections=sections, capabilities=capabilities)
    sys.stdout.buffer.write(encode_response(CollectionResponse(damaged, version)))
    return 0


raise SystemExit(main())
