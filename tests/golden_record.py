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


def options(language: str, case: str) -> dict[str, object]:
    """The settings of a case beyond its root. A Python case can set the three that follow."""
    listing = json.loads((golden_replies.GOLDEN / language / "cases.json").read_text())
    item = next(item for item in listing if item["case"] == case)
    return {key: item[key] for key in ("phase", "features", "exclude_tests") if key in item}


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout.rstrip("\n")


def changed_sources(root: Path, paths: list[str]) -> list[str]:
    """The files under `paths` that differ from HEAD, tracked or not: the real source of a reply."""
    lines = git(root, "status", "--porcelain", "--untracked-files=all", "--", *paths).splitlines()
    return [line[3:] for line in lines]


def record(
    language: str, names: list[str], reason: str, *, allow_dirty: bool = False
) -> list[Path]:
    if not reason.strip():
        raise golden_replies.GoldenError("REASON is required: say why the golden reply changes")
    if language == "typescript":
        raise golden_replies.GoldenError(
            "typescript_oracle_retired: the Python TypeScript recordings cannot be regenerated"
        )
    known = cases(language)
    if unknown := [name for name in names if name not in known]:
        raise golden_replies.GoldenError(f"unknown case {unknown}; known cases: {sorted(known)}")
    # The reply comes from the collector (src) and the case folders. The log names their commit.
    sources = ["src", *(str(known[name].relative_to(ROOT)) for name in names)]
    commit = git(ROOT, "rev-parse", "--short", "HEAD").strip()
    if changed := changed_sources(ROOT, sources):
        if not allow_dirty:
            raise golden_replies.GoldenError(
                f"the source is not committed: {changed[:5]}. Commit it, or set ALLOW_DIRTY=1"
            )
        commit += "+dirty"
    replies = {}
    for name in names:
        run = golden_producers.producer("python", language=language, **options(language, name))
        with tempfile.TemporaryDirectory() as workspace:
            root = golden_producers.materialize(known[name], Path(workspace))
            replies[name] = golden_replies.canonical(run(root), root)
    pin = golden_replies.pin_for(language)
    if pin and not golden_replies.same_interpreter(pin.recorded) and set(names) != set(known):
        raise golden_replies.GoldenError(
            f"the other golden replies were recorded with {pin.recorded['version']}: "
            "record CASE=all, so that one interpreter made all of them"
        )
    written = [golden_replies.store(language, name, reply) for name, reply in replies.items()]
    if pin:
        write_pin(language)
    today = datetime.now(UTC).date()
    runtime = golden_replies.interpreter()
    why = f"{reason.strip()} ({runtime['implementation']} {runtime['version']})"
    lines = [f"| {today} | {name} | {commit} | {why} |\n" for name in replies]
    log = golden_replies.GOLDEN / language / "RECORDINGS.md"
    log.write_text((log.read_text() if log.exists() else LOG_HEAD) + "".join(lines))
    return written


def write_pin(language: str) -> None:
    """Name the interpreter of this recording in `interpreter.json`. The bound parts stay."""
    path = golden_replies.GOLDEN / language / golden_replies.PIN_FILE
    table = json.loads(path.read_text())
    table["recorded_with"] = golden_replies.interpreter()
    path.write_text(json.dumps(table, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", default="")
    parser.add_argument("--case", default="", help="a case name, or `all`")
    parser.add_argument("--reason", default="", help="why the golden reply changes")
    parser.add_argument("--allow-dirty", action="store_true", help="log the commit as +dirty")
    args = parser.parse_args(argv)
    try:
        if not args.language or not args.case:
            raise golden_replies.GoldenError(
                "LANGUAGE and CASE are required: make golden-record LANGUAGE=<language> "
                "CASE=<case|all> REASON=<why>"
            )
        if not (golden_replies.GOLDEN / args.language / "cases.json").is_file():
            raise golden_replies.GoldenError(f"no cases for language {args.language!r}")
        names = list(cases(args.language)) if args.case == "all" else [args.case]
        for path in record(args.language, names, args.reason, allow_dirty=args.allow_dirty):
            print(f"recorded {path.relative_to(ROOT)}")
    except golden_replies.GoldenError as error:
        print(f"golden-record: {error}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
