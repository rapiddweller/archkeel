# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The premises of a core frame: declared trojan horse reach (AD-664) and stated external users
(#1549).

A premise is a claim of the contract, not a proof. A PASS that rests on one is never a plain PASS:
the frame names each premise of a rule in `premises`, the trojan horse sites also in `assumed`, each
applied trojan horse declaration in `trojan_horse_reach`, and the premises of the run in words in
`assuming`.
This module reads these keys and writes the text lines; it decides nothing.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from .core_json import CoreError, as_count, as_object, as_text, as_texts


@dataclass(frozen=True, slots=True)
class TrojanHorseRow:
    """One applied declaration of a trojan horse reach."""

    id: str
    module: str
    line: int
    trojan_horse: str
    loads: tuple[str, ...]
    changes: tuple[str, ...]
    rationale: str
    possible_loads: tuple[str, ...] = ()
    constant: str | None = None


#: The word of a premise kind: `trojan_horse_reach`, `external_user` or the name of a declared
# premise.
_KIND: Final = re.compile(r"[a-z][a-z_]*")


@dataclass(frozen=True, slots=True)
class Premises:
    """The premises of the PASS rules: each rule with its (kind, subject) pairs, and the words."""

    rules: Mapping[str, tuple[tuple[str, str], ...]]
    assuming: str | None
    #: Each FAIL rule whose every violation rests on a declared reach, with the declaration ids.
    fails: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    #: The notes of the run (code, text): facts that change no verdict (AD-1045).
    notes: tuple[tuple[str, str], ...] = ()


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
            if not _KIND.fullmatch(kind):
                raise CoreError(f"the core frame names a premise of the kind {kind!r}")
            pairs.append((kind, as_text(fields["subject"], "premises.subject")))
        rules[rule] = tuple(pairs)
    if not passing.issuperset(rules):
        raise CoreError("the core frame names a rule under a premise that is not PASS")
    words = frame.get("assuming")
    assuming = None if words is None else as_text(words, "assuming")
    if rules and assuming is None:
        raise CoreError("the core frame names premises without their words")
    fails = {
        rule: _texts(ids, f"fail_from_declared_reach.{rule}")
        for rule, ids in as_object(
            frame.get("fail_from_declared_reach", {}), "fail_from_declared_reach"
        ).items()
    }
    notes = tuple(
        (
            as_text(as_object(note, "notes[]")["code"], "notes.code"),
            as_text(as_object(note, "notes[]")["text"], "notes.text"),
        )
        for note in _list(frame.get("notes", []), "notes")
    )
    return Premises(rules, assuming, fails, notes)


def _list(value: object, where: str) -> list[object]:
    if not isinstance(value, list):
        raise CoreError(f"the core frame field {where} is not a list")
    return value


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
    """The trojan horse sites of each PASS rule that holds only under a declared reach."""
    found = {
        rule: _texts(sites, f"assumed.{rule}")
        for rule, sites in as_object(frame.get("assumed", {}), "assumed").items()
    }
    if not passing.issuperset(found):
        raise CoreError("the core frame names a rule under a declared reach that is not PASS")
    if any(not sites for sites in found.values()):
        raise CoreError("the core frame names a rule under a declared reach without a trojan horse")
    return found


def read_trojan_horses(frame: Mapping[str, object]) -> tuple[TrojanHorseRow, ...]:
    """The applied declarations of the run."""
    value = frame.get("trojan_horse_reach", [])
    if not isinstance(value, list):
        raise CoreError("the core frame field trojan_horse_reach is not a list")
    rows = []
    for item in value:
        fields = as_object(item, "trojan_horse_reach[]")
        constant = fields.get("constant")
        rows.append(
            TrojanHorseRow(
                id=as_text(fields["id"], "trojan_horse_reach.id"),
                module=as_text(fields["module"], "trojan_horse_reach.module"),
                line=as_count(fields["line"], "trojan_horse_reach.line"),
                trojan_horse=as_text(fields["trojan_horse"], "trojan_horse_reach.trojan_horse"),
                loads=_texts(fields["loads"], "trojan_horse_reach.loads"),
                changes=_texts(fields["changes"], "trojan_horse_reach.changes"),
                rationale=as_text(fields["rationale"], "trojan_horse_reach.rationale"),
                possible_loads=_texts(
                    fields.get("possible_loads", []), "trojan_horse_reach.possible_loads"
                ),
                constant=None
                if constant is None
                else as_text(constant, "trojan_horse_reach.constant"),
            )
        )
    return tuple(rows)


#: The group of a gap whose trojan horse has an applied declaration: it is a premise, not a job.
DECLARED: Final = "trojan_horse_reach.declared"


def declared(
    subjects: Sequence[str], lines: Sequence[int], trojan_horses: Sequence[TrojanHorseRow]
) -> str | None:
    """The id of the applied declaration of a gap, from its module and the lines of its evidence."""
    for row in trojan_horses:
        if row.module in subjects and row.line in lines:
            return row.id
    return None


def qualifier(words: str) -> str:
    """`PASS assuming <words>`: the words are the field `assuming` of the core, as on the page."""
    return f"PASS assuming {words}"


def trojan_horse_lines(
    premises: Premises, trojan_horses: Sequence[TrojanHorseRow], shown: int, show_all: bool
) -> list[str]:
    """The applied trojan horse declarations, the stated external users and the rules that rest on
    them."""
    lines = [f"Note ({code}): {text}" for code, text in premises.notes]
    if premises.assuming is not None and premises.rules:
        count = len(premises.rules)
        noun = "rule" if count == 1 else "rules"
        lines.append(f"{qualifier(premises.assuming)} ({count} {noun}); a premise is not a proof:")
    elif trojan_horses or premises.fails:
        lines.append("Declared reach (a premise, not a proof):")
    for row in trojan_horses:
        loads = (
            f"only the targets from {row.constant}"
            if row.constant
            else ", ".join(row.loads) or "nothing"
        )
        changes = ", ".join(row.changes) or "nothing"
        lines.append(
            f"  {row.id}: {row.module}:{row.line} ({row.trojan_horse}) "
            f"loads {loads}; changes {changes}"
        )
        lines.append(f"    Reason: {row.rationale}")
        if row.possible_loads:
            lines.append(f"    Possible targets: {', '.join(row.possible_loads)}")
    for rule, ids in sorted(premises.fails.items()):
        lines.append(f"  FAIL from a declared reach: {rule} (declared by {', '.join(ids)})")
    if premises.fails:
        lines.append(
            "    The contract allows an edge that it also forbids. Narrow `loads`, allow the edge"
            " in the rule, or move the code that loads."
        )
    by_kind: dict[str, set[str]] = {}
    for found in premises.rules.values():
        for kind, subject in found:
            by_kind.setdefault(kind, set()).add(subject)
    by_kind.pop("trojan_horse_reach", None)
    for kind, subjects in sorted(by_kind.items()):
        label = "stated external users" if kind == "external_user" else kind
        lines.append(f"  {label}: {', '.join(sorted(subjects))}")
    rules = sorted(premises.rules)
    if rules:
        listed = rules if show_all else rules[:shown]
        more = "" if show_all or len(rules) <= shown else f" and {len(rules) - shown} more"
        lines.append(f"  rules: {', '.join(listed)}{more}")
    return lines
