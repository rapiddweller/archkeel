# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Record the golden replies of a language (AD-343): `make golden-record`.

The recorder runs the current Python collector and writes the golden file of each case. It adds
one line to `RECORDINGS.md` with the date, the case, the commit and the reason. It refuses to run
without a reason: a changed golden reply is a deliberate decision.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import golden_producers
import golden_replies

ROOT = Path(__file__).parents[1]
LOG_HEAD = "| Date | Case | Commit | Reason |\n|---|---|---|---|\n"


def cases(language: str) -> dict[str, Path]:
    listing = json.loads((golden_replies.GOLDEN / language / "cases.json").read_text())
    return {item["case"]: ROOT / item["root"] for item in listing}


def record(language: str, names: list[str], reason: str) -> list[Path]:
    if not reason.strip():
        raise golden_replies.GoldenError("REASON is required: say why the golden reply changes")
    known = cases(language)
    if unknown := [name for name in names if name not in known]:
        raise golden_replies.GoldenError(f"unknown case {unknown}; known cases: {sorted(known)}")
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    run = golden_producers.producer("python")
    replies = {}
    for name in names:
        with tempfile.TemporaryDirectory() as workspace:
            root = golden_producers.materialize(known[name], Path(workspace))
            replies[name] = golden_replies.canonical(run(root), root)
    written = [golden_replies.store(language, name, reply) for name, reply in replies.items()]
    today = datetime.now(UTC).date()
    lines = [f"| {today} | {name} | {commit} | {reason.strip()} |\n" for name in replies]
    log = golden_replies.GOLDEN / language / "RECORDINGS.md"
    log.write_text((log.read_text() if log.exists() else LOG_HEAD) + "".join(lines))
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", required=True)
    parser.add_argument("--case", required=True, help="a case name, or `all`")
    parser.add_argument("--reason", default="", help="why the golden reply changes")
    args = parser.parse_args()
    try:
        names = list(cases(args.language)) if args.case == "all" else [args.case]
        for path in record(args.language, names, args.reason):
            print(f"recorded {path.relative_to(ROOT)}")
    except golden_replies.GoldenError as error:
        print(f"golden-record: {error}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
