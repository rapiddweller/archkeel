# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The 40-line text of `make self-check` for an agent that changes ArchKeel (AD-1088).

Run: `python tools/self_check_summary.py --status <make exit code> --log <file> [--dir D]
[--root R]`. `make self-check` calls it after `make self-validate`. It reads the results of that
run and runs no checker. Each group ends with one `next:` line. The groups `size`, `hotspots`
and `cycles` are measurements: they never change the exit code. The exit code of the make target
is the one of `make self-validate`, which owns the ratchet against the base commit.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from file_size import MAX_FILE_LINES, is_size_limited, line_count
from self_check_diff import Unusable, condense, grown, load, one
from self_check_gate import scan_table

from archkeel.cli.core_exit import EXIT_TABLE
from archkeel.cli.core_frame import Status
from archkeel.cli.core_words import plain

MAX_LINES = 40
LISTED = 5
AT_LIMIT_LISTED = 30
# A frame lists its rules as [kind, status]. This kind is the only rule kind that finds cycles.
CYCLE_KIND = "no_component_cycles"
NEAR_LIMIT = MAX_FILE_LINES * 9 // 10
EXIT_OF = {word: code for code, (word, _) in EXIT_TABLE.items()}
BASELINE = "tests/file_size_baseline.json"
# The three checks, the folder of each result, and whether `archkeel report --json` wraps the frame.
PARTS = (
    ("native", "validation-native", True),
    ("shell", "validation-shell", True),
    ("system", "validation-system", False),
)


def read(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} is not a result object")
    return document


def frame_of(document: dict[str, Any], wrapped: bool) -> dict[str, Any]:
    """The frame of a result: `archkeel report --json` wraps it, `--output` writes it bare."""
    found = document.get("frame", {}) if wrapped else document
    return found if isinstance(found, dict) else {}


def verdict(name: str, document: dict[str, Any] | None, wrapped: bool) -> str:
    if document is None:
        return f"{name} has no result"
    if refusal := document.get("refusal"):
        return f"{name} REFUSED ({one(refusal.get('kind'))})"
    status = str(frame_of(document, wrapped).get("status"))
    return f"{name} {status} (exit {EXIT_OF.get(status, '?')})"


def where(frame: dict[str, Any], evidence: list[str], fallback: str = "?") -> str:
    place = (frame.get("locations") or {}).get(evidence[0]) if evidence else None
    return f"{place['path']}:{place['line']}" if place else fallback


def ratchet(
    native: dict[str, Any] | None, base: Path, root: Path = Path("."), kept: Path | None = None
) -> tuple[list[str], int]:
    """The growth against the base commit in words, and the count of new items."""
    if native is None or native.get("refusal"):
        return ["native vs base: no native result"], 0
    try:
        before = load(str(base))
    except Unusable:
        return ["native vs base: no base result; run `make self-validate-native`"], 0
    try:
        own = load(str(kept)) if kept is not None else condense(native, scan=scan_table(root))
    except Unusable:
        return ["native vs base: no gate result; run `make self-validate-native`"], 0
    _lines, gaps, blocking, removed = grown(before, own)
    items = [*blocking, *gaps]
    sha = str(before.get("sha") or "?")[:12]
    lines = [f"native vs base {sha}: {len(items)} new items, {removed} gaps gone"]
    lines += [f"  new: {item[0]}" for item in items[:3]]
    if len(items) > 3:
        lines.append(f"  and {len(items) - 3} more in test-artifacts/selfcheck/grown.txt")
    return lines, len(items)


def violations(frames: dict[str, dict[str, Any]]) -> tuple[list[str], int]:
    rows = [
        f"{rule}: {one(row['source'])} -> {one(row['target'])} ({where(frame, row['evidence'])})"
        for frame in frames.values()
        for rule, found in (frame.get("details") or {}).items()
        for row in found
    ]
    lines = [f"new violations: {len(rows)} (the base has none)"] + [f"  {row}" for row in rows[:4]]
    if len(rows) > 4:
        lines.append(f"  and {len(rows) - 4} more")
    return lines, len(rows)


def unknown_causes(frames: dict[str, dict[str, Any]]) -> list[str]:
    """The causes of the collection gaps, the largest first: what keeps rules at UNKNOWN."""
    causes: dict[str, list[str]] = {}
    waiting = 0
    for frame in frames.values():
        waiting += len(frame.get("explained") or {})
        for gap in frame.get("collection_gaps") or ():
            cause = plain(gap["reason"]).split(": ", 1)[0]
            causes.setdefault(cause, []).append(where(frame, gap["evidence"], gap["subjects"][0]))
    ranked = sorted(causes.items(), key=lambda item: (-len(item[1]), item[0]))
    total = sum(len(places) for places in causes.values())
    lines = [
        f"unknown causes (measured, gaps per cause; top {min(LISTED, len(ranked))} of "
        f"{len(ranked)} causes, {total} gaps; {waiting} rules wait):"
    ]
    lines += [
        f"  {len(places)} x {one(cause)} (first: {places[0]})" for cause, places in ranked[:LISTED]
    ]
    lines.append(
        "  next: open the first place of the top cause. A new cause is growth against the base."
        if ranked
        else "  next: none, no gap in the scan."
    )
    return lines


def sizes(root: Path) -> list[str]:
    """Files over the limit that the baseline does not hold, and files within 10 % of it."""
    names = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--deduplicate", "-z"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    held = json.loads((root / BASELINE).read_text(encoding="utf-8"))
    counted = {n: line_count(root / n) for n in names if n and is_size_limited(n)}
    over = sorted((n for n, k in counted.items() if k > MAX_FILE_LINES and n not in held), key=str)
    near = [n for n, k in counted.items() if NEAR_LIMIT <= k <= MAX_FILE_LINES]
    full = sorted(n for n in near if counted[n] == MAX_FILE_LINES)
    lines = [
        f"size (measured, limit {MAX_FILE_LINES}): {len(over)} files over it, not in the baseline"
    ]
    lines += [f"  over: {name} ({counted[name]} lines)" for name in over[:3]]
    if len(over) > 3:
        lines.append(f"  and {len(over) - 3} more")
    named = ", ".join(full[:AT_LIMIT_LISTED]) or "none"
    more = f" and {len(full) - AT_LIMIT_LISTED} more" if len(full) > AT_LIMIT_LISTED else ""
    lines.append(
        f"  {len(near)} files at {NEAR_LIMIT} to {MAX_FILE_LINES} lines; "
        f"{len(full)} at {MAX_FILE_LINES}: {named}{more}"
    )
    lines.append(
        "  next: split each file over the limit at a responsibility seam; never raise the baseline."
        if over
        else "  next: a file at the limit has no room: split it by responsibility before it grows."
    )
    return lines


def top(counter: Counter[str]) -> str:
    return ", ".join(f"{name} {count}" for name, count in counter.most_common(LISTED)) or "none"


def hotspots(frames: dict[str, dict[str, Any]]) -> list[str]:
    """The modules with the most importers and the most imports, over the topology edges."""
    lines = ["hotspots (measured, scanned modules, import edges only):"]
    for name, frame in frames.items():
        topology = frame.get("topology")
        if not topology:
            continue
        scanned = {module["name"] for module in topology["modules"]}
        fan_in: Counter[str] = Counter()
        fan_out: Counter[str] = Counter()
        for edge in topology["edges"]:
            if (
                edge["source"] in scanned
                and edge["target"] in scanned
                and edge["source"] != edge["target"]
            ):
                fan_out[edge["source"]] += 1
                fan_in[edge["target"]] += 1
        partial = len(topology["edges"]) < topology["total"]["edges"]
        lines.append(f"  {name} fan-in: {top(fan_in)}{' (partial)' if partial else ''}")
        lines.append(f"  {name} fan-out: {top(fan_out)}")
    lines.append(
        "  next: a top module touches many others; look at it before you add an import to it."
    )
    return lines


def cycles(frames: dict[str, dict[str, Any]]) -> list[str]:
    found: list[str] = []
    waiting: list[str] = []
    decided = 0
    for name, frame in frames.items():
        for rule, (kind, status) in (frame.get("rules") or {}).items():
            if kind == CYCLE_KIND:
                decided += status != Status.UNKNOWN
                if status == Status.UNKNOWN:
                    waiting.append(rule)
        for rule, listed in (frame.get("explain", {}).get("cycles") or {}).items():
            found += [f"{name} {rule}: {len(item['members'])} members" for item in listed["items"]]
    lines = [
        f"cycles (verdict of {CYCLE_KIND}): {len(found)} found; {decided} rules decide"
        f"; {len(waiting)} wait"
    ]
    lines += [f"  cycle: {row}" for row in found[:3]]
    lines.append(
        "  next: break each cycle at its weakest import."
        if found
        else f"  next: none; {', '.join(waiting[:2])} still waits."
        if waiting
        else "  next: none."
    )
    return lines


def summary(dir_: Path, root: Path, status: int, log: str) -> list[str]:
    results: dict[str, dict[str, Any] | None] = {}
    for name, part, _wrapped in PARTS:
        try:
            results[name] = read(dir_ / part / "result.json")
        except (OSError, ValueError):
            results[name] = None
    frames = {
        name: frame_of(results[name] or {}, True) for name, _part, wrapped in PARTS if wrapped
    }
    frames = {name: frame for name, frame in frames.items() if frame}
    compared = dir_ / "selfcheck" / "compared-base.json"
    base = compared if compared.is_file() else Path(os.environ.get("BASE_RESULT") or compared)
    kept = dir_ / "selfcheck" / "result.json"
    ratchet_lines, new = ratchet(results["native"], base, root, kept if kept.is_file() else None)
    violation_lines, found = violations(frames)
    lines = ["self-check: " + " | ".join(verdict(n, results[n], w) for n, _p, w in PARTS)]
    lines += ratchet_lines
    lines.append(
        "  next: remove each new item before you push; the gate fails on it."
        if new
        else "  next: nothing new against the base."
    )
    lines += violation_lines
    lines.append(
        "  next: fix each violation; it has no approval path." if found else "  next: none."
    )
    lines += unknown_causes(frames)
    lines += sizes(root)
    lines += hotspots(frames)
    lines += cycles(frames)
    lines.append(f"self-validate exit {status} (the gate); full output: {log}")
    return lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", type=int, required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--dir", type=Path, default=Path("test-artifacts"))
    parser.add_argument("--root", type=Path, default=Path("."))
    given = parser.parse_args(argv)
    print("\n".join(summary(given.dir, given.root, given.status, given.log)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
