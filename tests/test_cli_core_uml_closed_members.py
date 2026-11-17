# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-747: a closed class scope passes only from a complete member inventory.

The plants are in `uml_closed_plants.py`. A PASS row where a form can add a member that the body
does not show is a false PASS.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_cli_core_only_scan import command
from test_cli_core_uml_compare import project
from uml_closed_plants import PLANTS
from uml_symbol_plants import ROW


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_closed_scope_row_is_the_pinned_row(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    files, uml, expected, cause = PLANTS[name]
    done = command(release_core, project(tmp_path, files, uml, None), "--json")
    result = json.loads(done.stdout)
    assert "refusal" not in result, result
    frame = result["frame"]
    assert frame["rules"][ROW] == ["uml_target", expected], frame["explained"]
    if expected == "PASS":
        assert not cause
        assert result["status"] == "PASS" and done.returncode == 0, frame
    if expected == "FAIL":
        assert {item["cause"] for item in frame["details"][ROW]} == {cause}
    if expected == "UNKNOWN":
        assert cause in frame["explained"][ROW], frame["explained"][ROW]
