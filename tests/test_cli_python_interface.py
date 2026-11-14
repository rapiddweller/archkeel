# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-504: `interface_boundary` on Python through the release core, against release 4.0.1.

Consumer: a CI job that reads the row of an `interface_boundary` rule of a Python project. Each
plant has the verdict of 4.0.1 (`python_interface_plants.FOUR`) and the verdicts that the core may
give. The core gives the verdict of 4.0.1, or UNKNOWN where the survey cannot read a hop or the
names of a module. It never gives PASS where 4.0.1 gives FAIL or UNKNOWN, and never FAIL where
4.0.1 gives PASS.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from python_interface_plants import Plant, build, plants
from test_cli_native_python_imports import rows, verdict

PLANTS = plants()


@pytest.mark.parametrize("plant", PLANTS, ids=[plant.name for plant in PLANTS])
def test_the_core_gives_the_verdict_of_4_0_1_or_unknown_never_a_weaker_one(
    release_core: Path, tmp_path: Path, plant: Plant
) -> None:
    root = tmp_path / "p"
    root.mkdir()
    result = verdict(release_core, build(root, plant))
    core = rows(result)["BOUNDARY"]
    assert core in plant.core, (plant.name, core, result["frame"]["explained"])
    # The differential: PASS only where 4.0.1 passes, FAIL only where 4.0.1 fails.
    assert core != "PASS" or plant.four == "PASS", plant.name
    assert core != "FAIL" or plant.four == "FAIL", plant.name
    if core != plant.four:
        assert core == "UNKNOWN" and plant.why, plant.name
