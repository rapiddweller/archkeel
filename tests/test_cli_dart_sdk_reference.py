# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-506: a forbidden SDK library is a real target outside the namespace, as in release 4.0.1.

`fixtures/G-dart` forbids `dart.io` for its domain. Release 4.0.1 exempts the name of a Dart SDK
library from `reference.namespace` (`ir/profiles.py` `sdk_libraries`). Any other name outside the
namespace stays a defect, also a name in the `dart` family that is no SDK library.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from core_support import ROOT, run
from corpus_support import commit_tree

from archkeel.cli import core_only

FIXTURE = ROOT / "fixtures/G-dart"
PREFIX = "hygiene:reference.namespace:"


def _namespace_gaps(frame: dict[str, Any]) -> list[str]:
    return [key for key in frame["unsupported"]["rules"] if key.startswith(PREFIX)]


def _frame(release_core: Path, root: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    _, envelope = run("validate", "--root", str(root))
    return envelope["frame"]


def _planted(tmp_path: Path, target: str) -> Path:
    root = tmp_path / "project"
    shutil.copytree(FIXTURE, root)
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["rules"][6]["target"] = target
    path.write_text(json.dumps(contract))
    commit_tree(root)
    return root


def test_the_forbidden_dart_io_of_the_fixture_is_no_namespace_defect(
    release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = _frame(release_core, FIXTURE, monkeypatch)
    assert _namespace_gaps(frame) == []
    assert not any(gap["kind"] == "reference.namespace" for gap in frame["collection_gaps"] or [])


@pytest.mark.parametrize("target", ["dart.async", "dart.web_gl", "dart.ui_web"])
def test_each_sdk_library_of_release_4_0_1_is_exempt(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, target: str
) -> None:
    frame = _frame(release_core, _planted(tmp_path, target), monkeypatch)
    assert _namespace_gaps(frame) == []


@pytest.mark.parametrize("target", ["dart.nothing", "dart", "other.io", "flutter.material"])
def test_a_name_that_is_no_sdk_library_stays_a_namespace_defect(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, target: str
) -> None:
    frame = _frame(release_core, _planted(tmp_path, target), monkeypatch)
    keys = _namespace_gaps(frame)
    assert len(keys) == 1 and keys[0].endswith(f"/rules/6/target:{target}")
