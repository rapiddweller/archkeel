# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read the baseline part of a core frame and fail closed (AD-546).

The core compares the run with the baseline file and gives the state, the differences and the
exit code. The shell reads the part, checks that it holds together, and copies the exit code. It
holds no comparison. A part that contradicts itself is a `CoreError`, never a verdict.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from .core_json import CoreError, _count, _fields, _object, _text


class BaselineState(StrEnum):
    """How the run stands against the baseline file."""

    CURRENT = "current"
    DRIFT = "drift"
    INVALID = "invalid"
    NOT_COMPARED = "not_compared"
    WRITTEN = "written"
    NOT_WRITTEN = "not_written"


class Difference(StrEnum):
    UNKNOWN = "unknown"
    VIOLATION = "violation"
    BUDGET = "budget"


@dataclass(frozen=True, slots=True)
class Changed:
    """One thing that the run and the file do not share."""

    what: Difference
    kind: str
    subject: str
    reason: str
    run: int
    file: int


@dataclass(frozen=True, slots=True)
class NamedBaselineGap:
    kind: str
    subject: str
    reason: str


@dataclass(frozen=True, slots=True)
class BaselineResult:
    state: BaselineState
    exit_code: int
    accepted_entries: int
    accepted_unknowns: int
    new: tuple[Changed, ...]
    gone: tuple[Changed, ...]
    gaps: tuple[NamedBaselineGap, ...]
    # The bytes that `--write-baseline` writes, as text. `None` when the run writes nothing.
    file: str | None


_FIELDS: Final = frozenset(
    {"state", "exit_code", "accepted_entries", "accepted_unknowns", "new", "gone", "gaps"}
)
_CHANGED: Final = frozenset({"what", "kind", "subject", "reason", "run", "file"})
_NAMED: Final = frozenset({"kind", "subject", "reason"})


def _changed(value: object, where: str) -> tuple[Changed, ...]:
    if not isinstance(value, list):
        raise CoreError(f"the core frame field {where} is not a list")
    found: list[Changed] = []
    for index, item in enumerate(value):
        row = _fields(item, f"{where}[{index}]", _CHANGED)
        try:
            what = Difference(_text(row["what"], f"{where}.what"))
        except ValueError as error:
            raise CoreError(f"the core frame field {where} has an unknown difference") from error
        found.append(
            Changed(
                what,
                _text(row["kind"], f"{where}.kind"),
                _text(row["subject"], f"{where}.subject"),
                _text(row["reason"], f"{where}.reason"),
                _count(row["run"], f"{where}.run"),
                _count(row["file"], f"{where}.file"),
            )
        )
    return tuple(found)


def _named(value: object) -> tuple[NamedBaselineGap, ...]:
    if not isinstance(value, list):
        raise CoreError("the core frame field baseline.gaps is not a list")
    rows = [_fields(item, "baseline.gaps", _NAMED) for item in value]
    return tuple(
        NamedBaselineGap(
            _text(row["kind"], "baseline.gaps.kind"),
            _text(row["subject"], "baseline.gaps.subject"),
            _text(row["reason"], "baseline.gaps.reason"),
        )
        for row in rows
    )


def read_baseline(value: object, status: str) -> BaselineResult:
    """The checked part. `status` is the status of the run: UNKNOWN never gives exit code 0."""
    found = _object(value, "baseline")
    file = found.pop("file", None)
    part = _fields(found, "baseline", _FIELDS)
    try:
        state = BaselineState(_text(part["state"], "baseline.state"))
    except ValueError as error:
        raise CoreError("the core frame field baseline.state has an unknown word") from error
    exit_code = _count(part["exit_code"], "baseline.exit_code")
    new, gone = _changed(part["new"], "baseline.new"), _changed(part["gone"], "baseline.gone")
    gaps = _named(part["gaps"])
    if exit_code > 2:
        raise CoreError("the core frame baseline.exit_code is not 0, 1 or 2")
    if state in {BaselineState.DRIFT, BaselineState.INVALID} and exit_code != 1:
        raise CoreError(f"the core frame baseline is {state} and does not exit 1")
    if state is BaselineState.NOT_COMPARED and exit_code != 1:
        raise CoreError("the core frame baseline is not_compared and does not exit 1")
    if state is BaselineState.DRIFT and not (new or gone):
        raise CoreError("the core frame baseline is drift without a difference")
    if state is BaselineState.CURRENT and (new or gone):
        raise CoreError("the core frame baseline is current with a difference")
    if exit_code == 0 and (status == "UNKNOWN" or gaps):
        raise CoreError("the core frame baseline exits 0 for a run that has an UNKNOWN")
    if file is not None and not isinstance(file, str):
        raise CoreError("the core frame field baseline.file is not a text")
    return BaselineResult(
        state,
        exit_code,
        _count(part["accepted_entries"], "baseline.accepted_entries"),
        _count(part["accepted_unknowns"], "baseline.accepted_unknowns"),
        new,
        gone,
        gaps,
        file,
    )


def lines(result: BaselineResult) -> Sequence[str]:
    """The text lines of the part. An accepted UNKNOWN keeps its word: it says "accepted"."""
    out = [
        f"Baseline: {result.state}; {result.accepted_entries} entries "
        f"({result.accepted_unknowns} UNKNOWN items, an entry has a count)"
    ]
    if result.accepted_unknowns:
        out.append(
            "Each accepted UNKNOWN stays UNKNOWN: it is known, not decided, and the run exits 2."
        )
    for side, rows in (("new", result.new), ("stale", result.gone)):
        for row in rows:
            out.append(
                f"Baseline {side}: {row.what}: {row.kind}: {row.subject}: {row.reason} "
                f"(run {row.run}, file {row.file})"
            )
    out.extend(f"Baseline gap: {gap.kind}: {gap.subject}: {gap.reason}" for gap in result.gaps)
    if result.new or result.gone:
        out.append("Action: Fix the new item, or rewrite the file with --write-baseline.")
    return out


def as_json(result: BaselineResult) -> Mapping[str, object]:
    """The part for the result of the command, without the bytes of the file."""
    return {
        "state": result.state,
        "exit_code": result.exit_code,
        "accepted_entries": result.accepted_entries,
        "accepted_unknowns": result.accepted_unknowns,
        "new": [vars_of(row) for row in result.new],
        "gone": [vars_of(row) for row in result.gone],
        "gaps": [{"kind": g.kind, "subject": g.subject, "reason": g.reason} for g in result.gaps],
    }


def vars_of(row: Changed) -> Mapping[str, object]:
    return {
        "what": row.what,
        "kind": row.kind,
        "subject": row.subject,
        "reason": row.reason,
        "run": row.run,
        "file": row.file,
    }
