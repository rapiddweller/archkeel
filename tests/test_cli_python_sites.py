# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-520: the core compares the relationships of a UML target on Python plants.

`python_site_rows.json` pins, for each plant of `python_site_plants.py`, the row of release 4.0.1
(`validate --json` of an installed 4.0.1 on the same tree), the row of the core and its cause. A
core PASS needs the truth PASS; a core FAIL needs the truth DIFF; every other difference from the
release is a stricter UNKNOWN.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from python_site_plants import PLANTS
from python_symbol_sources import project
from test_cli_core_only_scan import command

ROW = "UML-TARGET-a2e40c5592b1b06a"
ROWS = json.loads((Path(__file__).parent / "python_site_rows.json").read_text())
STRICTER = {("PASS", "UNKNOWN"), ("FAIL", "UNKNOWN")}
# (equal, PASS to UNKNOWN, FAIL to UNKNOWN, plants). A release FAIL is true but one.


def test_every_plant_has_a_pinned_row() -> None:
    assert set(ROWS) == set(PLANTS)


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_core_row_is_sound_and_never_weaker_than_the_release(name: str) -> None:
    four, core, _ = ROWS[name]
    truth = PLANTS[name].truth
    assert four == core or (four, core) in STRICTER
    assert core != "PASS" or truth == "PASS"
    assert core != "FAIL" or truth == "DIFF"
    assert (four == "FAIL" and truth == "PASS") == (name == "closed-dead-if-false")


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_site_row_is_the_pinned_row(release_core: Path, tmp_path: Path, name: str) -> None:
    _, expected, cause = ROWS[name]
    done = command(release_core, project(tmp_path / "p", PLANTS[name]), "--json")
    result = json.loads(done.stdout)
    assert "refusal" not in result, result
    assert result["frame"]["rules"][ROW] == ["uml_target", expected], result["frame"]
    if expected == "FAIL":
        found = {item["cause"] for item in result["frame"]["details"][ROW]}
        assert "; ".join(sorted(found)) == cause and done.returncode == 1
    if expected == "UNKNOWN":
        assert cause in result["frame"]["explained"][ROW]
        assert done.returncode == 2
