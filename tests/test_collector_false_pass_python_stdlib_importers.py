# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1969, #1970, AD-1059: the standard library imports by a string or hands out a code object.

Consumer: `archkeel validate`. `app.consumer` may not depend on `app.lib`. Each plant imports
`app.lib` under CPython 3.12 (the test asserts it), so the rule must be UNKNOWN or FAIL, never PASS.
A control has the same shape without the hazard: CPython leaves `app.lib` unloaded and the rule is
PASS. A project function or method with the name of a standard library importer is a control.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from python_stdlib_importer_plants import CONTROLS, P
from test_collector_false_pass_python_trojan_attribute import _loads_lib, _root, _verdict

pytestmark = pytest.mark.skipif(shutil.which("python3.12") is None, reason="Python is the oracle")


@pytest.mark.parametrize("name", sorted(P))
def test_a_string_importer_of_the_standard_library_is_never_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _root(tmp_path, P[name])
    assert _loads_lib(root), "CPython must import app.lib: the plant is real"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame


@pytest.mark.parametrize("name", sorted(CONTROLS))
def test_the_same_names_on_a_project_object_or_without_a_module_name_stay_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    root = _root(tmp_path, CONTROLS[name])
    assert not _loads_lib(root), "CPython must leave app.lib unloaded: the control is clean"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] == "PASS", frame
