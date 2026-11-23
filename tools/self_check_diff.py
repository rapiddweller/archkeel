# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare a self-check result with the result of the same run on the base commit (AD-1061).

Run: `python tools/self_check_diff.py <base.json> <pr.json> [--base-sha S] [--labels a,b]
[--body-file F]` or `python tools/self_check_diff.py same <a.json> <b.json>`.

A file is the full JSON of `archkeel validate` or the condensed form of `condense`: the gaps as
(kind, subjects, reason), the rule statuses, the UNKNOWN reason kinds, the violations and the exit
code, with the sha and the native tree that it was computed for. The PR result must have no
refusal, no FAIL, no violation and the exit code that its statuses give. Growth is a new gap (a
multiset compare, so a growing gap counts for each occurrence), a new UNKNOWN reason kind, or a
rule with a worse status (PASS < UNKNOWN < FAIL). Removals do not offset additions. Growth passes
only with the label `ratchet-lead` and the PR text line `Ratchet growth: <N> items: <reason>`,
where N is the printed count. A base that is missing, corrupt, refused or for another commit
compares as an empty base, and only the same approval passes it.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from native_expected import RANK, observed

FORMAT = "selfcheck-v1"
LABEL = "ratchet-lead"
LINE = re.compile(r"^Ratchet growth: (\d+) items?: (\S.{9,})$", re.MULTILINE)
SHOWN = 20
FIELDS = ("rules", "unknown", "gaps", "violations", "exit_code")
EMPTY: dict[str, Any] = {"rules": {}, "unknown": {}, "gaps": [], "violations": []}


class Unusable(Exception):
    """A result file that cannot be compared; the message names the file and the reason."""


def condense(result: dict[str, Any], sha: str = "", tree: str = "") -> dict[str, Any]:
    """The parts of a full result that the comparison needs."""
    gaps, rules, violations = observed(result)
    frame: dict[str, Any] = result.get("frame") or {}
    return {
        "format": FORMAT,
        "sha": sha,
        "tree": tree,
        "exit_code": result.get("exit_code"),
        "refusal": result.get("refusal"),
        "rules": rules,
        "unknown": dict(frame.get("unknown_kinds") or {}),
        "gaps": [list(gap) for gap in gaps],
        "violations": [list(item) for item in violations],
        "violation_counts": dict(frame.get("violations") or {}),
    }


def load(path: str) -> dict[str, Any]:
    """A condensed result from a file; raise `Unusable` with the reason when it is not one."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise Unusable(f"{path} is missing or unreadable ({error.strerror})") from error
    try:
        found = json.loads(text)
    except ValueError as error:
        raise Unusable(f"{path} is empty or corrupt ({error})") from error
    if not isinstance(found, dict):
        raise Unusable(f"{path} is not a result object")
    if found.get("format") != FORMAT:
        if "frame" not in found and "refusal" not in found:
            raise Unusable(f"{path} is not a self-check result")
        try:
            found = condense(found)
        except (AttributeError, TypeError, KeyError, ValueError) as error:
            raise Unusable(f"{path} is corrupt: its fields have the wrong shape") from error
    gaps = found.get("gaps")
    shaped = isinstance(gaps, list) and all(isinstance(g, list) and len(g) == 3 for g in gaps)
    if not shaped or any(not isinstance(found.get(f), (dict, list, int)) for f in FIELDS[:4]):
        raise Unusable(f"{path} is corrupt: its fields have the wrong shape")
    return dict(found)


def absolute(pr: dict[str, Any]) -> list[str]:
    """What must hold for the PR result alone: no refusal, FAIL or violation; a true exit code."""
    if pr.get("refusal"):
        refusal = pr["refusal"]
        return [f"the PR result is a refusal: {refusal.get('kind')}: {refusal.get('message')}"]
    found = [
        f"rule {rule} is FAIL" for rule, status in sorted(pr["rules"].items()) if status == "FAIL"
    ]
    found += [f"violation: {item}" for item in pr["violations"]]
    counted = sum(int(n) for n in (pr.get("violation_counts") or {}).values())
    if counted > len(pr["violations"]):
        found.append(f"the result counts {counted} violations and lists {len(pr['violations'])}")
    statuses = set(pr["rules"].values())
    expected = (
        1 if "FAIL" in statuses else 2 if statuses - {"PASS"} or pr["gaps"] or not statuses else 0
    )
    if pr.get("exit_code") != expected:
        found.append(
            f"exit code {pr.get('exit_code')} differs from {expected}, which its statuses give"
        )
    return found


def grown(base: dict[str, Any], pr: dict[str, Any]) -> tuple[list[str], int, int]:
    """The grown items by name, their count and the count of removed gaps."""
    old = Counter(map(tuple, base["gaps"]))
    new = Counter(map(tuple, pr["gaps"]))
    by_reason: dict[tuple[str, str], list[str]] = defaultdict(list)
    for kind, subjects, reason in sorted((new - old).elements()):
        by_reason[(kind, reason)].append(subjects)
    lines: list[str] = []
    for (kind, reason), subjects in sorted(by_reason.items()):
        lines.append(f"GROWN {len(subjects)} new gaps [{kind}]: {reason}")
        lines += [f"    {item}" for item in subjects[:SHOWN]]
        if len(subjects) > SHOWN:
            lines.append(f"    and {len(subjects) - SHOWN} more")
    count = sum(len(subjects) for subjects in by_reason.values())
    for rule, status in sorted(pr["rules"].items()):
        before = base["rules"].get(rule, "PASS")
        if RANK.get(status, 2) > RANK.get(before, 2):
            lines.append(f"GROWN rule status: {rule} {before} -> {status}")
            count += 1
    for rule, kind in sorted(pr["unknown"].items()):
        if base["unknown"].get(rule) != kind:
            lines.append(f"GROWN UNKNOWN reason: {rule}: {kind}")
            count += 1
    return lines, count, sum((old - new).values())


def approval(count: int, labels: list[str], body: str) -> list[str]:
    """The reasons why growth of `count` items is not approved; empty when it is."""
    ask = f"`Ratchet growth: {count} items: <reason>`"
    if LABEL not in labels:
        return [f"growth of {count} items needs the label {LABEL} and the PR text line {ask}"]
    said = [int(found.group(1)) for found in LINE.finditer(body)]
    if not said:
        return [f"the label {LABEL} is set, but the PR text has no line {ask}"]
    if count not in said:
        return [f"the PR text says Ratchet growth: {said[0]} items, the grown count is {count}"]
    return []


def where(result: dict[str, Any]) -> str:
    return (
        f"{str(result.get('sha') or '?')[:12]} (native tree {str(result.get('tree') or '?')[:12]})"
    )


def check(base_path: str, pr_path: str, base_sha: str, labels: list[str], body: str) -> int:
    """Print the comparison and return the exit code: 0 when nothing grew or growth is approved."""
    try:
        pr = load(pr_path)
    except Unusable as error:
        print(f"the PR result is unusable: {error}")
        return 1
    errors = absolute(pr)
    try:
        base = load(base_path)
        if base.get("refusal"):
            raise Unusable(f"{base_path} is a refusal: {base['refusal'].get('kind')}")
        if base_sha and base.get("sha") != base_sha:
            raise Unusable(f"{base_path} is for {base.get('sha') or 'no commit'}, not {base_sha}")
        print(f"base {where(base)}; PR {where(pr)}")
    except Unusable as error:
        base = EMPTY
        print(f"the base result is unusable: {error}; nothing is compared, each item counts as new")
        if LABEL not in labels:
            errors.append(f"unusable base: set the label {LABEL} and the growth line to pass")
    lines, count, removed = grown(base, pr)
    print("\n".join(lines))
    if count:
        errors += approval(count, labels, body)
    if count and removed:
        print(f"{removed} gaps are removed. A reworded reason or a renamed module shows as both.")
    print(f"self-check diff: grown {count}, removed {removed}")
    for line in errors:
        print(f"FAIL {line}")
    return 1 if errors else 0


def same(first: str, second: str) -> int:
    """Exit 0 when two results of one commit are equal (the release and the gate profile)."""
    try:
        one, two = load(first), load(second)
    except Unusable as error:
        print(f"FAIL {error}")
        return 1
    differ = [f for f in FIELDS if f != "gaps" and one.get(f) != two.get(f)]
    if Counter(map(tuple, one["gaps"])) != Counter(map(tuple, two["gaps"])):
        differ.append("gaps")
    print(f"same-commit compare: fields that differ: {differ or 'none'}")
    return 1 if differ else 0


def main(argv: list[str]) -> int:
    def option(name: str) -> str:
        return argv[argv.index(name) + 1] if name in argv else ""

    if argv[:1] == ["same"] and len(argv) == 3:
        return same(argv[1], argv[2])
    if len(argv) < 2:
        print(__doc__)
        return 2
    labels = [name for name in option("--labels").split(",") if name]
    body_file = option("--body-file")
    body = (
        Path(body_file).read_text(encoding="utf-8")
        if body_file and Path(body_file).is_file()
        else ""
    )
    return check(argv[0], argv[1], option("--base-sha"), labels, body)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
