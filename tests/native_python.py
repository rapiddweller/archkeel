# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Native Python dump helpers that do not import the deleted comparison oracle."""

import json
import subprocess
import sysconfig
from pathlib import Path
from typing import Any


def _minor() -> int:
    """The minor version of the interpreter that runs the tests."""
    return int(sysconfig.get_python_version().split(".")[1])


def _native(binary: Path, root: Path, rels: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        [str(binary), "--dump", str(_minor()), str(root)],
        input="".join(f"{rel}\n" for rel in rels),
        capture_output=True,
        text=True,
        check=True,
    )
    # JSON retains U+2028 and U+0085; splitlines would split inside a JSON string.
    rows = [json.loads(line) for line in completed.stdout.split("\n") if line]
    return {row["file"]: row["outcome"] for row in rows}


def _write(root: Path, cases: dict[str, str | bytes]) -> list[str]:
    for name, text in cases.items():
        data = text.encode("utf-8") if isinstance(text, str) else text
        (root / name).write_bytes(data)
    return sorted(cases)
