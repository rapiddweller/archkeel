# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Which files the 500-line limit covers, and how a file is measured (AD-314).

`tools/self_check_summary.py` shows the measurement; no test fails on size. This file is the
one place that says which files count.
"""

from pathlib import Path

MAX_FILE_LINES = 500
SIZE_LIMIT_EXEMPT: dict[str, str] = {
    "native/report/assets/explorer/elkjs-0.12.0.bundled.js": "vendored ELK release, not our code",
    "native/report/assets/explorer/flow.runtime.js": "generated from the parts of flow/",
}
# The scripts and styles of the report page are code too (lead L-283).
REPORT_ASSETS = "native/report/assets/"
SCRIPT_SUFFIXES = (".py", ".cjs", ".mjs", ".js")


def is_size_limited(relative: str) -> bool:
    top, _, rest = relative.partition("/")
    if relative in SIZE_LIMIT_EXEMPT:
        return False
    if top == "src" or relative.startswith("studio/src/"):
        return relative.endswith((*SCRIPT_SUFFIXES, ".ts", ".tsx", ".css"))
    if relative.startswith(REPORT_ASSETS):
        return relative.endswith((".js", ".css"))
    if top in {"native", "crates"}:
        return relative.endswith(".rs")
    if relative.startswith("tools/rustc-facts/"):
        return relative.endswith(".rs")
    if top == "tools":
        return relative.endswith(SCRIPT_SUFFIXES) and "/node_modules/" not in relative
    # Test modules and fixture helpers are code. Golden data and fixture sources are inputs.
    return top in {"tests", "fixtures"} and "/" not in rest and relative.endswith(SCRIPT_SUFFIXES)


def line_count(path: Path) -> int:
    """Lines as `splitlines()` counts them, so U+2028 and other Unicode breaks count as breaks."""
    return len(path.read_text(encoding="utf-8").splitlines())
