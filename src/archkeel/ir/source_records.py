# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Mutable record builders used before freezing the source protocol values."""

from collections.abc import Sequence
from typing import Any, TypeAlias, TypedDict

from .facts import EvidenceClass, stable_id

# Mutable JSON builders remain private to collection/evaluation, never the process port.
RawData: TypeAlias = dict[str, Any]


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
    data: RawData


class RawEvidence(TypedDict):
    """Evidence entry produced by ``add_evidence`` in :mod:`source`."""

    id: str
    file: str
    line: int
    end_line: int
    column: int
    excerpt: str


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
    data: RawData | None = None,
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


def record_evidence(
    evidence: dict[str, RawEvidence],
    rel_path: str,
    position: tuple[int, int, int],
    excerpt: str,
) -> str:
    """File one source location as evidence; shared by every profile's reader (AD-97)."""
    line, end_line, column = position
    # One source location is one evidence owner even when several observations
    # (for example a call and a dynamic-typing signal) refer to it.
    evidence_id = stable_id("EVD", rel_path, line, end_line, column)
    evidence[evidence_id] = {
        "id": evidence_id,
        "file": rel_path,
        "line": line,
        "end_line": end_line,
        "column": column,
        "excerpt": excerpt,
    }
    return evidence_id


def file_evidence(evidence: dict[str, RawEvidence], rel_path: str, lines: Sequence[str]) -> str:
    """Cite the file a module is: the fact root layout, assignment and placement judge (AD-107).

    Line 1 shows the file when it holds text. An empty file, or one whose first line is blank,
    has no line to show, so line 0 cites the file itself: an empty `__init__.py` still makes its
    package exist, and its package's violation must stay traceable.
    """
    line: str = lines[0] if lines else ""
    first = line.rstrip()
    return record_evidence(evidence, rel_path, (1, 1, 0) if first else (0, 0, 0), first)
