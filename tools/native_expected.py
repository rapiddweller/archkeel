# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare the self-check of native/ with its pinned result (AD-357, AD-382, AD-383).

`make self-validate-native` writes the report of native/ with its own contract. Since #953 the scan
of native/ has pair gaps: method calls that may reach `impl` blocks of other files. The pinned file
`native/expected-gaps.json` lists each gap (source module, module, reason), the status of each
rule, and each known violation (rule, subjects, the number of its follow-up issue). A new or a
missing gap, a new or a missing violation, a violation without an issue number, another status, a
diagnostic other than `incomplete_scan` or another exit code (2 with gaps, else 1 with
violations, else 0) fails the gate. With no pinned gap, each rule with a pinned violation must
FAIL and every other rule must PASS.

Run: `python tools/native_expected.py <report.json> <expected-gaps.json> [--write]`. `--write`
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
Violation = tuple[str, tuple[str, ...]]


def observed(report: dict[str, Any]) -> tuple[list[Gap], dict[str, str], list[Violation]]:
    """The gaps, the status of each rule, and each violation as (rule, sorted subjects)."""
    coverage = report.get("coverage") or {}
    gaps = sorted(
        (
            str(item["data"].get("source_module", "")),
            str(item["data"].get("module", "")),
            str(item["data"].get("reason", item["title"])),
        )
        for item in coverage.get("failures") or ()
    )
    rules = report.get("rule_assessments") or ()
    statuses = {str(item["id"]): str(item["status"]) for item in rules}
    findings = (item for item in report.get("findings") or () if item.get("kind") == "violation")
    violations = sorted(
        (str(rule), tuple(sorted(str(subject) for subject in item.get("subjects") or ())))
        for item in findings
        for rule in item.get("rules") or ()
    )
    return gaps, statuses, violations


def _where(report: dict[str, Any], rule: str, limit: int = 5) -> str:
    """The title and the first file:line of the first findings of a rule (AD-382)."""
    found = [f for f in report.get("findings") or () if rule in (f.get("rules") or ())]
    lines = [
        f"\n  {f['title']} at "
        + ", ".join(f"{at['path']}:{at['line']}" for at in (f.get("locations") or ())[:3])
        for f in found[:limit]
    ]
    return "".join(lines) + (f"\n  and {len(found) - limit} more" if len(found) > limit else "")


def _pinned_violations(expected: dict[str, Any]) -> dict[Violation, Any]:
    return {
        (str(item["rule"]), tuple(sorted(item["subjects"]))): item.get("issue")
        for item in expected.get("violations") or ()
    }


def _counted(
    report: dict[str, Any], rules: list[dict[str, Any]], violations: list[Violation]
) -> list[str]:
    """Each rule whose violation count is more than its violation findings show."""
    shown: dict[str, int] = {}
    for rule, _ in violations:
        shown[rule] = shown.get(rule, 0) + 1
    return [
        f"violation of {item['id']}{_where(report, str(item['id']))}"
        for item in rules
        if int(item.get("count") or 0) > shown.get(str(item["id"]), 0)
    ]


def problems(report: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    gaps, statuses, violations = observed(report)
    pinned = sorted(tuple(gap) for gap in expected["gaps"])
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
    found += _counted(report, list(report.get("rule_assessments") or ()), violations)
    failing = {rule for rule, _ in known}
    wanted = (
        expected["rules"]
        if pinned
        else {rule: "FAIL" if rule in failing else "PASS" for rule in expected["rules"]}
    )
    if statuses != wanted:
        found.append(f"rule statuses {statuses} differ from {wanted}")
    kinds = {str(item["kind"]) for item in report.get("diagnostics") or ()} - {"incomplete_scan"}
    found += [f"diagnostic {kind}" for kind in sorted(kinds)]
    exit_code = 2 if pinned else 1 if known else 0
    if report.get("exit_code") != exit_code:
        found.append(f"exit code {report.get('exit_code')} differs from {exit_code}")
    return found


def summary(report: dict[str, Any]) -> str:
    """The counts of the run, so that a green gate does not read as proven (AD-382)."""
    gaps, statuses, violations = observed(report)
    count = Counter(statuses.values())
    return (
        f"native self-check: {count['PASS']} rules PASS, {count['FAIL']} FAIL, "
        f"{count['UNKNOWN']} UNKNOWN; {len(gaps)} pinned gaps, {len(violations)} violations"
    )


def written(report: dict[str, Any], old: dict[str, Any]) -> dict[str, Any]:
    """The pinned file of a report: the issue of each violation comes from the old file."""
    gaps, statuses, violations = observed(report)
    issues = _pinned_violations(old)
    return {
        "rules": statuses,
        "gaps": [list(gap) for gap in gaps],
        "violations": [
            {"rule": rule, "subjects": list(subjects), "issue": issues.get((rule, subjects))}
            for rule, subjects in violations
        ],
    }


def main(argv: list[str]) -> int:
    report = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    path = Path(argv[1])
    if argv[2:] == ["--write"]:
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        path.write_text(json.dumps(written(report, old), indent=2) + "\n", encoding="utf-8")
        return 0
    found = problems(report, json.loads(path.read_text(encoding="utf-8")))
    for line in found:
        print(line, file=sys.stderr)
    print(summary(report))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
