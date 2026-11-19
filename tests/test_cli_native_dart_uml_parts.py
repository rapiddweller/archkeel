# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The closed UML scope of a Dart mixin in a part file."""

from pathlib import Path

import pytest
from core_support import run

from archkeel.cli import core_only
from tools.fixture_tree import fixture_tree
from tools.report_gallery import MATRIX, load_runs

ROOT = MATRIX.parent / "H-uml-dart" / "part-members"
RULE = "UML-TARGET-a2e40c5592b1b06a"


def test_an_extra_method_in_a_part_has_source_evidence(
    release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    entry = next(row for row in load_runs() if row["name"] == "H-uml-dart-plant-part-member")
    with fixture_tree(ROOT, entry["plant"]["edits"]) as root:
        code, result = run("report", "--root", str(root))
    frame = result["frame"]
    assert (code, frame["rules"][RULE][1]) == (1, "FAIL")
    [detail] = frame["details"][RULE]
    assert detail["source"] == "catalog-model"
    assert detail["target"] == "catalog.models.CatalogModel.reset"
    assert detail["cause"] == "closed scope holds an unlisted definition"
    assert [frame["locations"][site] for site in detail["evidence"]] == [
        {"path": "lib/model_members.dart", "line": 9}
    ]


def test_an_unread_second_part_keeps_the_inventory_unknown(
    release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    edits = [{"path": "lib/models.dart", "append": "part 'unread.dart';\n"}]
    with fixture_tree(ROOT, edits) as root:
        code, result = run("report", "--root", str(root))
    frame = result["frame"]
    assert (code, frame["rules"][RULE][1]) == (2, "UNKNOWN")
    assert "not every part of the library was read" in frame["explained"][RULE]
    [gap] = frame["collection_gaps"]
    assert gap["detail"] == "DartTargetMissing: the file lib/unread.dart does not exist"
