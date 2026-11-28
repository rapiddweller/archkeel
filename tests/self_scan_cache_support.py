# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A fake `rustc` and `cargo` for the tests of `tools/self_scan_cache.py` (AD-1450).

The key holds the output of `rustc -Vv` and `cargo -V`. The fakes make the tests run without a
Rust toolchain: the text of `rustc.txt` is the version, and a file `fail` makes both tools fail.
"""

from __future__ import annotations

import os
from pathlib import Path

SCRIPT = (
    '#!/bin/sh\nd="$(dirname "$0")"\n[ -f "$d/fail" ] && exit 1\ncat "$d/$(basename "$0").txt"\n'
)


def fake_toolchain(directory: Path) -> dict[str, str]:
    """The environment with the fake tools first in PATH."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in (("rustc", "rustc 1.97.0 fake\n"), ("cargo", "cargo 1.97.0 fake\n")):
        tool = directory / name
        tool.write_text(SCRIPT)
        tool.chmod(0o755)
        version = directory / f"{name}.txt"
        if not version.exists():
            version.write_text(text)
    return {**os.environ, "PATH": f"{directory}{os.pathsep}{os.environ['PATH']}"}
