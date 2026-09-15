# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Extract every fenced ```mermaid``` block from tracked Markdown files.

Single source of truth for both the label test (tests/test_mermaid.py) and the CI
render step, so neither can drift from what the other considers "every block".
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FENCE_OPEN = "```mermaid"
FENCE_CLOSE = "```"


def blocks(root: Path = ROOT) -> list[tuple[str, int, str]]:
    """Return `(repo-relative path, start line, block text)` for every Mermaid block.

    `start line` is the 1-based line of the ` ```mermaid ` fence itself; block text
    starts on the following line.
    """
    paths = subprocess.check_output(["git", "ls-files", "*.md"], cwd=root, text=True).splitlines()
    found: list[tuple[str, int, str]] = []
    for path in paths:
        lines = (root / path).read_text(encoding="utf-8").splitlines()
        in_block = False
        start = 0
        current: list[str] = []
        for number, line in enumerate(lines, start=1):
            if not in_block:
                if line.strip() == FENCE_OPEN:
                    in_block, start, current = True, number, []
                continue
            if line.strip() == FENCE_CLOSE:
                found.append((path, start, "\n".join(current)))
                in_block = False
                continue
            current.append(line)
        if in_block:
            raise ValueError(f"{path}:{start}: unterminated mermaid block")
    return found


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Extract Mermaid blocks for rendering.")
    parser.add_argument(
        "--write", type=Path, required=True, help="directory to write <n>.mmd and index.txt into"
    )
    args = parser.parse_args(argv)
    args.write.mkdir(parents=True, exist_ok=True)
    index_lines = []
    for number, (path, line, text) in enumerate(blocks(), start=1):
        (args.write / f"{number}.mmd").write_text(text + "\n", encoding="utf-8")
        index_lines.append(f"{number}\t{path}:{line}")
        print(f"{number}.mmd\t{path}:{line}")
    (args.write / "index.txt").write_text("\n".join(index_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
