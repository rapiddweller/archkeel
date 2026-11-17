# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1714: a bare class annotation never passes a builtin type that the class namespace can change.

Consumer: `archkeel validate` with a UML target (AD-748): class `A`, attribute `A.x: int`. The
project allows Python 3.14 (`requires-python = ">=3.11"`). On 3.14 the annotation is evaluated
in the namespace of `A` when it is read (PEP 649), and `typing.get_type_hints(A)` reads that
namespace for a string annotation on every version. A slot `int`, a store `A.int = str` in a file
outside the scan roots, or a `setattr` with a computed name then changes what `x: int` means, so
the row must not PASS (AD-802).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from python_symbol_plants import C, pl
from python_symbol_sources import Want, project
from test_cli_core_only_scan import command

ROW = "UML-TARGET-a2e40c5592b1b06a"
SLOT = "class A:\n    __slots__ = ('int',)\n    x: int\n"
PLAIN = "class A:\n    x: int\n"
# name: (demo/m.py, more files below demo, files at the root, Python, the truth of `x`)
PLANTS = {
    "slot": (SLOT, {}, {}, "python3.14", "<member 'int' of 'A' objects>"),
    "future-slot": (
        "from __future__ import annotations\n" + SLOT,
        {},
        {},
        "python3.12",
        "<member 'int' of 'A' objects>",
    ),
    "outside-store": (
        PLAIN,
        {},
        {"boot.py": "import demo.m\ndemo.m.A.int = str\n"},
        "python3.14",
        "<class 'str'>",
    ),
    "computed-setattr": (
        PLAIN,
        {"helper.py": "def put(o, n, v):\n    setattr(o, n, v)\n"},
        {"boot.py": "import demo.m, demo.helper\ndemo.helper.put(demo.m.A, 'int', str)\n"},
        "python3.14",
        "<class 'str'>",
    ),
}
READ = (
    "import sys, runpy, typing; sys.path.insert(0, '.'); "
    "runpy.run_path('boot.py') if __import__('os').path.exists('boot.py') else None; "
    "import demo.m; A = demo.m.A; "
    "print(typing.get_type_hints(A)['x'] if 'annotations' in open('demo/m.py').read() "
    "else __import__('annotationlib').get_annotations(A)['x'])"
)


def _row(release_core: Path, root: Path) -> str:
    done = command(release_core, root, "--json")
    return json.loads(done.stdout)["frame"]["rules"][ROW][1]


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_class_namespace_that_can_hold_the_name_keeps_the_attribute_unproven(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    source, more, outside, python, truth = PLANTS[name]
    want = Want("attribute", "A.x", {"annotation": "int"})
    root = project(tmp_path / "p", pl(source, [C, want], "DIFF", **more))
    for path, text in outside.items():
        (root / path).write_text(text)
    if shutil.which(python):
        done = subprocess.run([python, "-I", "-c", READ], cwd=root, capture_output=True, text=True)
        assert done.stdout.strip() == truth, done.stderr

    assert _row(release_core, root) in {"FAIL", "UNKNOWN"}


def test_a_bare_builtin_annotation_without_a_namespace_write_still_passes(
    release_core: Path, tmp_path: Path
) -> None:
    want = Want("attribute", "A.x", {"annotation": "int"})
    root = project(tmp_path / "p", pl(PLAIN, [C, want], "PASS"))
    assert _row(release_core, root) == "PASS"
