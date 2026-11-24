# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare a self-check result with the result of the same run on the base commit (AD-1064).

Run: `python tools/self_check_diff.py <base.json> <pr.json> [--base-sha S] [--labels a,b]
[--body-file F] [--report-only] [--grown-file F] [--summary-file F]`, or `same <a.json> <b.json>`,
`alone <pr.json>` (the PR result must be clean) or `shell <pr.json>` (all rules PASS, no gap).

A file is the full JSON of `archkeel validate` or the condensed form of `condense`: the gaps as
(kind, subjects, reason), the rule statuses, the UNKNOWN reason kinds, the violations and the exit
code, with the sha and the native tree that it was computed for. The PR result must have no
refusal, no FAIL, no violation and the exit code that its statuses give. Growth is a new gap (a
multiset compare, so a growing gap counts for each occurrence), a new UNKNOWN reason kind, or a
rule with a worse status (PASS < UNKNOWN < FAIL). Removals do not offset additions. Growth passes
only with the label `ratchet-lead` and the PR text line `Ratchet growth: <N> items: <reason>`,
where N is the printed count. A base that is missing, corrupt, refused or for another commit
compares as an empty base, and only the same approval passes it. The log shows the first
`SHOWN` grown items; `--grown-file` takes all of them. `--report-only` (main CI, which cannot see
the label) fails only on a result that is not clean.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

Gap = tuple[str, str, str]
Violation = tuple[str, str, str, str]
RANK = {"PASS": 0, "UNKNOWN": 1, "FAIL": 2}
RECEIVER_GAP = re.compile(r"A method call may reach the method (\S+) of a type in its own file")
FORMAT = "selfcheck-v1"
LABEL = "ratchet-lead"
LINE = re.compile(r"Ratchet growth: (0|[1-9][0-9]*) items?: \S.{9,}")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
SHOWN = 10
FIELDS = ("rules", "unknown", "gaps", "violations", "exit_code")
EMPTY: dict[str, Any] = {"rules": {}, "unknown": {}, "gaps": [], "violations": []}


class Unusable(Exception):
    """A result file that cannot be compared; the message names the file and the reason."""


def observed(result: dict[str, Any]) -> tuple[list[Gap], dict[str, str], list[Violation]]:
    """The gaps, the status of each rule, and each violation as (rule, source, target, cause)."""
    frame = result.get("frame")
    frame = frame if isinstance(frame, dict) else {}
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


def condense(result: dict[str, Any], sha: str = "", tree: str = "") -> dict[str, Any]:
    """The parts of a full result that the comparison needs."""
    if not result.get("refusal") and not isinstance(result.get("frame"), dict):
        raise ValueError("the result has no frame")
    gaps, rules, violations = observed(result)
    frame: dict[str, Any] = result.get("frame") or {}
    reply = (frame.get("self_test") or {}).get("reply") or {}
    files = reply.get("files")
    return {
        "format": FORMAT,
        "sha": sha,
        "tree": tree,
        "exit_code": result.get("exit_code"),
        "refusal": result.get("refusal"),
        "files": files if isinstance(files, int) else None,
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
            raise Unusable(
                f"{path} is corrupt: {error or 'its fields have the wrong shape'}"
            ) from error
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
    found = [] if pr["rules"] else ["the PR result has no rules, so it proves nothing"]
    found += [
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


def both(text: str) -> tuple[str, str]:
    return text, text


def grown(base: dict[str, Any], pr: dict[str, Any]) -> tuple[list[str], list[tuple[str, str]], int]:
    """The heading lines, each grown item as (short, full) text, and the count of removed gaps."""
    old = Counter(map(tuple, base["gaps"]))
    new = Counter(map(tuple, pr["gaps"]))
    by_reason: dict[tuple[str, str], list[str]] = defaultdict(list)
    for kind, subjects, reason in sorted((new - old).elements()):
        by_reason[(kind, reason)].append(subjects)
    lines: list[str] = []
    items: list[tuple[str, str]] = []
    for (kind, reason), subjects in sorted(by_reason.items()):
        lines.append(f"GROWN {len(subjects)} new gaps [{kind}]: {reason}")
        items += [(f"gap [{kind}] {item}", f"gap [{kind}] {item} -- {reason}") for item in subjects]
    if any(RECEIVER_GAP.search(reason) for _kind, reason in by_reason):
        lines.append(
            "Hint: write a method call as a path call (`Type::method(&value)`) or bind a typed "
            "local (`let local: Type = ...; local.method()`)"
        )
    for rule, status in sorted(pr["rules"].items()):
        before = base["rules"].get(rule, "PASS")
        if RANK.get(status, 2) > RANK.get(before, 2):
            items += [both(f"rule status: {rule} {before} -> {status}")]
    for rule, kind in sorted(pr["unknown"].items()):
        if base["unknown"].get(rule) != kind:
            items += [both(f"UNKNOWN reason: {rule}: {kind}")]
    items += [
        both(f"rule removed: {rule}") for rule in sorted(set(base["rules"]) - set(pr["rules"]))
    ]
    before, after = base.get("files"), pr.get("files")
    if isinstance(before, int) and not (isinstance(after, int) and after >= before):
        shown = after if after is not None else "?"
        items.append(both(f"scope shrank: files {before} -> {shown}"))
    return lines, items, sum((old - new).values())


def plain_lines(body: str) -> list[str]:
    """The lines of the PR text that a reader sees as plain text: no code, quote or comment."""
    lines: list[str] = []
    fence = ""
    quoted = False
    for line in re.sub(r"<!--.*?(-->|\Z)", "", body, flags=re.DOTALL).splitlines():
        marker = FENCE.match(line)
        if marker and (not fence or marker.group(1)[0] == fence):
            fence = "" if fence else marker.group(1)[0]
            continue
        quoted = line.lstrip().startswith(">") or (quoted and bool(line.strip()))
        if not fence and not quoted:
            lines.append(line.rstrip("\r"))
    return lines


def approval(count: int, labels: list[str], body: str) -> list[str]:
    """The reasons why growth of `count` items is not approved; empty when it is."""
    ask = f"`Ratchet growth: {count} items: <reason>`"
    if LABEL not in labels:
        return [f"growth of {count} items needs the label {LABEL} and the PR text line {ask}"]
    said = [int(m.group(1)) for line in plain_lines(body) if (m := LINE.fullmatch(line))]
    if not said:
        return [f"the label {LABEL} is set, but the PR text has no plain line {ask}"]
    if len(said) > 1:
        return [f"the PR text has {len(said)} Ratchet growth lines; keep exactly one"]
    if count not in said:
        return [f"the PR text says Ratchet growth: {said[0]} items, the grown count is {count}"]
    return []


def where(result: dict[str, Any]) -> str:
    return (
        f"{str(result.get('sha') or '?')[:12]} (native tree {str(result.get('tree') or '?')[:12]})"
    )


def summary(result: dict[str, Any]) -> str:
    """The counts of the run, so that a green gate does not read as proven (AD-382)."""
    count = Counter(result["rules"].values())
    return (
        f"self-check: {count['PASS']} rules PASS, {count['FAIL']} FAIL, "
        f"{count['UNKNOWN']} UNKNOWN; "
        f"{len(result['gaps'])} gap records, {len(result['violations'])} violations"
    )


def report(
    items: list[tuple[str, str]], errors: list[str], grown_file: str, summary_file: str
) -> None:
    """Print the first `SHOWN` grown items; keep all of them in `grown_file` and the summary."""
    for short, _full in items[:SHOWN]:
        print(f"    {short}")
    if len(items) > SHOWN:
        print(f"    and {len(items) - SHOWN} more")
    if grown_file and items:
        print(f"All {len(items)} grown items are in {grown_file}")
        Path(grown_file).parent.mkdir(parents=True, exist_ok=True)
        Path(grown_file).write_text("".join(f"{full}\n" for _s, full in items), encoding="utf-8")
    if summary_file and (items or errors):
        lines = [f"### Self-check: {len(items)} grown items"]
        lines += [f"- {text}" for text in errors]
        lines += [f"- `{short}`" for short, _full in items[:SHOWN]]
        if len(items) > SHOWN:
            lines.append(f"- and {len(items) - SHOWN} more")
        with Path(summary_file).open("a", encoding="utf-8") as out:
            out.write("\n".join(lines) + "\n")


def check(
    base_path: str,
    pr_path: str,
    base_sha: str,
    labels: list[str],
    body: str,
    report_only: bool = False,
    grown_file: str = "",
    summary_file: str = "",
) -> int:
    """Print the comparison and return the exit code: 0 when nothing grew or growth is approved."""
    try:
        pr = load(pr_path)
    except Unusable as error:
        print(f"the PR result is unusable: {error}")
        return 1
    hard = absolute(pr)
    errors: list[str] = []
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
    print(summary(pr))
    lines, items, removed = grown(base, pr)
    count = len(items)
    if lines:
        print("\n".join(lines))
    if count:
        errors += approval(count, labels, body)
    if count and removed:
        print(f"{removed} gaps are removed. A reworded reason or a renamed module shows as both.")
    print(f"self-check diff: grown {count}, removed {removed}")
    report(items, hard + errors, grown_file, summary_file)
    for line in hard + errors:
        print(f"FAIL {line}")
    if hard or errors:
        print("Run `make self-validate-native` to see the same result on your machine.")
    return 1 if hard or (errors and not report_only) else 0


def alone(path: str, strict: bool) -> int:
    """Exit 0 when one result is clean. `strict` (the shell): all rules PASS and no gap."""
    try:
        found = load(path)
    except Unusable as error:
        print(f"FAIL {error}")
        return 1
    errors = absolute(found)
    if strict and not errors:
        statuses = set(found["rules"].values())
        if statuses != {"PASS"} or found["gaps"]:
            errors.append("the result must have all rules PASS and no gap")
    if not found.get("refusal"):
        print(summary(found))
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
    if one.get("sha") != two.get("sha"):
        differ.append("sha")
    if Counter(map(tuple, one["gaps"])) != Counter(map(tuple, two["gaps"])):
        differ.append("gaps")
    print(f"same-commit compare: fields that differ: {differ or 'none'}")
    return 1 if differ else 0


def main(argv: list[str]) -> int:
    def option(name: str) -> str:
        return argv[argv.index(name) + 1] if name in argv else ""

    if argv[:1] == ["same"] and len(argv) == 3:
        return same(argv[1], argv[2])
    if argv[:1] in (["alone"], ["shell"]) and len(argv) == 2:
        return alone(argv[1], strict=argv[0] == "shell")
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
    return check(
        argv[0],
        argv[1],
        option("--base-sha"),
        labels,
        body,
        "--report-only" in argv,
        option("--grown-file"),
        option("--summary-file"),
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
