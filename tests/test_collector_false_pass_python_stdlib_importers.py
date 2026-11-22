# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1970: the standard library imports a module that a string names, under CPython 3.12.

Each plant imports `app.lib`. A plant that the collector reads gives UNKNOWN. The four plants that
give PASS are strict expected failures: when a fix lands, the strict marker fails the run, and the
person who fixes it removes the marker and the entry of `docs/known-limits.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from python_stdlib_importer_plants import P
from test_collector_false_pass_python_trojan_attribute import _loads_lib, _root, _verdict

OPEN = {
    "logging.config '()' handler",
    "logging.config 'class' handler",
    "logging.config '()' formatter",
    "unittest loadTestsFromName",
}


@pytest.mark.parametrize(
    "name",
    [
        pytest.param(name, marks=pytest.mark.xfail(strict=True, reason="#1970"))
        if name in OPEN
        else name
        for name in sorted(P)
    ],
)
def test_a_string_importer_of_the_standard_library_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _root(tmp_path, P[name])
    assert _loads_lib(root), "CPython must import app.lib: the plant is real"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame
