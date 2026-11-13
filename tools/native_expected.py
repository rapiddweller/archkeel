# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare a self-check of the core with its pinned result (AD-357, AD-382, AD-383, AD-430).

`make self-validate-native` writes the result of `archkeel validate` on native/ with its own
contract. The scan of native/ has pair gaps: method calls that may reach `impl` blocks of other
files. The pinned file `native/expected-gaps.json` lists each gap (kind, subjects, reason), the
status of each rule, the reason kind of each UNKNOWN rule, and each known violation (rule, source,
target, cause, the number of its follow-up issue). The gate fails on each difference: a new or a
missing gap, a new or a missing violation, a violation without an issue number, another status,
another reason kind, a refusal, or another exit code. The exit code comes from the pinned
statuses: 1 with a FAIL, else 2 with an UNKNOWN or a gap, else 0.

Run: `python tools/native_expected.py <result.json> <expected-gaps.json> [--write]`. `--write`
keeps the issue of each violation that the old file pins; a new violation gets no issue, and the
gate fails until a person writes one in. The gate checks only that a positive issue number is
present; it does not call the network, so it does not check that the issue exists or is open.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

Gap = tuple[str, str, str]
Violation = tuple[str, str, str, str]


def _frame(result: dict[str, Any]) -> dict[str, Any]:
    frame = result.get("frame")
    return frame if isinstance(frame, dict) else {}


def observed(result: dict[str, Any]) -> tuple[list[Gap], dict[str, str], list[Violation]]:
    """The gaps, the status of each rule, and each violation as (rule, source, target, cause)."""
    frame = _frame(result)
    gaps = [
        (str(gap["kind"]), ", ".join(sorted(map(str, gap["subjects"]))), str(gap["reason"]))
        for gap in frame.get("collection_gaps") or ()
    ]
    gaps += [
        (str(gap["kind"]), str(gap["subject"]), str(gap["reason"]))
        for gap in result.get("gaps") or ()
    ]
    statuses = {str(rule): str(row[1]) for rule, row in (frame.get("rules") or {}).items()}
    violations = sorted(
        (str(rule), str(row["source"]), str(row["target"]), str(row["cause"]))
        for rule, rows in (frame.get("details") or {}).items()
        for row in rows
    )
    return sorted(gaps), statuses, violations


def _where(result: dict[str, Any], rule: str, limit: int = 5) -> str:
    """The edge and the first file:line of the first violations of a rule (AD-382)."""
    frame = _frame(result)
    places = frame.get("locations") or {}
    rows = (frame.get("details") or {}).get(rule) or []
    lines = []
    for row in rows[:limit]:
        found = [places[key] for key in row.get("evidence") or () if key in places][:3]
        at = ", ".join(f"{place['path']}:{place['line']}" for place in found)
        lines.append(f"\n  {row['source']} -> {row['target']}: {row['cause']} at {at}")
    return "".join(lines) + (f"\n  and {len(rows) - limit} more" if len(rows) > limit else "")


def _pinned_violations(expected: dict[str, Any]) -> dict[Violation, Any]:
    return {
        (str(item["rule"]), str(item["source"]), str(item["target"]), str(item["cause"])): item.get(
            "issue"
        )
        for item in expected.get("violations") or ()
    }


def _counted(result: dict[str, Any], violations: list[Violation]) -> list[str]:
    """Each rule whose violation count is more than its violation rows show."""
    shown = Counter(rule for rule, *_ in violations)
    counts = _frame(result).get("violations") or {}
    return [
        f"violation of {rule}{_where(result, str(rule))}"
        for rule, count in sorted(counts.items())
        if int(count) > shown[str(rule)]
    ]


def expected_exit(expected: dict[str, Any]) -> int:
    """The exit code of the pinned result: FAIL is 1, else UNKNOWN or a gap is 2, else 0."""
    statuses = set(expected["rules"].values())
    if "FAIL" in statuses:
        return 1
    return 2 if statuses - {"PASS"} or expected["gaps"] or not statuses else 0


def problems(result: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    if "refusal" in result:
        refusal = result["refusal"]
        return [f"refused: {refusal['kind']}: {refusal['message']}"]
    gaps, statuses, violations = observed(result)
    pinned = sorted(
        (str(kind), str(subject), str(reason)) for kind, subject, reason in expected["gaps"]
    )
    known = _pinned_violations(expected)
    found = [f"new gap: {gap}" for gap in sorted((Counter(gaps) - Counter(pinned)).elements())]
    found += [f"missing gap: {gap}" for gap in sorted((Counter(pinned) - Counter(gaps)).elements())]
    found += [f"new violation: {item}" for item in violations if item not in known]
    found += [f"missing violation: {item}" for item in sorted(known) if item not in violations]
    found += [
        f"violation without an issue number: {item}"
        for item, issue in sorted(known.items())
        if not (isinstance(issue, int) and issue > 0)
    ]
    found += _counted(result, violations)
    if statuses != expected["rules"]:
        found.append(f"rule statuses {statuses} differ from {expected['rules']}")
    unknown = dict(_frame(result).get("unknown_kinds") or {})
    if unknown != expected["unknown"]:
        found.append(f"UNKNOWN reasons {unknown} differ from {expected['unknown']}")
    exit_code = expected_exit(expected)
    if result.get("exit_code") != exit_code:
        found.append(f"exit code {result.get('exit_code')} differs from {exit_code}")
    return found


def summary(result: dict[str, Any], name: str = "native") -> str:
    """The counts of the run, so that a green gate does not read as proven (AD-382)."""
    gaps, statuses, violations = observed(result)
    count = Counter(statuses.values())
    return (
        f"{name} self-check: {count['PASS']} rules PASS, {count['FAIL']} FAIL, "
        f"{count['UNKNOWN']} UNKNOWN; {len(gaps)} pinned gaps, {len(violations)} violations"
    )


def written(result: dict[str, Any], old: dict[str, Any]) -> dict[str, Any]:
    """The pinned file of a result: the issue of each violation comes from the old file."""
    gaps, statuses, violations = observed(result)
    issues = _pinned_violations(old)
    return {
        "name": old.get("name", "native"),
        "rules": statuses,
        "unknown": dict(_frame(result).get("unknown_kinds") or {}),
        "gaps": [list(gap) for gap in gaps],
        "violations": [
            {"rule": item[0], "source": item[1], "target": item[2], "cause": item[3]}
            | {"issue": issues.get(item)}
            for item in violations
        ],
    }


def main(argv: list[str]) -> int:
    result = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    path = Path(argv[1])
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if argv[2:] == ["--write"]:
        if "refusal" in result:
            print(f"refused: {result['refusal']}", file=sys.stderr)
            return 1
        path.write_text(json.dumps(written(result, old), indent=2) + "\n", encoding="utf-8")
        return 0
    found = problems(result, old)
    for line in found:
        print(line, file=sys.stderr)
    print(summary(result, str(old.get("name", "native"))))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
