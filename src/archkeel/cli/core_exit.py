# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The one exit table of the command line and the exit code of each outcome (AD-432, AD-731).

The table is the only place that says what an exit code means. The help prints it, the text header
states the code with its reason, and a test asserts that the printed word and the code agree.

`exit_for` is the only exit decision. With `--baseline`, exit 2 means that every UNKNOWN is
accepted, and CI treats it as green. Only a verdict can give that code: a run that did not give a
verdict, or a file that was not written, exits 1 with a baseline and 2 without one.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final

from .core_frame import CoreError, CoreFrame, GapKind, Status

#: The meaning of each exit code. The word is the one that a header prints for that code.
EXIT_TABLE: Final[Mapping[int, tuple[str, str]]] = {
    0: (
        "PASS",
        "every rule is decided and passes (with a baseline: nothing differs, nothing UNKNOWN)",
    ),
    1: (
        "FAIL",
        "a rule is violated (with a baseline: the run differs, or it did not run or write a file)",
    ),
    2: ("UNKNOWN", "something is not decided (UNKNOWN is not PASS), or the command could not run"),
}
_STATUS_EXIT: Final[Mapping[Status, int]] = {Status.PASS: 0, Status.FAIL: 1, Status.UNKNOWN: 2}


class Outcome(StrEnum):
    """What one command came to. Each exit decision starts from one of these."""

    # The core gave a frame, and each requested file was written.
    VERDICT = "verdict"
    # The core gave a frame, and the collector refused the scan: nothing was decided.
    COLLECT_REFUSED = "collect_refused"
    # The command gave no frame: an argument, the core binary, the core or its frame failed.
    COMMAND_REFUSED = "command_refused"
    # The core gave a frame, and a requested file (report or baseline) was not written.
    DELIVERY_FAILED = "delivery_failed"
    # A command without a verdict did its work: `init` drafted, `skill` installed.
    COMPLETED = "completed"


def word_of(code: int) -> str:
    """The verdict word that a header prints for an exit code."""
    return EXIT_TABLE[code][0]


def require_baseline_part(frame: CoreFrame, *, asked: bool) -> None:
    """A frame of a run that the collector did not refuse holds the baseline part it was asked."""
    collect_refused = any(gap.kind is GapKind.COLLECT for gap in frame.gaps)
    if asked and frame.baseline is None and not collect_refused:
        raise CoreError("the core frame lacks the baseline part that the request asked for")


def outcome_of(frame: CoreFrame, *, delivered: bool) -> Outcome:
    """The outcome of a run that gave a frame. A refused scan comes before a missing file."""
    if any(gap.kind is GapKind.COLLECT for gap in frame.gaps):
        return Outcome.COLLECT_REFUSED
    return Outcome.VERDICT if delivered else Outcome.DELIVERY_FAILED


def verdict_code(frame: CoreFrame) -> int:
    """The exit code of the verdict of the frame. With a baseline part, the core decided it."""
    if frame.baseline is not None:
        return frame.baseline.exit_code
    return _STATUS_EXIT[frame.status]


def exit_for(outcome: Outcome, frame: CoreFrame | None, *, baseline: bool) -> int:
    """The exit code of a command. `baseline` is true when the command compares with a file."""
    match outcome:
        case Outcome.VERDICT:
            if frame is None:
                raise CoreError("a verdict without a frame has no exit code")
            return verdict_code(frame)
        case Outcome.COLLECT_REFUSED | Outcome.COMMAND_REFUSED | Outcome.DELIVERY_FAILED:
            return 1 if baseline else 2
        case Outcome.COMPLETED:
            return 0


def envelope(
    command: str | None, outcome: Outcome, status: Status | None, code: int
) -> dict[str, object]:
    """The head of every JSON result (AD-735): the command, the outcome, the status of the run
    (`None` for a command without a verdict) and the exit code."""
    return {"command": command, "outcome": outcome, "status": status, "exit_code": code}


def table_lines() -> list[str]:
    """The exit table as help lines."""
    return [f"  {code}  {word:<8}{meaning}" for code, (word, meaning) in EXIT_TABLE.items()]
