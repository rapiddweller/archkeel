# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2109, AD-1172: a rename of a re-exported name is followed to a fixpoint.

`app.util` holds `import cProfile as cp`. Each module renames the name of the module before it
(`from app.m1 import q1 as q2`) and the consumer calls `run` on the last name. CPython 3.12 imports
`app.lib` (the test asserts it), so `NO-LIB` must be UNKNOWN or FAIL. The control renames a number.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from python_stdlib_importer_plants import quiet
from test_collector_false_pass_python_trojan_attribute import _loads_lib, _root, _verdict

pytestmark = pytest.mark.skipif(shutil.which("python3.12") is None, reason="Python is the oracle")


def chain(hops: int, first: str) -> tuple[str, dict[str, str]]:
    """The consumer source and the modules of a rename chain of `hops` renames."""
    files = {"util": "import cProfile as cp\n\nvalue = 1\n"}
    before = ("util", first)
    for hop in range(1, hops + 1):
        name = f"q{hop}"
        files[f"m{hop}"] = f"from app.{before[0]} import {before[1]} as {name}\n"
        before = (f"m{hop}", name)
    return quiet(
        f"from app.{before[0]} import {before[1]}\n", f"{before[1]}.run('import app.lib')"
    ), files


def _run(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, hops: int, first: str
):
    source, files = chain(hops, first)
    root = _root(tmp_path, source)
    for name, text in files.items():
        (root / f"src/app/{name}.py").write_text(text)
    return root, _verdict(root, release_core, monkeypatch)["frame"]


@pytest.mark.parametrize("hops", [1, 2, 3, 4, 6])
def test_a_rename_chain_of_any_length_hands_the_module_on(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, hops: int
) -> None:
    root, frame = _run(tmp_path, release_core, monkeypatch, hops, "cp")

    assert _loads_lib(root), "CPython must import app.lib: the plant is real"
    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame


@pytest.mark.parametrize("hops", [1, 4])
def test_a_rename_chain_of_a_number_stays_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, hops: int
) -> None:
    source, files = chain(hops, "value")
    root = _root(tmp_path, source.replace(".run('import app.lib')", ""))
    for name, text in files.items():
        (root / f"src/app/{name}.py").write_text(text)
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert not _loads_lib(root), "CPython must leave app.lib unloaded: the control is clean"
    assert frame["rules"]["NO-LIB"][1] == "PASS", frame


def test_a_rename_cycle_ends_the_table(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path, "value = 1\n")
    (root / "src/app/util.py").write_text("import cProfile as a\n")
    (root / "src/app/m1.py").write_text("from app.m2 import b as a\nfrom app.util import a as c\n")
    (root / "src/app/m2.py").write_text("from app.m1 import a as b\n")
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] == "PASS", frame
