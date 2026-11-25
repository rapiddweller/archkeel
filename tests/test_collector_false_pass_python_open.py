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
from python_stdlib_importer_plants import BUILD, CODE, guarded, quiet
from test_collector_false_pass_python_trojan_attribute import _loads_lib, _root, _verdict

OPEN = {
    # #1974: `typing.get_type_hints` evaluates the annotation string, which calls `__import__`.
    "typing-get-type-hints": (
        "import typing\n\n\nclass K:\n    x: \"__import__('app.lib')\"\n\n\n"
        "typing.get_type_hints(K)\n",
        {},
    ),
    # #1976: four more routes. Each plant imports `app.lib` under CPython 3.12.
    "literal import call gives the module": (
        guarded(
            "import importlib\n",
            "importlib.import_module('unittest').TestLoader().loadTestsFromName('app.lib')",
        ),
        {},
    ),
    "vars of dis": (
        "import dis\n\n\n" + CODE + "code = vars(dis)['Bytecode'](f).codeobj\n" + BUILD,
        {},
    ),
    "cProfile -m entry point": (
        quiet(
            "import cProfile\nimport sys\n\nsys.argv = ['x', '-m', 'app.lib']\n",
            "cProfile.main()",
        ),
        {},
    ),
    "pdb set_trace with scripted stdin": (
        quiet(
            "import io\nimport pdb\nimport sys\n\n"
            "sys.stdin = io.StringIO('import app.lib\\nc\\n')\n",
            "pdb.set_trace()",
        ),
        {},
    ),
    "inspect eval_str": (
        "import inspect\n\n\ndef f(x: \"__import__('app.lib')\"):\n    pass\n\n\n"
        "inspect.signature(f, eval_str=True)\n",
        {},
    ),
}


@pytest.mark.xfail(strict=True, reason="#1974 (typing string), #1976 (four routes)")
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
