# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Name the reference and call records that the dependency proof binds (AD-237)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Protocol

from .facts_codec import parse_record
from .model import Section
from .source_records import RawRecord

_SOURCE_OWNERSHIP_REFERENCE_KINDS = frozenset(
    {"source_role", "value_reference", "attribute_reference"}
)


def binds_reference(kind: str, *, include_calls: bool, include_source_ownership: bool) -> bool:
    """Return whether the proof binds a reference record of this kind."""
    return (
        kind == "script_namespace_effect"
        or include_calls
        or include_source_ownership
        and kind in _SOURCE_OWNERSHIP_REFERENCE_KINDS
    )


def _bound_raw_records(
    section: str,
    records: Iterable[RawRecord],
    *,
    include_calls: bool,
    include_source_ownership: bool,
) -> Iterable[RawRecord]:
    """Return the raw records of a section that the proof binds, before any parse.

    The test is the one of `dependency_binding_id`. A record without a text kind stays in the
    result, so `parse_record` rejects it as it did before. A malformed record of an unbound kind
    is dropped here and `parse_observation` rejects it later in the same run.
    """
    if section == "calls":
        return records if include_calls else ()
    if section != "references" or include_calls:
        return records
    return (
        record
        for record in records
        if not isinstance(record, dict)
        or not isinstance(record.get("kind"), str)
        or binds_reference(
            record["kind"], include_calls=False, include_source_ownership=include_source_ownership
        )
    )


class SectionLists(Protocol):
    """The raw record lists of a scan that the dependency proof reads."""

    modules: list[RawRecord]
    imports: list[RawRecord]
    symbols: list[RawRecord]
    references: list[RawRecord]
    calls: list[RawRecord]


def bound_sections(
    scan: SectionLists,
    declarations: Iterable[RawRecord],
    *,
    include_calls: bool,
    include_source_ownership: bool,
) -> Iterator[Section]:
    """Parse only the raw records that the proof binds, section by section."""
    named = (
        ("modules", scan.modules),
        ("imports", scan.imports),
        ("symbols", scan.symbols),
        ("references", scan.references),
        ("calls", scan.calls),
        ("declarations", declarations),
    )
    for name, records in named:
        bound = _bound_raw_records(
            name,
            records,
            include_calls=include_calls,
            include_source_ownership=include_source_ownership,
        )
        yield Section(name, tuple(parse_record(item) for item in bound))
