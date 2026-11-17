# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Print the test areas that a change selects (AD-674, AD-736).

`python tools/select_areas.py <base-ref>` reads `git diff --name-only --no-renames
<base-ref>...HEAD` (a rename lists the old and the new path), applies `tests/areas.py` and prints
one `--area '<name>'` option for each selected area, ready for pytest.
A change without files selects the area `self-check and CI`, so the selection is never empty.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from areas import areas_of_change  # noqa: E402


def changed(base: str) -> list[str]:
    done = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in done.stdout.splitlines() if line]


def main(argv: list[str]) -> int:
    areas = areas_of_change(changed(argv[0])) or ["self-check and CI"]
    print(" ".join(f"--area {shlex.quote(area)}" for area in areas))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
