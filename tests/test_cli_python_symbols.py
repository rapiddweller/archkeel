# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-518: the core compares the symbol part of a UML target on Python plants.

`python_symbol_rows.json` pins, for each plant of `python_symbol_plants.py`, the row of release
4.0.1 (`validate --json` of an installed 4.0.1 on the same tree), the row of the core and its
cause. A core PASS needs the truth PASS; a core FAIL needs the truth DIFF; every other
difference from the release is a stricter UNKNOWN.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from python_symbol_plants import PLANTS, C, pl
from python_symbol_sources import Want, project
from test_cli_core_only_scan import command

ROW = "UML-TARGET-a2e40c5592b1b06a"
ROWS = json.loads((Path(__file__).parent / "python_symbol_rows.json").read_text())
STRICTER = {("PASS", "UNKNOWN"), ("FAIL", "UNKNOWN")}
# 4.0.1 PASS, 4.0.1 FAIL and core row counts: (equal, PASS to UNKNOWN, FAIL to UNKNOWN, plants).
# Release 4.0.1 gives FAIL where Python binds what the target plans: a false FAIL.
FALSE_FAIL = {
    "globals-write",
    "dict-instance",
    "nested-function",
    "ff-attr-helper-method",
    "ff-attr-class-nested",
    "lambda-as-method",
}


def test_every_plant_has_a_pinned_row() -> None:
    assert set(ROWS) == set(PLANTS)


@pytest.mark.parametrize(
    ("annotation", "target", "expected"),
    [
        ("int", "str", "FAIL"),
        ("'int'", "int", "UNKNOWN"),
        ("UnknownType", "UnknownType", "UNKNOWN"),
        ("ClassVar[int]", "int", "UNKNOWN"),
    ],
)
def test_annotation_only_attributes_keep_unproved_types_unknown(
    release_core: Path, tmp_path: Path, annotation: str, target: str, expected: str
) -> None:
    source = f"from __future__ import annotations\nclass A:\n    x: {annotation}\n"
    want = Want("attribute", "A.x", {"annotation": target})
    done = command(release_core, project(tmp_path / "p", pl(source, [C, want], "DIFF")), "--json")
    result = json.loads(done.stdout)
    assert result["frame"]["rules"][ROW] == ["uml_target", expected], result


def test_annotation_declaration_does_not_hide_a_wrong_return_type(
    release_core: Path, tmp_path: Path
) -> None:
    source = "class A:\n    x: int\n    def run(self) -> int:\n        return 1\n"
    wants = [
        C,
        Want("attribute", "A.x", {"annotation": "int"}),
        Want(
            "method",
            "A.run",
            {
                "signature": {
                    "parameters": [{"name": "self", "kind": "positional", "default_known": True}],
                    "returns": "str",
                }
            },
        ),
    ]
    done = command(release_core, project(tmp_path / "p", pl(source, wants, "DIFF")), "--json")
    result = json.loads(done.stdout)
    assert result["frame"]["rules"][ROW] == ["uml_target", "FAIL"], result
    assert any(
        item["cause"] == "return annotation differs" for item in result["frame"]["details"][ROW]
    )


def test_a_class_without_a_declared_attribute_stays_unknown(
    release_core: Path, tmp_path: Path
) -> None:
    source = "class A:\n    pass\n"
    wants = [C, Want("attribute", "A.x")]
    done = command(release_core, project(tmp_path / "p", pl(source, wants, "DIFF")), "--json")
    result = json.loads(done.stdout)
    # Absence is not provable for a partial Python inventory.
    assert result["frame"]["rules"][ROW] == ["uml_target", "UNKNOWN"], result
    text = result["frame"]["explained"][ROW]
    assert "absent symbol: the symbol inventory is not complete" in text
    # #2089: the row names the symbol that the inventory lacks.
    assert re.search(r"not in the symbol inventory: \S*A\.x\b", text), text


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_core_row_is_sound_and_never_weaker_than_the_release_without_cause(name: str) -> None:
    four, core, _ = ROWS[name]
    truth = PLANTS[name].truth
    assert four == core or (four, core) in STRICTER
    assert core != "PASS" or truth == "PASS"
    assert core != "FAIL" or truth == "DIFF"
    # A release FAIL that the truth contradicts is a false FAIL, and the core never repeats it.
    assert (four == "FAIL" and truth == "PASS") == (name in FALSE_FAIL)


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_symbol_row_is_the_pinned_row(release_core: Path, tmp_path: Path, name: str) -> None:
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
