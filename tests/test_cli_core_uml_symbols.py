# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-512: the core compares the symbol part of a UML target on TypeScript plants.

The plants and their release rows are in `uml_symbol_plants.py`. A core PASS where 4.0.1 gives FAIL
or UNKNOWN is a bug. A core UNKNOWN where 4.0.1 passes is stricter; where the release PASS is wrong
(`WRONG_RELEASE_PASS`) the core is right.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_cli_core_only_scan import command
from test_cli_core_uml_compare import project
from uml_symbol_plants import (
    CAUSES,
    COUNTS,
    PLANTS,
    ROW,
    STRICTER,
    WRONG_RELEASE_PASS,
)


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_core_row_is_never_weaker_than_the_release_row(name: str) -> None:
    _, _, release, core = PLANTS[name]
    assert release == core or (release, core) in STRICTER


def test_the_difference_between_the_release_rows_and_the_core_rows_is_counted() -> None:
    rows = [(release, core) for _, _, release, core in PLANTS.values()]
    equal = sum(release == core for release, core in rows)
    passes = {n for n, p in PLANTS.items() if (p[2], p[3]) == ("PASS", "UNKNOWN")}
    fails = {n for n, p in PLANTS.items() if (p[2], p[3]) == ("FAIL", "UNKNOWN")}
    assert (equal, len(passes), len(fails), len(PLANTS)) == COUNTS
    assert WRONG_RELEASE_PASS < passes


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_symbol_row_is_the_pinned_row(release_core: Path, tmp_path: Path, name: str) -> None:
    files, uml, _, expected = PLANTS[name]
    done = command(release_core, project(tmp_path, files, uml, None), "--json")
    result = json.loads(done.stdout)
    assert "refusal" not in result, result
    assert result["frame"]["rules"][ROW] == ["uml_target", expected], result["frame"]["explained"]
    causes = CAUSES.get(name, "")
    causes = (causes,) if isinstance(causes, str) else causes
    if expected == "FAIL":
        found = {item["cause"] for item in result["frame"]["details"][ROW]}
        assert found == set(causes), found
        assert done.returncode == 1
    if expected == "PASS":
        assert result["status"] == "PASS" and done.returncode == 0, result["frame"]
        assert name not in CAUSES
    if expected == "UNKNOWN":
        assert causes[0] in result["frame"]["explained"][ROW], result["frame"]["explained"][ROW]
        assert result["frame"]["unknown_kinds"][ROW] == "no_receipt"
        assert done.returncode == 2
