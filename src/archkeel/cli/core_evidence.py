# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read evidence metadata without interpreting rule semantics."""

from dataclasses import dataclass

from .core_json import CoreError, _count, _fields, _object, _text


@dataclass(frozen=True, slots=True)
class ViolationDetail:
    """One violation of a rule: source, target, cause and the keys of its evidence."""

    source: str
    target: str | None
    cause: str
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Location:
    """A place in a source file: a path and a line."""

    path: str
    line: int


@dataclass(frozen=True, slots=True)
class CollectionGap:
    """A part of the code that the collector could not read, with its reason and evidence."""

    kind: str
    subjects: tuple[str, ...]
    reason: str
    evidence: tuple[str, ...]
    # The collector's free text beside the reason; no part of the gap key (AD-540).
    detail: str | None = None


def _list(value: object, where: str) -> list[object]:
    if not isinstance(value, list):
        raise CoreError(f"the core frame field {where} is not a list")
    return list(value)


def _strings(value: object, where: str) -> tuple[str, ...]:
    return tuple(_text(item, where) for item in _list(value, where))


def _details(value: object) -> dict[str, tuple[ViolationDetail, ...]]:
    result: dict[str, tuple[ViolationDetail, ...]] = {}
    for rule, rows in _object(value, "details").items():
        details: list[ViolationDetail] = []
        for row in _list(rows, f"details.{rule}"):
            item = _fields(row, "detail", frozenset({"source", "target", "cause", "evidence"}))
            details.append(
                ViolationDetail(
                    _text(item["source"], "detail.source"),
                    None if item["target"] is None else _text(item["target"], "detail.target"),
                    _text(item["cause"], "detail.cause"),
                    _strings(item["evidence"], "detail.evidence"),
                )
            )
        result[rule] = tuple(details)
    return result


def _locations(value: object) -> dict[str, Location]:
    result: dict[str, Location] = {}
    for key, row in _object(value, "locations").items():
        item = _fields(row, "location", frozenset({"path", "line"}))
        result[key] = Location(
            _text(item["path"], "location.path"), _count(item["line"], "location.line")
        )
    return result


def _collection_gaps(value: object) -> tuple[CollectionGap, ...]:
    gaps: list[CollectionGap] = []
    for row in _list(value, "collection_gaps"):
        names = frozenset({"kind", "subjects", "reason", "evidence"})
        item = _fields(
            row, "collection gap", names | _object(row, "collection gap").keys() & {"detail"}
        )
        gaps.append(
            CollectionGap(
                _text(item["kind"], "collection gap.kind"),
                _strings(item["subjects"], "collection gap.subjects"),
                _text(item["reason"], "collection gap.reason"),
                _strings(item["evidence"], "collection gap.evidence"),
                _text(item["detail"], "collection gap.detail") if "detail" in item else None,
            )
        )
    return tuple(gaps)
