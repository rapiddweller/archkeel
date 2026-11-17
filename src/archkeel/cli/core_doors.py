# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The declared reach of door sites in a core frame (AD-664).

A declared reach is a premise of the contract, not a proof. A PASS that rests on it is never a
plain PASS: the frame names it in `assumed`, and each applied declaration in `door_reach`. This
module reads both keys and writes the text lines; it decides nothing.
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


def qualifier(doors: int) -> str:
    """`PASS assuming the declared reach of N doors`, the same words as the page."""
    return f"PASS assuming the declared reach of {doors} door{'' if doors == 1 else 's'}"


def door_lines(
    assumed: Mapping[str, Sequence[str]], doors: Sequence[DoorRow], shown: int, show_all: bool
) -> list[str]:
    """The applied declarations and the rules whose PASS rests on them."""
    if not doors:
        return []
    lines = [
        f"{qualifier(len(doors))} ({len(assumed)} rules); the reach is a premise, not a proof:"
    ]
    for row in doors:
        loads = ", ".join(row.loads) or "nothing"
        changes = ", ".join(row.changes) or "nothing"
        lines.append(
            f"  {row.id}: {row.module}:{row.line} ({row.door}) loads {loads}; changes {changes}"
        )
    rules = sorted(assumed)
    if rules:
        listed = rules if show_all else rules[:shown]
        more = "" if show_all or len(rules) <= shown else f" and {len(rules) - shown} more"
        lines.append(f"  rules: {', '.join(listed)}{more}")
    return lines
