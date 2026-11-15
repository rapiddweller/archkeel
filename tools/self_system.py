# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Print the verdict of ArchKeel as one system: its Python shell and its Rust core.

`make self-validate` runs one contract for each part (AD-478: one scan has one language). This tool
reads the two result files and prints one line for the system, then one line for each part. The
verdict of the system is the weakest verdict of the parts (FAIL, then UNKNOWN, then PASS).

Run: `python tools/self_system.py TITLE=result.json [TITLE=result.json ...]`. The exit code is 0:
the pinned result of each part is the gate (`tools/native_expected.py`), not this line.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path

from tools.report_product import STATUSES, contract_of, system_line


def main(argv: Sequence[str]) -> int:
    parts = []
    for argument in argv:
        title, _, path = argument.partition("=")
        try:
            envelope = json.loads(Path(path).read_text())
            parts.append(contract_of(envelope, title))
        except (OSError, ValueError) as err:
            parts.append(contract_of(None, title, f"{type(err).__name__}: {err}"[:200]))
    print(
        system_line([part.status for part in parts], [part.counts for part in parts if part.status])
    )
    for part in parts:
        if part.status:
            words = ", ".join(f"{part.counts[name]} {name}" for name in STATUSES)
            print(f"  {part.title}: {part.status}: {words}")
        else:
            print(f"  {part.title}: no result: {part.error}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
