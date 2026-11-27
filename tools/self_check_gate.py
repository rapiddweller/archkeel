# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The integrity gate of one self-check run (AD-1260).

Run: `python tools/self_check_gate.py <result.json>`. `make self-validate-native` and `make
self-validate-shell` call it on the JSON of `archkeel report --json`.

The gate fails only when the run did not give a usable answer, or when the core says FAIL:
the file is missing, empty or not a result; the result is a refusal; it has no rule rows; a
status is not PASS, FAIL or UNKNOWN; the core reports a FAIL or a violation; the counted
violations differ from the listed ones; or the exit code is not the one that the statuses give.
An UNKNOWN rule and a gap never fail the gate and never turn into a PASS: the core decides them.
There is no comparison with another commit, no baseline and no label.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SHOWN = 10
STATUSES = ("PASS", "FAIL", "UNKNOWN")


def one(text: object) -> str:
    """One line: a newline in a reason or a message must not start a line of the log."""
    return " ".join(str(text).splitlines())


def read(path: str) -> dict[str, Any]:
    """The result object of a file; raise `ValueError` with the reason when it is none."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"{path} is missing or unreadable ({error.strerror})") from error
    try:
        found = json.loads(text)
    except ValueError as error:
        raise ValueError(f"{path} is empty or corrupt ({error})") from error
    if not isinstance(found, dict):
        raise ValueError(f"{path} is not a result object")
    return found


def problems(result: dict[str, Any]) -> list[str]:
    """Why the run is not a usable answer or says FAIL; empty when the gate is green."""
    if refusal := result.get("refusal"):
        kind = refusal.get("kind") if isinstance(refusal, dict) else refusal
        message = refusal.get("message") if isinstance(refusal, dict) else ""
        return [f"the result is a refusal: {kind}: {message}"]
    frame = result.get("frame")
    rows = frame.get("rules") if isinstance(frame, dict) else None
    if not isinstance(frame, dict) or not isinstance(rows, dict) or not rows:
        return ["the result has no rules, so it proves nothing"]
    try:
        statuses = {str(rule): str(row[1]) for rule, row in rows.items()}
    except (TypeError, IndexError, KeyError):
        return ["a rule row of the result has the wrong shape"]
    found = [
        f"rule {rule} has the status {status}, not PASS, FAIL or UNKNOWN"
        for rule, status in sorted(statuses.items())
        if status not in STATUSES
    ]
    found += [
        f"rule {rule} is FAIL" for rule, status in sorted(statuses.items()) if status == "FAIL"
    ]
    details = frame.get("details") or {}
    listed = [
        f"violation: {rule}: {one(row.get('source'))} -> {one(row.get('target'))}"
        for rule, group in sorted(details.items())
        for row in group
    ]
    found += listed[:SHOWN]
    if len(listed) > SHOWN:
        found.append(f"and {len(listed) - SHOWN} more violations")
    counted = sum(int(n) for n in (frame.get("violations") or {}).values())
    if counted > len(listed):
        found.append(f"the result counts {counted} violations and lists {len(listed)}")
    gaps = len(frame.get("collection_gaps") or ()) + len(result.get("gaps") or ())
    values = set(statuses.values())
    expected = 1 if "FAIL" in values else 2 if values - {"PASS"} or gaps else 0
    if result.get("exit_code") != expected:
        found.append(
            f"exit code {result.get('exit_code')} differs from {expected}, which its statuses give"
        )
    return found


def counts(result: dict[str, Any]) -> str:
    frame: dict[str, Any] = result.get("frame") or {}
    tally = Counter(str(row[1]) for row in (frame.get("rules") or {}).values())
    gaps = len(frame.get("collection_gaps") or ()) + len(result.get("gaps") or ())
    violations = sum(len(group) for group in (frame.get("details") or {}).values())
    return (
        f"self-check: {tally['PASS']} rules PASS, {tally['FAIL']} FAIL, "
        f"{tally['UNKNOWN']} UNKNOWN; {gaps} gap records, {violations} violations"
    )


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: self_check_gate.py <result.json>")
        return 2
    try:
        result = read(argv[0])
        found = problems(result)
        if not found:
            print(counts(result))
    except (ValueError, TypeError, AttributeError) as error:
        found = [f"the self-check result is unusable: {one(error)}"]
    for line in found:
        print(f"FAIL {one(line)}")
    print("self-check gate: GREEN" if not found else "self-check gate: RED (exit 1)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
