# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare a self-check of the core with its pinned result (AD-357, AD-382, AD-383, AD-432).

`make self-validate-native` writes the result of `archkeel validate` on native/ with its own
contract. The scan of native/ has pair gaps: method calls that may reach `impl` blocks of other
files. The pinned file `native/expected-gaps.json` lists each gap (kind, subjects, reason), the
status of each rule, the reason kind of each UNKNOWN rule, and each known violation (rule, source,
target, cause, the number of its follow-up issue). The gate fails on each difference: a new or a
missing gap, a new or a missing violation, a violation without an issue number, another status,
another reason kind, a refusal, or another exit code. The exit code comes from the pinned
statuses: 1 with a FAIL, else 2 with an UNKNOWN or a gap, else 0.

Ratchet (AD-672): a pin may only shrink. Growth is a gap, a violation, an UNKNOWN reason, or a
rule that is new and not PASS or has a worse status (PASS < UNKNOWN < FAIL) than before. Growth
enters only through the growth file next to the pin (`--growth`): one entry with a `reason` for
each grown item. A growing gap needs a new entry for each new occurrence (AD-944).
`--write` refuses growth that the growth file does not list, and
`--base-ref <ref>` fails when the pin has growth against its version at `<ref>` that the growth
file does not list. The lead raises the ratchet and logs the reason in the decision log.
AD-733: an entry whose finding is gone is stale; check mode fails on it, `--write` drops it, and a
missing base ref is printed.

Run: `python tools/native_expected.py <result.json> <expected-gaps.json> [--write]`. `--write`
keeps the issue of each violation that the old file pins; a new violation gets no issue, and the
gate fails until a person writes one in. The gate checks only that a positive issue number is
present; it does not call the network, so it does not check that the issue exists or is open.
For gap growth, pass `--growth <growth-file> --base-ref <committed-ref>`. Commit an intermediate
pin before assessing growth after a separate shrink.
"""

from __future__ import annotations

import json
import re
import subprocess
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


RECEIVER_GAP = re.compile(r"A method call may reach the method (\S+) of a type in its own file")


def receiver_gap_hint(result: dict[str, Any], new: list[Gap]) -> str | None:
    """A message for the new gaps of the field-receiver class (#1571): the files and the fix.

    A method call on a field or a local of an unproved type may reach a method of a type in its
    own file: the scan cannot rule it out, so the pair of modules is a gap. The new gaps name the
    modules of the calls; the evidence of each gap gives the file.
    """
    wanted = {gap for gap in new if RECEIVER_GAP.search(gap[2])}
    if not wanted:
        return None
    frame = _frame(result)
    places = frame.get("locations") or {}
    files: Counter[str] = Counter()
    for gap in frame.get("collection_gaps") or ():
        key = (str(gap["kind"]), ", ".join(sorted(map(str, gap["subjects"]))), str(gap["reason"]))
        if key not in wanted:
            continue
        found = [places[item] for item in gap.get("evidence") or () if item in places]
        where = str(found[0]["path"]) if found else key[1].replace(".", "/")
        files[where] += 1
    listed = ", ".join(f"{name} ({count})" for name, count in files.most_common(8))
    more = f" and {len(files) - 8} more" if len(files) > 8 else ""
    count = sum(files.values()) or len(wanted)
    return (
        f"your change adds {count} field-receiver gaps in {listed}{more}; "
        "write the calls as path calls (`Type::method(&value)`) or bind typed locals "
        "(`let local: Type = ...; local.method()`), then run `make self-validate-native`"
    )


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


RANK = {"PASS": 0, "UNKNOWN": 1, "FAIL": 2}


def growth(new: dict[str, Any], old: dict[str, Any]) -> list[list[str]]:
    """Each item of the pin `new` that the pin `old` does not hold or holds with a better status."""
    grown: list[list[str]] = []
    old_gaps = Counter(tuple(map(str, gap)) for gap in old.get("gaps") or ())
    new_gaps = Counter(tuple(map(str, gap)) for gap in new.get("gaps") or ())
    grown += [["gap", *gap] for gap in sorted((new_gaps - old_gaps).elements())]
    known = set(_pinned_violations(old))
    grown += [["violation", *item] for item in sorted(_pinned_violations(new)) if item not in known]
    old_rules = old.get("rules") or {}
    for rule, status in sorted((new.get("rules") or {}).items()):
        if RANK.get(status, 2) > RANK.get(old_rules.get(rule, "PASS"), 2):
            grown.append(["rule", str(rule), str(status)])
    old_unknown = old.get("unknown") or {}
    grown += [
        ["unknown", str(rule), str(kind)]
        for rule, kind in sorted((new.get("unknown") or {}).items())
        if old_unknown.get(rule) != kind
    ]
    return grown


def tokens(pin: dict[str, Any]) -> set[tuple[str, ...]]:
    """The items that a pin holds, in the form of a growth entry (AD-733)."""
    items = {("gap", *map(str, gap)) for gap in pin.get("gaps") or ()}
    items |= {("violation", *item) for item in _pinned_violations(pin)}
    items |= {
        ("rule", str(rule), str(status))
        for rule, status in (pin.get("rules") or {}).items()
        if status != "PASS"
    }
    items |= {
        ("unknown", str(rule), str(kind)) for rule, kind in (pin.get("unknown") or {}).items()
    }
    return items


def stale(pin: dict[str, Any], listed: dict[str, Any]) -> list[dict[str, Any]]:
    """The growth entries whose finding the pin no longer holds (AD-733)."""
    live = tokens(pin)
    gaps = Counter(("gap", *map(str, gap)) for gap in pin.get("gaps") or ())
    gone = []
    for item in listed.get("raised") or ():
        entry = tuple(map(str, item.get("entry") or ()))
        if entry not in live or (entry[0] == "gap" and gaps[entry] == 0):
            gone.append(item)
        elif entry[0] == "gap":
            gaps[entry] -= 1
    return gone


def unlisted(
    grown: list[list[str]], listed: dict[str, Any], previous: dict[str, Any] | None = None
) -> list[str]:
    """The grown items that the growth file lists without a reason or does not list at all."""
    reasons = Counter(
        tuple(map(str, item.get("entry") or ()))
        for item in listed.get("raised") or ()
        if len(str(item.get("reason") or "").strip()) >= 10
    )
    old_reasons = Counter(
        tuple(map(str, item.get("entry") or ()))
        for item in (previous or {}).get("raised") or ()
        if len(str(item.get("reason") or "").strip()) >= 10
    )
    for entry, count in old_reasons.items():
        if entry and entry[0] == "gap":
            reasons[entry] = max(0, reasons[entry] - count)
    missing = []
    for item in grown:
        entry = tuple(item)
        if reasons[entry] == 0:
            missing.append(f"growth without a reason in the growth file: {item}")
        else:
            reasons[entry] -= 1
    return missing


def _fork_point(ref: str) -> str:
    """The merge base of `ref` and HEAD: what this branch started from (AD-733).

    A branch that is behind main (non-strict protection) must not read main's later changes of a
    pin as its own shrinking or growth.
    """
    done = subprocess.run(["git", "merge-base", ref, "HEAD"], capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 and done.stdout.strip() else ref


def _git_show(ref: str, path: Path) -> dict[str, Any] | None:
    if path.is_absolute():
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
        )
        if root.returncode != 0 or not path.is_relative_to(Path(root.stdout.strip())):
            return None
        path = path.relative_to(Path(root.stdout.strip()))
    shown = subprocess.run(
        ["git", "show", f"{ref}:{path.as_posix()}"], capture_output=True, text=True, check=False
    )
    return json.loads(shown.stdout) if shown.returncode == 0 else None


def _option(argv: list[str], name: str) -> str | None:
    return argv[argv.index(name) + 1] if name in argv else None


def main(argv: list[str]) -> int:
    result = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    path = Path(argv[1])
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    growth_path = Path(_option(argv, "--growth") or "")
    listed = json.loads(growth_path.read_text(encoding="utf-8")) if growth_path.is_file() else {}
    base = _option(argv, "--base-ref")
    if "--write" in argv:
        if "refusal" in result:
            print(f"refused: {result['refusal']}", file=sys.stderr)
            return 1
        new = written(result, old)
        grown = growth(new, old)
        gap_growth = [item for item in grown if item[0] == "gap"]
        previous: dict[str, Any] = {}
        if gap_growth:
            ref = _fork_point(base) if base else None
            before = _git_show(ref, path) if ref else None
            prior = _git_show(ref, growth_path) if ref and growth_path.is_file() else None
            if before is None or prior is None:
                print(
                    "--write refused: provide --base-ref with committed pin and growth files",
                    file=sys.stderr,
                )
                return 1
            old_gaps = Counter(tuple(gap) for gap in old.get("gaps") or ())
            base_gaps = Counter(tuple(gap) for gap in before.get("gaps") or ())
            if any(old_gaps[tuple(item[1:])] != base_gaps[tuple(item[1:])] for item in gap_growth):
                print(
                    "--write refused: commit the intermediate pin and use it as --base-ref",
                    file=sys.stderr,
                )
                return 1
            previous = prior
        refused = unlisted(grown, listed, previous)
        for line in refused:
            print(line, file=sys.stderr)
        if refused:
            print(
                "--write refused: add each item with a reason to the growth file", file=sys.stderr
            )
            return 1
        path.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
        if growth_path.is_file() and (gone := stale(new, listed)):
            kept = list(listed["raised"])
            for item in gone:
                kept.remove(item)
            growth_path.write_text(
                json.dumps({**listed, "raised": kept}, indent=2) + "\n", encoding="utf-8"
            )
            print(f"dropped {len(gone)} stale growth entries from {growth_path}", file=sys.stderr)
        return 0
    found = problems(result, old)
    gaps_seen, _statuses, _violations = observed(result)
    pinned = Counter((str(k), str(sub), str(why)) for k, sub, why in old.get("gaps") or ())
    hint = receiver_gap_hint(result, sorted((Counter(gaps_seen) - pinned).elements()))
    if hint:
        found.append(hint)
    found += [
        f"stale growth entry (its finding is gone; run --write): {i['entry']}"
        for i in stale(old, listed)
    ]
    if base:
        ref = _fork_point(base)
        if (before := _git_show(ref, path)) is None:
            print(f"ratchet: base {base} unavailable, skipped", file=sys.stderr)
        else:
            grown = growth(old, before)
            prior = _git_show(ref, growth_path) if growth_path.is_file() else None
            if prior is None and any(item[0] == "gap" for item in grown):
                found.append(
                    "ratchet: base growth file unavailable; provide a committed growth file"
                )
            else:
                found += unlisted(grown, listed, prior)
    for line in found:
        print(line, file=sys.stderr)
    print(summary(result, str(old.get("name", "native"))))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
