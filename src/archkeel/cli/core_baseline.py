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

from .core_json import CoreError, as_count, as_object, as_text
from .core_words import kind_label, plain


class BaselineState(StrEnum):
    """How the run stands against the baseline file."""

    CURRENT = "current"
    DRIFT = "drift"
    INVALID = "invalid"
    NOT_COMPARED = "not_compared"
    WRITTEN = "written"
    NOT_WRITTEN = "not_written"


class Difference(StrEnum):
    """What a baseline comparison found: an UNKNOWN, a violation or a budget."""

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
    """A gap that the core names about the baseline: its kind, subject and reason."""

    kind: str
    subject: str
    reason: str


@dataclass(frozen=True, slots=True)
class BaselineResult:
    """The baseline part of a frame: its state, the exit code that the core decided and the rows."""

    state: BaselineState
    exit_code: int
    accepted_entries: int
    accepted_unknowns: int
    new: tuple[Changed, ...]
    gone: tuple[Changed, ...]
    gaps: tuple[NamedBaselineGap, ...]
    # The rule rows that the file accepts. Each stays UNKNOWN.
    accepted_rules: tuple[str, ...]
    # The bytes that `--write-baseline` writes, as text. `None` when the run writes nothing.
    file: str | None


def _changed(value: object, where: str) -> tuple[Changed, ...]:
    if not isinstance(value, list):
        raise CoreError(f"the core frame field {where} is not a list")
    found: list[Changed] = []
    for index, item in enumerate(value):
        row = as_object(item, f"{where}[{index}]")
        try:
            what = Difference(as_text(row["what"], f"{where}.what"))
        except ValueError as error:
            raise CoreError(f"the core frame field {where} has an unknown difference") from error
        found.append(
            Changed(
                what,
                as_text(row["kind"], f"{where}.kind"),
                as_text(row["subject"], f"{where}.subject"),
                as_text(row["reason"], f"{where}.reason"),
                as_count(row["run"], f"{where}.run"),
                as_count(row["file"], f"{where}.file"),
            )
        )
    return tuple(found)


def _named(value: object) -> tuple[NamedBaselineGap, ...]:
    if not isinstance(value, list):
        raise CoreError("the core frame field baseline.gaps is not a list")
    rows = [as_object(item, "baseline.gaps") for item in value]
    return tuple(
        NamedBaselineGap(
            as_text(row["kind"], "baseline.gaps.kind"),
            as_text(row["subject"], "baseline.gaps.subject"),
            as_text(row["reason"], "baseline.gaps.reason"),
        )
        for row in rows
    )


def _rules(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise CoreError("the core frame field baseline.accepted_rules is not a list")
    return tuple(as_text(item, "baseline.accepted_rules") for item in value)


def read_baseline(value: object, status: str) -> BaselineResult:
    """The checked part. `status` is the status of the run: UNKNOWN never gives exit code 0."""
    found = as_object(value, "baseline")
    file = found.pop("file", None)
    part = as_object(found, "baseline")
    try:
        state = BaselineState(as_text(part["state"], "baseline.state"))
    except ValueError as error:
        raise CoreError("the core frame field baseline.state has an unknown word") from error
    exit_code = as_count(part["exit_code"], "baseline.exit_code")
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
        as_count(part["accepted_entries"], "baseline.accepted_entries"),
        as_count(part["accepted_unknowns"], "baseline.accepted_unknowns"),
        new,
        gone,
        gaps,
        _rules(part["accepted_rules"]),
        file,
    )


def lines(result: BaselineResult) -> Sequence[str]:
    """The text lines of the part. An accepted UNKNOWN keeps its word: it says "accepted"."""
    out = [
        f"Baseline: {result.state}; {result.accepted_entries} accepted entries match this run "
        f"({result.accepted_unknowns} UNKNOWN items; one entry can stand for several items)"
    ]
    if result.accepted_unknowns:
        out.append(
            "Each accepted UNKNOWN stays UNKNOWN: it is known, not decided, and the run exits 2."
        )
    for side, rows in (("new", result.new), ("stale", result.gone)):
        for row in rows:
            label = row.what if row.kind == row.what else f"{row.what} {kind_label(row.kind)}"
            note = f": {plain(row.reason)}" if row.reason else ""
            out.append(
                f"Baseline {side} {label}: {row.subject}{note} "
                f"(this run has {row.run}, the file lists {row.file})"
            )
    out.extend(
        f"Baseline gap {kind_label(gap.kind)}: {gap.subject}: {plain(gap.reason)}"
        for gap in result.gaps
    )
    if result.new or result.gone:
        out.append("Next: fix the new item, or rewrite the file with --write-baseline.")
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
        "accepted_rules": list(result.accepted_rules),
        "gaps": [{"kind": g.kind, "subject": g.subject, "reason": g.reason} for g in result.gaps],
    }


def vars_of(row: Changed) -> Mapping[str, object]:
    """The JSON fields of one changed baseline row."""

    return {
        "what": row.what,
        "kind": row.kind,
        "subject": row.subject,
        "reason": row.reason,
        "run": row.run,
        "file": row.file,
    }
