# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The integrity gate of the self-check run (AD-1260).

Run: `python tools/self_check_gate.py <result.json>`. `make self-validate-system` calls it on the
frame of the one system run, which holds the shell, the core and the studio; the gate checks each
part on its own. It reads the JSON of `archkeel report --json` too.

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


def one_part(frame: dict[str, Any], rules: list[str], label: str) -> list[str]:
    """The rule rows, the violations and the counts of one set of rules of a frame."""
    rows = {rule: frame["rules"].get(rule) for rule in rules} if rules else {}
    if not rows or any(row is None for row in rows.values()):
        return [f"{label}the result has no rules, so it proves nothing"]
    try:
        statuses = {str(rule): str(row[1]) for rule, row in rows.items()}
    except (TypeError, IndexError, KeyError):
        return [f"{label}a rule row of the result has the wrong shape"]
    found = [
        f"{label}rule {rule} has the status {status}, not PASS, FAIL or UNKNOWN"
        for rule, status in sorted(statuses.items())
        if status not in STATUSES
    ]
    found += [
        f"{label}rule {rule} is FAIL"
        for rule, status in sorted(statuses.items())
        if status == "FAIL"
    ]
    details = {rule: group for rule, group in (frame.get("details") or {}).items() if rule in rows}
    listed = [
        f"{label}violation: {rule}: {one(row.get('source'))} -> {one(row.get('target'))}"
        for rule, group in sorted(details.items())
        for row in group
    ]
    found += listed[:SHOWN]
    if len(listed) > SHOWN:
        found.append(f"{label}and {len(listed) - SHOWN} more violations")
    counted = sum(int(n) for rule, n in (frame.get("violations") or {}).items() if rule in rows)
    if counted > len(listed):
        found.append(f"{label}the result counts {counted} violations and lists {len(listed)}")
    return found


def problems(result: dict[str, Any]) -> list[str]:
    """Why the run is not a usable answer or says FAIL; empty when the gate is green.

    The result is the JSON of `archkeel report --json` (the frame is inside) or a frame that
    `--output` wrote. A frame of a system run holds its parts: each part is checked on its own
    rules, so a FAIL or a violation of one part fails the gate (AD-1260 for each part).
    """
    if refusal := result.get("refusal"):
        kind = refusal.get("kind") if isinstance(refusal, dict) else refusal
        message = refusal.get("message") if isinstance(refusal, dict) else ""
        return [f"the result is a refusal: {kind}: {message}"]
    frame = result.get("frame", result)
    rows = frame.get("rules") if isinstance(frame, dict) else None
    if not isinstance(frame, dict) or not isinstance(rows, dict) or not rows:
        return ["the result has no rules, so it proves nothing"]
    system = frame.get("system")
    if isinstance(system, dict):
        parts = system.get("parts")
        if not isinstance(parts, list) or not parts:
            return ["the system result has no parts, so it proves nothing"]
        found: list[str] = []
        for part in parts:
            rules = part.get("rules") if isinstance(part, dict) else None
            found += one_part(frame, rules or [], f"{part.get('id')}: " if rules else "part: ")
        return found
    found = one_part(frame, list(rows), "")
    gaps = len(frame.get("collection_gaps") or ()) + len(result.get("gaps") or ())
    values = {str(row[1]) for row in rows.values() if isinstance(row, list) and len(row) > 1}
    expected = 1 if "FAIL" in values else 2 if values - {"PASS"} or gaps else 0
    if "frame" in result and result.get("exit_code") != expected:
        found.append(
            f"exit code {result.get('exit_code')} differs from {expected}, which its statuses give"
        )
    return found


def counts(result: dict[str, Any]) -> str:
    frame: dict[str, Any] = result.get("frame", result) or {}
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
