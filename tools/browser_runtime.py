# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Generate or check the Explorer's Flow runtime from its parts (issue 1723).

The Explorer source is the folder `explorer/flow/`: one file for each responsibility. The parts
share one closure, so the runtime joins them in the order of `PARTS` inside one function: the
page keeps one script and one hash. A part holds its function declarations and the statements of
its responsibility; a statement that runs at load keeps its place in this order.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "native/report/assets/explorer"
TOOLS = ROOT / "tools/browser-runtime"


PARTS = (
    "boot",
    "uml",
    "route",
    "permissions",
    "canvas",
    "sheets",
    "explore",
    "navigate",
    "levels",
    "state",
    "start",
)
HEAD = (
    b'"use strict";\n'
    b"// One report model, scene projection and UML renderer for every architecture view.\n"
)


def source() -> bytes:
    """The source of the runtime: the parts of `flow/` in order, inside one function."""
    parts = b"\n".join((ASSETS / "flow" / f"{part}.js").read_bytes() for part in PARTS)
    return HEAD + b"(function () {\n" + parts + b"})();\n"


def runtime(source: bytes) -> bytes:
    """Return the reproducible minified runtime and its source digest."""
    result = subprocess.run(
        [
            "node",
            str(TOOLS / "node_modules/terser/bin/terser"),
            "--config-file",
            str(TOOLS / "options.json"),
        ],
        input=source,
        capture_output=True,
        check=True,
    )
    footer = (
        f"// Generated from flow/; source-sha256={hashlib.sha256(source).hexdigest()}\n"
        "// Owner: tools/browser_runtime.py. Edit a part of flow/; make browser-runtime-generate.\n"
    )
    return result.stdout + b"\n" + footer.encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = ASSETS / "flow.runtime.js"
    generated = runtime(source())
    if args.check:
        if path.read_bytes() != generated:
            raise SystemExit("flow.runtime.js is stale; run python tools/browser_runtime.py")
    else:
        path.write_bytes(generated)


if __name__ == "__main__":
    main()
