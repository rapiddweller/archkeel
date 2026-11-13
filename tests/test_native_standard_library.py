# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-388: the core pins the standard library of each profile.

The Python list is `sys.stdlib_module_names` of each supported minor. CPython defines that set
to be the same on each platform, so the list of the running interpreter must equal it here and on
each CI runner.
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "native" / "store" / "src" / "standard_library.txt"
PYTHON = "archkeel-python-analyzer"


def _minor() -> str:
    """The minor version of the running interpreter, such as `3.11`."""
    major, minor, _ = platform.python_version_tuple()
    return f"{major}.{minor}"


def _pinned(owner: str) -> set[str]:
    rows = (line.split(" ") for line in TABLE.read_text(encoding="utf-8").splitlines())
    return {name for row_owner, name in rows if row_owner == owner}


def test_the_pinned_list_is_the_standard_library_of_the_running_interpreter() -> None:
    assert _pinned(f"{PYTHON}@{_minor()}") == set(sys.stdlib_module_names)
