# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The change record of a widening comparison and the fail-closed field comparison (#11).

Every classifier in `ir.widening`, `ir.widening_rules` and `ir.widening_ratchet` returns
`WideningChange` values. `generic_field_widenings` reports any field that no set-based or
boolean classifier named, so an unrecognised difference never passes as neutral.
"""

from __future__ import annotations

import builtins as _builtins
from dataclasses import asdict, dataclass
from dataclasses import fields as dataclass_fields
from typing import Any, ClassVar, Final, Protocol


class _DataclassInstance(Protocol):
    """Structural stand-in for `_typeshed.DataclassInstance`, itself an external dependency."""

    __dataclass_fields__: ClassVar[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class WideningChange:
    subject: str
    field: str
    message: str


# Rationale and provenance are the design's own "neutral" prose; `id` and `kind` are the keys
# these classifiers match entries by, never content to diff themselves.
_ALWAYS_NEUTRAL: Final = frozenset({"id", "kind", "rationale", "provenance"})


def set_widenings(
    subject: str,
    field: str,
    before: frozenset[str],
    after: frozenset[str],
    *,
    grows_widens: bool,
) -> list[WideningChange]:
    """One field's added/removed entries, reporting only the direction that widens it."""
    label = f"{subject}.{field}"
    if grows_widens:
        return [
            WideningChange(subject, field, f"{label} gained {_builtins.str.__str__(item)!r}")
            for item in sorted(after - before)
        ]
    return [
        WideningChange(subject, field, f"{label} lost {_builtins.str.__str__(item)!r}")
        for item in sorted(before - after)
    ]


def generic_field_widenings(
    subject: str, before: _DataclassInstance, after: _DataclassInstance, *, handled: frozenset[str]
) -> list[WideningChange]:
    """Fail closed: any field neither neutral nor already classified is a widening if it differs.

    `handled` names the fields a set-based or boolean classifier already covered for this
    dataclass type. Everything else — an unenumerated field on a known kind, or the entire
    shape of a kind this module has no classifier for — falls through to here, which is what
    makes the "no diagnosis is treated as widening" test in tests/test_widening.py hold: two
    contracts differing only in a field this function does not name still report widening.
    """
    findings = []
    skip = _ALWAYS_NEUTRAL | handled
    # dataclasses.asdict, not a per-field getattr: the same construct CONSTRUCT-NO-DYNAMIC
    # forbids elsewhere in this codebase, avoided here for its own sake, not only self-checked.
    before_values = asdict(before)
    after_values = asdict(after)
    for field in dataclass_fields(before):
        if field.name in skip:
            continue
        before_value = before_values[field.name]
        after_value = after_values[field.name]
        if before_value != after_value:
            before_text, after_text = (
                repr(_builtins.str.__str__(value) if isinstance(value, str) else value)
                for value in (before_value, after_value)
            )
            findings.append(
                WideningChange(
                    subject,
                    field.name,
                    f"{subject}.{field.name} changed from {before_text} to {after_text}",
                )
            )
    return findings
