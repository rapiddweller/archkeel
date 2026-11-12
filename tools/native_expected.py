# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare the self-check of native/ with its pinned result (AD-357).

`make self-validate-native` writes the report of native/ with its own contract. Since #953 the scan
of native/ has pair gaps: method calls that may reach `impl` blocks of other files. The pinned file
`native/expected-gaps.json` lists each gap (source module, module, reason) and the status of each
rule. A new gap, a missing gap, another status, a violation, a diagnostic other than
`incomplete_scan` or another exit code (2 with gaps, 0 without) fails the gate. With no pinned gap,
every rule must PASS.

Run: `python tools/native_expected.py <report.json> <expected-gaps.json> [--write]`.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

Gap = tuple[str, str, str]


def observed(report: dict[str, Any]) -> tuple[list[Gap], dict[str, str], list[str]]:
    """The gaps, the status of each rule, and each rule with a violation."""
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
    violated = sorted(str(item["id"]) for item in rules if item.get("count"))
    return gaps, statuses, violated


def _where(report: dict[str, Any], rule: str, limit: int = 5) -> str:
    """The title and the first file:line of the first findings of a rule (AD-382)."""
    found = [f for f in report.get("findings") or () if rule in (f.get("rules") or ())]
    lines = [
        f"\n  {f['title']} at "
        + ", ".join(f"{at['path']}:{at['line']}" for at in (f.get("locations") or ())[:3])
        for f in found[:limit]
    ]
    return "".join(lines) + (f"\n  and {len(found) - limit} more" if len(found) > limit else "")


def problems(report: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    gaps, statuses, violated = observed(report)
    pinned = sorted(tuple(gap) for gap in expected["gaps"])
    found = [f"new gap: {gap}" for gap in sorted((Counter(gaps) - Counter(pinned)).elements())]
    found += [f"missing gap: {gap}" for gap in sorted((Counter(pinned) - Counter(gaps)).elements())]
    wanted = expected["rules"] if pinned else dict.fromkeys(expected["rules"], "PASS")
    if statuses != wanted:
        found.append(f"rule statuses {statuses} differ from {wanted}")
    found += [f"violation of {rule}{_where(report, rule)}" for rule in violated]
    kinds = {str(item["kind"]) for item in report.get("diagnostics") or ()} - {"incomplete_scan"}
    found += [f"diagnostic {kind}" for kind in sorted(kinds)]
    exit_code = 2 if pinned else 0
    if report.get("exit_code") != exit_code:
        found.append(f"exit code {report.get('exit_code')} differs from {exit_code}")
    return found


def summary(report: dict[str, Any]) -> str:
    """The counts of the run, so that a green gate does not read as proven (AD-382)."""
    gaps, statuses, violated = observed(report)
    count = Counter(statuses.values())
    return (
        f"native self-check: {count['PASS']} rules PASS, {count['FAIL']} FAIL, "
        f"{count['UNKNOWN']} UNKNOWN; {len(gaps)} pinned gaps, {len(violated)} violations"
    )


def main(argv: list[str]) -> int:
    report = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    path = Path(argv[1])
    if argv[2:] == ["--write"]:
        gaps, statuses, _ = observed(report)
        pinned = {"rules": statuses, "gaps": [list(gap) for gap in gaps]}
        path.write_text(json.dumps(pinned, indent=2) + "\n", encoding="utf-8")
        return 0
    found = problems(report, json.loads(path.read_text(encoding="utf-8")))
    for line in found:
        print(line, file=sys.stderr)
    print(summary(report))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
