# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read evidence metadata without interpreting rule semantics."""

from dataclasses import dataclass

from .core_json import CoreError, _count, _fields, _object, _text


@dataclass(frozen=True, slots=True)
class ViolationDetail:
    source: str
    target: str | None
    cause: str
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Location:
    path: str
    line: int


@dataclass(frozen=True, slots=True)
class CollectionGap:
    kind: str
    subjects: tuple[str, ...]
    reason: str
    evidence: tuple[str, ...]


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
        item = _fields(row, "collection gap", frozenset({"kind", "subjects", "reason", "evidence"}))
        gaps.append(
            CollectionGap(
                _text(item["kind"], "collection gap.kind"),
                _strings(item["subjects"], "collection gap.subjects"),
                _text(item["reason"], "collection gap.reason"),
                _strings(item["evidence"], "collection gap.evidence"),
            )
        )
    return tuple(gaps)
