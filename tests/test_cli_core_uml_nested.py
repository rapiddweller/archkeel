# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-526: the core compares the UML target of an inside contract.

Each plant is a TypeScript tree whose inside contract draws its own target. `PLANTS` of
`uml_nested_plants.py` names the row of release 4.0.1 on the same tree (REFUSED: 4.0.1 gives no
row and exits 2) and the row of the core. The core is never more permissive than 4.0.1: it gives
no PASS where 4.0.1 gives FAIL or refuses.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_cli_core_only_scan import command
from uml_nested_plants import PLANTS, write

ROW = "UML-TARGET-a2e40c5592b1b06a"


def run_of(core: Path, tmp_path: Path, name: str) -> tuple[int, dict]:
    done = command(core, write(tmp_path, PLANTS[name]), "--json")
    return done.returncode, json.loads(done.stdout)


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_nested_uml_row_is_the_release_row_or_stricter(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    plant = PLANTS[name]
    code, result = run_of(release_core, tmp_path, name)
    assert "refusal" not in result, result
    frame = result["frame"]
    if plant.core == "NO-ROW":
        assert ROW not in frame["rules"], frame["rules"]
        assert code == 2 and "inside contracts" in frame["unsupported"]["rules"], frame
        return
    assert frame["rules"][ROW] == ["uml_target", plant.core], frame["explained"]
    if plant.core == "FAIL":
        assert frame["details"][ROW] and code == 1
    if plant.core == "PASS":
        assert result["status"] == "PASS" and code == 0, frame
    # The core gives no PASS where 4.0.1 gives FAIL or no row.
    assert not (plant.core == "PASS" and plant.release in {"FAIL", "REFUSED"})


def test_a_nested_fail_names_the_missing_import_of_the_inside_target(
    release_core: Path, tmp_path: Path
) -> None:
    _, result = run_of(release_core, tmp_path, "one-import-missing")
    details = result["frame"]["details"][ROW]
    assert [row["cause"] for row in details] == ["declared import is absent"], details


@pytest.mark.parametrize(
    ("name", "words"),
    [
        ("module-outside-mount", "outside the mount"),
        ("same-element-in-two-forms", "both draw"),
        ("same-element-equal-twice", "duplicate planned entity"),
        ("gap-outside-mount", "scope of the run is not complete"),
    ],
)
def test_an_unknown_nested_row_names_its_cause(
    release_core: Path, tmp_path: Path, name: str, words: str
) -> None:
    _, result = run_of(release_core, tmp_path, name)
    assert words in result["frame"]["explained"][ROW], result["frame"]["explained"]


def test_no_nested_plant_gives_a_pass_where_release_4_0_1_does_not() -> None:
    passing = {name for name, plant in PLANTS.items() if plant.core == "PASS"}
    assert passing == {
        "nested-equal",
        "nested-and-root-equal",
        "inside-element-in-root-only",
        "two-mount-levels",
    }
    assert all(PLANTS[name].release == "PASS" for name in passing)
    assert len(PLANTS) >= 16
