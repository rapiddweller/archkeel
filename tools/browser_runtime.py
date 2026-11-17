# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Generate or check the Explorer's Flow runtime from its source."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "native/report/assets/explorer"
TOOLS = ROOT / "tools/browser-runtime"


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
        f"// Generated from flow.js; source-sha256={hashlib.sha256(source).hexdigest()}\n"
        "// Owner: tools/browser_runtime.py. Edit flow.js; make browser-runtime-generate.\n"
        "// Check: tests/test_report_generated_assets.py\n"
    )
    return result.stdout + b"\n" + footer.encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = ASSETS / "flow.runtime.js"
    generated = runtime((ASSETS / "flow.js").read_bytes())
    if args.check:
        if path.read_bytes() != generated:
            raise SystemExit("flow.runtime.js is stale; run python tools/browser_runtime.py")
    else:
        path.write_bytes(generated)


if __name__ == "__main__":
    main()
