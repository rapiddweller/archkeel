# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Raw record helpers private to the bundled analyzer."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, TypeAlias, TypedDict

from archkeel.ir.model import EvidenceClass

ANALYZER_VERSION = "0.10.0"
# AD-2: record payloads are open JSON whose shape varies by record kind.
RecordData: TypeAlias = dict[str, Any]


class RawRecord(TypedDict):
    """Envelope produced by :func:`classified` for every scanner/report record."""

    id: str
    evidence_class: str
    area: str
    kind: str
    title: str
    subjects: list[str]
    evidence_ids: list[str]
    rule_ids: list[str]
    fact_ids: list[str]
    provenance: list[str]
    data: RecordData


class RawEvidence(TypedDict):
    """Evidence entry produced by ``add_evidence`` in :mod:`source`."""

    id: str
    file: str
    line: int
    end_line: int
    column: int
    excerpt: str


def stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:16]}"


def analyzer_code_digest() -> str:
    """Hash bundled analyzer source bytes with package-relative framing."""
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(root.glob("*.py")):
        relative = path.name.encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def classified(
    *,
    item_id: str,
    evidence_class: EvidenceClass,
    area: str,
    kind: str,
    title: str,
    subjects: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    rule_ids: list[str] | None = None,
    fact_ids: list[str] | None = None,
    provenance: list[str] | None = None,
    data: RecordData | None = None,
) -> RawRecord:
    return {
        "id": item_id,
        "evidence_class": evidence_class.value,
        "area": area,
        "kind": kind,
        "title": title,
        "subjects": sorted(value for value in (subjects or []) if value),
        "evidence_ids": sorted(evidence_ids or []),
        "rule_ids": sorted(rule_ids or []),
        "fact_ids": sorted(fact_ids or []),
        "provenance": sorted(provenance or []),
        "data": data or {},
    }
