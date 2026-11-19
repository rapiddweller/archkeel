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
ALIAS_EXTENSION = (
    "\ntypedef Alias = CatalogModel;\nextension ModelExtra on Alias { void extra() {} }\n"
)


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


@pytest.mark.parametrize(
    ("edits", "reason"),
    [
        (
            [{"path": "lib/models.dart", "append": "part 'unread.dart';\n"}],
            "DartTargetMissing: the file lib/unread.dart does not exist",
        ),
        (
            [
                {"path": "lib/models.dart", "append": "part '../outside.dart';\n"},
                {"path": "outside.dart", "append": "part of 'lib/models.dart';\n"},
            ],
            "DartTargetNotSelected: the part outside.dart is not a selected source",
        ),
    ],
)
def test_an_unread_second_part_keeps_the_inventory_unknown(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, edits: list[dict[str, str]], reason: str
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    with fixture_tree(ROOT, edits) as root:
        code, result = run("report", "--root", str(root))
    frame = result["frame"]
    assert (code, frame["rules"][RULE][1]) == (2, "UNKNOWN")
    assert "not every part of the library was read" in frame["explained"][RULE]
    [gap] = frame["collection_gaps"]
    assert gap["detail"] == reason


def test_an_extension_on_an_alias_keeps_the_inventory_unknown(
    release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    edits = [{"path": "lib/model_members.dart", "append": ALIAS_EXTENSION}]
    with fixture_tree(ROOT, edits) as root:
        code, result = run("report", "--root", str(root))
    frame = result["frame"]
    assert (code, frame["rules"][RULE][1]) == (2, "UNKNOWN")
    assert "the receiver of an extension is not proven" in frame["explained"][RULE]
    assert frame["collection_gaps"] == []


@pytest.mark.parametrize(
    ("owner", "library", "other_claim", "reason"),
    [
        ("models.dart", "", False, "DartPartUnowned"),
        ("'catalog.models'", "library catalog.models;\n", False, "DartPartUnowned"),
        ("'models.dart'", "", True, "DartPartConflict"),
        ("'models.dart';\npart of catalog.models", "", False, "DartPartUnowned"),
    ],
)
def test_wrong_and_conflicting_part_owners_cite_each_directive(
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    owner: str,
    library: str,
    other_claim: bool,
    reason: str,
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    edits = [
        {"path": "lib/models.dart", "old": "part '", "new": f"{library}part '"},
        {"path": "lib/model_members.dart", "old": "'models.dart'", "new": owner},
    ]
    if other_claim:
        edits.append({"path": "lib/other.dart", "append": "\npart 'model_members.dart';\n"})
    with fixture_tree(ROOT, edits) as root:
        code, result = run("report", "--root", str(root))
    frame = result["frame"]
    assert (code, frame["rules"][RULE][1]) == (2, "UNKNOWN")
    [gap] = frame["collection_gaps"]
    assert gap["detail"].startswith(f"{reason}:")
    assert gap["subjects"] == ["lib/model_members.dart:5"]
    expected = {("lib/model_members.dart", 5), ("lib/models.dart", 6 if library else 5)}
    if other_claim:
        expected.add(("lib/other.dart", 2))
    if "\n" in owner:
        expected.add(("lib/model_members.dart", 6))
    assert {
        (frame["locations"][site]["path"], frame["locations"][site]["line"])
        for site in gap["evidence"]
    } == expected
