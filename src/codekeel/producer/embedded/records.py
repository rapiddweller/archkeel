# Codekeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Raw record helpers private to the bundled analyzer."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from codekeel.ir.model import EvidenceClass

SCHEMA_VERSION = "1.2.0"
ANALYZER_VERSION = "0.3.0"


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
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
