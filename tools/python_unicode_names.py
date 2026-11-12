# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Write the unassigned Unicode ranges of each supported CPython for named escape checks."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = """
import unicodedata
ranges = []
start = previous = -2
for point in [p for p in range(0x110000) if unicodedata.category(chr(p)) == 'Cn'] + [-1]:
    if point != previous + 1:
        if start >= 0:
            ranges.append(f'{start:X}-{previous:X}')
        start = point
    previous = point
print(' '.join(ranges))
"""


def main() -> None:
    rows = []
    for minor in (11, 12, 13, 14):
        result = subprocess.run(
            ["uv", "run", "--no-project", "--python", f"3.{minor}", "python", "-I", "-c", SCRIPT],
            capture_output=True,
            text=True,
            check=True,
        )
        rows.append(result.stdout.strip())
    (ROOT / "native/python/src/unassigned.txt").write_text("\n".join(rows) + "\n")


if __name__ == "__main__":
    main()
