# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The one exit table of the command line and the exit code of one run (AD-432, AD-546).

The table is the only place that says what an exit code means. The help prints it, the text header
states the code with its reason, and a test asserts that the printed word and the code agree.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from .core_frame import CoreError, CoreFrame, GapKind, Status

#: The meaning of each exit code. The word is the one that a header prints for that code.
EXIT_TABLE: Final[Mapping[int, tuple[str, str]]] = {
    0: (
        "PASS",
        "every rule is decided and passes (with a baseline: nothing differs, nothing UNKNOWN)",
    ),
    1: ("FAIL", "a rule is violated (with a baseline: the run differs, or the scan could not run)"),
    2: ("UNKNOWN", "something is not decided (UNKNOWN is not PASS), or the command could not run"),
}
_STATUS_EXIT: Final[Mapping[Status, int]] = {Status.PASS: 0, Status.FAIL: 1, Status.UNKNOWN: 2}


def word_of(code: int) -> str:
    """The verdict word that a header prints for an exit code."""
    return EXIT_TABLE[code][0]


def exit_code(frame: CoreFrame, *, baseline: bool, write_baseline: bool) -> int:
    """The exit code of a run. With a baseline, the core decided it (AD-546).

    A refused scan has nothing to compare. With `--baseline` it exits 1, because exit 2 then means
    that every UNKNOWN is accepted; without a baseline it exits 2. The table says so.
    """
    collect_refused = any(gap.kind is GapKind.COLLECT for gap in frame.gaps)
    if (baseline or write_baseline) and frame.baseline is None and not collect_refused:
        raise CoreError("the core frame lacks the baseline part that the request asked for")
    if frame.baseline is not None:
        return frame.baseline.exit_code
    if baseline and collect_refused:
        return 1
    return _STATUS_EXIT[frame.status]


def table_lines() -> list[str]:
    """The exit table as help lines."""
    return [f"  {code}  {word:<8}{meaning}" for code, (word, meaning) in EXIT_TABLE.items()]
