# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Open false PASS of the Python trojan horse rules (AD-1059, `docs/known-limits.md`).

Each plant imports `app.lib` under CPython 3.12 and the core still gives PASS. The plants are
strict expected failures: when a fix lands, the plant passes, the strict marker fails the run,
and the person who fixes it removes the marker and the entry of `known-limits.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_collector_false_pass_python_trojan_attribute import _loads_lib, _root, _verdict

PATCH = "try:\n    util.{path}('app.lib.value').start()\nexcept Exception:\n    pass\n"
OPEN = {
    # #1973: a project module re-exports a standard library module and another module uses it.
    # The names of the standard library resolve through the import bindings of the module that
    # uses them; no attribute of a project module is followed. The same holds for
    # `unittest.mock.patch` since AD-450 and for `dis`, `unittest.main` and `xml.sax.make_parser`.
    "re-exported mock-patch": (
        "from app import util\n\n" + PATCH.format(path="mock.patch"),
        {"src/app/util.py": "from unittest import mock\n"},
    ),
    "re-exported dis": (
        "from app import util\n\n\ndef f():\n    import json\n    return json\n\n\n"
        "code = util.dis.Bytecode(f).codeobj\n"
        "names = tuple('app.lib' if n == 'json' else n for n in code.co_names)\n"
        "type(f)(code.replace(co_names=names), {})()\n",
        {"src/app/util.py": "import dis\n"},
    ),
    # #1974: `typing.get_type_hints` evaluates the annotation string, which calls `__import__`.
    "typing-get-type-hints": (
        "import typing\n\n\nclass K:\n    x: \"__import__('app.lib')\"\n\n\n"
        "typing.get_type_hints(K)\n",
        {},
    ),
    "re-exported unittest-main": (
        "from app import util\n\ntry:\n"
        "    util.unittest.main(module='app.lib', exit=False, argv=['x'])\n"
        "except Exception:\n    pass\n",
        {"src/app/util.py": "import unittest\n"},
    ),
}


@pytest.mark.xfail(strict=True, reason="#1973 (re-export) and #1974 (typing string annotation)")
@pytest.mark.parametrize("name", sorted(OPEN))
def test_an_open_route_through_a_re_exported_standard_library_module_gives_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    source, files = OPEN[name]
    root = _root(tmp_path, source)
    for relative, text in files.items():
        (root / relative).write_text(text)
    assert _loads_lib(root), "CPython must import app.lib: the plant is real"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame
