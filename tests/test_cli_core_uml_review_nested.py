# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-526, proof review: the joined UML target links the references of the whole tree, and the
stops keep the mount index of each mount.

Each plant states the truth of its row. `!PASS` means that 4.0.1 refuses the tree or the element
is not provable, so the core must not give PASS; `PASS?` is left to 4.0.1 (no assertion).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_cli_core_only_scan import command
from uml_review_plants import PLANTS, write

ROW = "UML-TARGET-a2e40c5592b1b06a"
LINKS = [name for name in PLANTS if "link-ref" in name]
MOUNTS = [name for name in PLANTS if "outside" in name]


def verdict(core: Path, tmp_path: Path, name: str) -> tuple[str, dict]:
    done = command(core, write(tmp_path, PLANTS[name]), "--json")
    frame = json.loads(done.stdout).get("frame", {})
    row = frame.get("rules", {}).get(ROW)
    return (row[1] if row else "NO-ROW"), frame


@pytest.mark.parametrize("name", LINKS)
def test_a_reference_that_4_0_1_refuses_to_link_gives_no_pass(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    found, frame = verdict(release_core, tmp_path, name)
    assert found in {"UNKNOWN", "NO-ROW"}, (found, frame.get("explained"))
    assert "refuses to link" in frame["explained"][ROW]


@pytest.mark.parametrize("name", MOUNTS)
def test_a_module_outside_its_mount_is_unknown_whatever_the_mount_index(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    found, frame = verdict(release_core, tmp_path, name)
    assert found == "UNKNOWN", (found, frame.get("explained"))
    if PLANTS[name].truth == "UNKNOWN":
        assert "outside the mount" in frame["explained"][ROW], frame["explained"]


@pytest.mark.parametrize(
    "name", ["c-nested-equal", "link-same-edge-in-two-contracts", "link-open-scope-on-definition"]
)
def test_a_link_stop_does_not_hold_a_tree_that_links_cleanly(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    found, frame = verdict(release_core, tmp_path, name)
    assert found != "UNKNOWN" or "refuses to link" not in frame["explained"].get(ROW, ""), frame
    if PLANTS[name].truth == "PASS":
        assert found == "PASS"
