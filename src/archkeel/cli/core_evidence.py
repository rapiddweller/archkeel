# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read evidence metadata without interpreting rule semantics."""

from dataclasses import dataclass

from .core_json import CoreError, as_count, as_object, as_text


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
    return tuple(as_text(item, where) for item in _list(value, where))


def read_details(value: object) -> dict[str, tuple[ViolationDetail, ...]]:
    """Read the violation rows of each rule."""
    result: dict[str, tuple[ViolationDetail, ...]] = {}
    for rule, rows in as_object(value, "details").items():
        details: list[ViolationDetail] = []
        for row in _list(rows, f"details.{rule}"):
            item = as_object(row, "detail")
            details.append(
                ViolationDetail(
                    as_text(item["source"], "detail.source"),
                    None if item["target"] is None else as_text(item["target"], "detail.target"),
                    as_text(item["cause"], "detail.cause"),
                    _strings(item["evidence"], "detail.evidence"),
                )
            )
        result[rule] = tuple(details)
    return result


def read_locations(value: object) -> dict[str, Location]:
    """Read the table of source locations by evidence key."""
    result: dict[str, Location] = {}
    for key, row in as_object(value, "locations").items():
        item = as_object(row, "location")
        result[key] = Location(
            as_text(item["path"], "location.path"), as_count(item["line"], "location.line")
        )
    return result


def read_collection_gaps(value: object) -> tuple[CollectionGap, ...]:
    """Read the gaps of the collector."""
    gaps: list[CollectionGap] = []
    for row in _list(value, "collection_gaps"):
        item = as_object(row, "collection gap")
        gaps.append(
            CollectionGap(
                as_text(item["kind"], "collection gap.kind"),
                _strings(item["subjects"], "collection gap.subjects"),
                as_text(item["reason"], "collection gap.reason"),
                _strings(item["evidence"], "collection gap.evidence"),
                as_text(item["detail"], "collection gap.detail") if "detail" in item else None,
            )
        )
    return tuple(gaps)
