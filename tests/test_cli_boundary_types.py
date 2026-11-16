# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-550: the core decides the syntax half of `boundary_types` on plants.

`boundary_types_rows.json` pins, for each plant of `boundary_types_plants.py`, the row of release
4.0.1 (`validate --json` of an installed 4.0.1 on the same tree), the row of the core and the named
causes of its gaps. A core PASS needs the truth PASS and a core FAIL needs the truth FAIL. The core
never answers PASS where the release answers FAIL or UNKNOWN. Every other difference from the
release is a stricter UNKNOWN: a named gap where the release decides.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from boundary_types_plants import PLANTS
from boundary_types_sources import RULE, project
from test_cli_core_only_scan import command

ROWS = json.loads((Path(__file__).parent / "boundary_types_rows.json").read_text())
STRICTER = {("PASS", "UNKNOWN"), ("FAIL", "UNKNOWN")}
# (equal, PASS to UNKNOWN, FAIL to UNKNOWN, plants) between release 4.0.1 and the core.
COUNTS = (39, 11, 9, 59)
CAUSE = re.compile(r"boundary_type_position: \S+ \S+: (\w+): ")


def test_every_plant_has_a_pinned_row() -> None:
    assert set(ROWS) == set(PLANTS)


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_core_row_is_sound_and_never_weaker_than_the_release(name: str) -> None:
    four, core, _ = ROWS[name]
    truth = PLANTS[name].truth
    assert four == core or (four, core) in STRICTER
    assert core != "PASS" or truth == "PASS"
    assert core != "FAIL" or truth == "FAIL"


def test_the_difference_between_the_release_and_the_core_is_counted() -> None:
    rows = [(four, core) for four, core, _ in ROWS.values()]
    equal = sum(four == core for four, core in rows)
    passes = sum(row == ("PASS", "UNKNOWN") for row in rows)
    fails = sum(row == ("FAIL", "UNKNOWN") for row in rows)
    assert (equal, passes, fails, len(rows)) == COUNTS


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_rule_row_is_the_pinned_row(release_core: Path, tmp_path: Path, name: str) -> None:
    _, expected, cause = ROWS[name]
    root = project(tmp_path / "p", PLANTS[name])
    result = json.loads(command(release_core, root, "--json").stdout)
    assert "refusal" not in result, result
    assert result["frame"]["rules"][RULE] == ["boundary_types", expected], result["frame"]
    text = command(release_core, root, "--text").stdout
    found = {match.group(1) for line in text.splitlines() if (match := CAUSE.search(line))}
    if "boundary_type_allowance_stale:" in text:
        found.add("stale_allowance")
    assert "; ".join(sorted(found)) == cause
    if expected == "FAIL":
        assert result["exit_code"] == 1
