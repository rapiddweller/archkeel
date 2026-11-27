# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The index of the decision records, generated from the records themselves (AD-752).

`python tools/decision_index.py` prints the index: one row for each `ad-<n>-*.md` file, with the
number from the file name, the title from the first heading and a link, sorted by number with the
newest first. `--write PATH` writes it. No check fails on it (AD-1300). The list is not committed:
a pull request that adds a record adds one file and no line of a shared index, so two such pull
requests never conflict. `docs/architecture/decisions/INDEX.md` keeps the hand-written list as it
was on 2026-11-17.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FOLDER = Path(__file__).resolve().parents[1] / "docs/architecture/decisions"
NAME = re.compile(r"^ad-(\d+[a-z]?)-.+\.md$")
HEADING = re.compile(r"^#\s+(?:AD-\S+?[:.]?\s+)?(.+?)\s*$")


def label_of(identifier: str) -> str:
    """The number of a file name without leading zeros: `01` is 1, `24a` stays `24a`."""
    return re.sub(r"^0+(?=\d)", "", identifier)


def sort_key(label: str) -> tuple[int, str]:
    number = re.match(r"\d+", label)
    return (int(number.group(0)) if number else 0, label)


def records(folder: Path = FOLDER) -> list[tuple[str, str, str]]:
    """(label, title, file name) of each record, newest number first."""
    found = []
    for path in folder.glob("ad-*.md"):
        match = NAME.match(path.name)
        if match is None:
            continue
        first = next(
            (
                line
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.startswith("# ")
            ),
            "",
        )
        heading = HEADING.match(first)
        title = heading.group(1).rstrip(".") if heading else path.stem
        found.append((label_of(match.group(1)), title, path.name))
    return sorted(found, key=lambda row: (sort_key(row[0]), row[2]), reverse=True)


def table(rows: list[tuple[str, str, str]]) -> str:
    lines = ["| Decision | Title |", "|---|---|"]
    lines += [f"| AD-{label} | [{title}]({name}) |" for label, title, name in rows]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    text = table(records())
    if "--write" in argv:
        Path(argv[argv.index("--write") + 1]).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
