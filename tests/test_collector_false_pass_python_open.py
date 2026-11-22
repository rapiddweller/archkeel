# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Open false PASS of the Python trojan horse rules (AD-1058, `docs/known-limits.md`).

Each plant imports `app.lib` under CPython 3.12 and the core still gives PASS. The plants are
strict expected failures: when a fix lands, the plant passes, the strict marker fails the run,
and the person who fixes it removes the marker and the issue from `known-limits.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_collector_false_pass_python_trojan_attribute import EDIT, F, _loads_lib, _root, _verdict

OPEN = {
    # #1969: `dis.Bytecode(f).codeobj` hands out the code object without the name `__code__`.
    "dis-codeobj": (
        "import dis\n\n\n" + F + "code = dis.Bytecode(f).codeobj\n"
        "g = type(f)(code.replace(co_names=" + EDIT + "), {})\ng()\n",
        1969,
    ),
}


@pytest.mark.xfail(strict=True, reason="#1969: dis.Bytecode(f).codeobj is not read")
@pytest.mark.parametrize("name", sorted(OPEN))
def test_an_open_route_to_a_code_object_gives_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    source, _issue = OPEN[name]
    root = _root(tmp_path, source)
    assert _loads_lib(root), "CPython must import app.lib: the plant is real"
    frame = _verdict(root, release_core, monkeypatch)["frame"]

    assert frame["rules"]["NO-LIB"][1] in {"FAIL", "UNKNOWN"}, frame
