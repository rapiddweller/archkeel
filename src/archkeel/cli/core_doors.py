# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The premises of a core frame: declared door reach (AD-664) and stated external users (#1549).

A premise is a claim of the contract, not a proof. A PASS that rests on one is never a plain PASS:
the frame names each premise of a rule in `premises`, the door sites also in `assumed`, each
applied door declaration in `door_reach`, and the premises of the run in words in `assuming`.
This module reads these keys and writes the text lines; it decides nothing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from .core_json import CoreError, as_count, as_object, as_text, as_texts


@dataclass(frozen=True, slots=True)
class DoorRow:
    """One applied declaration of a door reach."""

    id: str
    module: str
    line: int
    door: str
    loads: tuple[str, ...]
    changes: tuple[str, ...]


#: The kinds of a premise that the core writes.
PREMISE_KINDS: Final = ("door_reach", "external_user")


@dataclass(frozen=True, slots=True)
class Premises:
    """The premises of the PASS rules: each rule with its (kind, subject) pairs, and the words."""

    rules: Mapping[str, tuple[tuple[str, str], ...]]
    assuming: str | None


def read_premises(frame: Mapping[str, object], passing: set[str]) -> Premises:
    """The premises of each PASS rule and the words of the run (#1549)."""
    rules: dict[str, tuple[tuple[str, str], ...]] = {}
    for rule, rows in as_object(frame.get("premises", {}), "premises").items():
        if not isinstance(rows, list) or not rows:
            raise CoreError(f"the core frame field premises.{rule} is not a list of premises")
        pairs = []
        for row in rows:
            fields = as_object(row, f"premises.{rule}[]")
            kind = as_text(fields["kind"], "premises.kind")
            if kind not in PREMISE_KINDS:
                raise CoreError(f"the core frame names a premise of the kind {kind}")
            pairs.append((kind, as_text(fields["subject"], "premises.subject")))
        rules[rule] = tuple(pairs)
    if not passing.issuperset(rules):
        raise CoreError("the core frame names a rule under a premise that is not PASS")
    words = frame.get("assuming")
    assuming = None if words is None else as_text(words, "assuming")
    if rules and assuming is None:
        raise CoreError("the core frame names premises without their words")
    return Premises(rules, assuming)


def _texts(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise CoreError(f"the core frame field {where} is not a list")
    return tuple(as_text(item, f"{where}[]") for item in value)


def pass_qualifiers(
    frame: Mapping[str, object], passing: set[str]
) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    """The qualifiers of the PASS rules: beyond the reference engine, and under a declared reach."""
    beyond = as_texts(frame["beyond"], "beyond")
    if not passing.issuperset(beyond):
        raise CoreError("the core frame names a rule beyond the reference that is not PASS")
    return beyond, _read_assumed(frame, passing)


def _read_assumed(frame: Mapping[str, object], passing: set[str]) -> dict[str, tuple[str, ...]]:
    """The door sites of each PASS rule that holds only under a declared reach."""
    found = {
        rule: _texts(sites, f"assumed.{rule}")
        for rule, sites in as_object(frame.get("assumed", {}), "assumed").items()
    }
    if not passing.issuperset(found):
        raise CoreError("the core frame names a rule under a declared reach that is not PASS")
    if any(not sites for sites in found.values()):
        raise CoreError("the core frame names a rule under a declared reach without a door")
    return found


def read_doors(frame: Mapping[str, object]) -> tuple[DoorRow, ...]:
    """The applied declarations of the run."""
    value = frame.get("door_reach", [])
    if not isinstance(value, list):
        raise CoreError("the core frame field door_reach is not a list")
    rows = []
    for item in value:
        fields = as_object(item, "door_reach[]")
        rows.append(
            DoorRow(
                id=as_text(fields["id"], "door_reach.id"),
                module=as_text(fields["module"], "door_reach.module"),
                line=as_count(fields["line"], "door_reach.line"),
                door=as_text(fields["door"], "door_reach.door"),
                loads=_texts(fields["loads"], "door_reach.loads"),
                changes=_texts(fields["changes"], "door_reach.changes"),
            )
        )
    return tuple(rows)


#: The group of a gap whose door has an applied declaration: it is a premise, not a job.
DECLARED: Final = "door_reach.declared"


def declared(subjects: Sequence[str], lines: Sequence[int], doors: Sequence[DoorRow]) -> str | None:
    """The id of the applied declaration of a gap, from its module and the lines of its evidence."""
    for row in doors:
        if row.module in subjects and row.line in lines:
            return row.id
    return None


def qualifier(words: str) -> str:
    """`PASS assuming <words>`: the words are the field `assuming` of the core, as on the page."""
    return f"PASS assuming {words}"


def door_lines(
    premises: Premises, doors: Sequence[DoorRow], shown: int, show_all: bool
) -> list[str]:
    """The applied door declarations, the stated external users and the rules that rest on them."""
    if premises.assuming is None:
        return []
    count = len(premises.rules)
    lines = [f"{qualifier(premises.assuming)} ({count} rules); a premise is not a proof:"]
    for row in doors:
        loads = ", ".join(row.loads) or "nothing"
        changes = ", ".join(row.changes) or "nothing"
        lines.append(
            f"  {row.id}: {row.module}:{row.line} ({row.door}) loads {loads}; changes {changes}"
        )
    pairs = [pair for found in premises.rules.values() for pair in found]
    users = sorted({subject for kind, subject in pairs if kind == "external_user"})
    if users:
        lines.append(f"  stated external users: {', '.join(users)}")
    rules = sorted(premises.rules)
    if rules:
        listed = rules if show_all else rules[:shown]
        more = "" if show_all or len(rules) <= shown else f" and {len(rules) - shown} more"
        lines.append(f"  rules: {', '.join(listed)}{more}")
    return lines
