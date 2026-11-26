# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#2089: an `interface.usage_unknown` hold of the kind "import seen" names why it proves no use.

Consumer: a person who reads the gap of a public entry. The gap names the cause of each import
that reaches the module of the entry (the class of the collector, as in `explain.holds`), the
first import and the module or hop that withheld its route. A plant for each cause; a plant that
proves the use (a control) gives no hold.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from python_interface_plants import DEFINES, IMPL, LIB, Plant, build
from test_cli_native_python_imports import verdict

SINK = "def sink(value: object) -> None:\n    pass\n"
ENTRY = ("app.lib.impl:f",)
FILES = {LIB: "", IMPL: DEFINES}


def plant(name: str, consumer: str, files: dict[str, str]) -> Plant:
    return Plant(name, consumer, ENTRY, files, core=("UNKNOWN",))


PLANTS = {
    # A use inside the scan hands the package object on: a write below it is not excluded.
    # The import of the package is no import of the module of the entry.
    "escaped": plant(
        "module object handed on",
        "from app.lib.impl import f\nimport app.lib as pkg\nfrom app.sink import sink\n"
        "sink(pkg)\nf()\n",
        {**FILES, "src/app/sink.py": SINK},
    ),
    # `__all__` is not one literal list: the names of the module are not read.
    "unread_all": plant(
        "__all__ not literal",
        "from app.lib.impl import f\nf()\n",
        {**FILES, IMPL: DEFINES + "__all__ = [name for name in ('f', 'g')]\n"},
    ),
}


def usage_unknown(result: dict[str, object]) -> list[str]:
    rows = result["frame"]["unsupported"]["rules"]  # type: ignore[index]
    return [
        text for name, text in rows.items() if name.startswith("hygiene:interface.usage_unknown:")
    ]


@pytest.mark.parametrize("cause", sorted(PLANTS))
def test_an_import_seen_hold_names_its_cause_its_import_and_its_module(
    release_core: Path, tmp_path: Path, cause: str
) -> None:
    root = tmp_path / "p"
    root.mkdir()
    result = verdict(release_core, build(root, PLANTS[cause]))
    reasons = usage_unknown(result)
    assert len(reasons) == 1, result["frame"]["unsupported"]["rules"]
    text = reasons[0]
    assert "reaches the component, but the core proves no use of this entry" in text, text
    assert f"Cause of each of 1 imports: 1 {cause}." in text, text
    assert f"First: app.consumer imports f, {cause} (app.lib.impl)." in text, text
    assert result["status"] != "PASS"


def test_a_proven_use_gives_no_hold(release_core: Path, tmp_path: Path) -> None:
    """The control: the same shape without the cause proves the use."""
    root = tmp_path / "p"
    root.mkdir()
    control = plant("control", "from app.lib.impl import f\nf()\n", FILES)
    result = verdict(release_core, build(root, control))
    assert usage_unknown(result) == [], result["frame"]["unsupported"]["rules"]
