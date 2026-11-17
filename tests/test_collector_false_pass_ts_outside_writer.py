# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A repository file outside the scan roots that replaces a global holds the rule (#1546, AD-788).

`boot.ts` sits at the root of the repository, outside the scan root `src`. It writes
`window.open = hidden`, where `hidden` is code of component `b`. Component `a` calls
`window.open()`. With the file in the repository the rule is UNKNOWN, and the gap names the file
and the line. Without it the rule passes under the printed assumption, which now says that code
outside the scan roots replaces no global.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from core_support import run
from corpus_support import commit_tree
from test_collector_false_pass_sources import BASE

from archkeel.cli import core_only

PREMISE = (
    "code outside the scan roots hands in no global or platform object and replaces no global, "
    "and addresses that a framework renders from data hold no javascript: code"
)
BOOT = "import {hidden} from './src/b/b';\nwindow.open = hidden as any;\n"


def _validate(tmp_path: Path, release_core: Path, extra: dict[str, str]) -> dict:
    root = tmp_path / "repo"
    files = {
        **BASE,
        "src/a/a.ts": "window.open();\n",
        "src/b/b.ts": "export function hidden() {}\n",
        **extra,
    }
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    commit_tree(root)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: release_core)
        return run("validate", "--root", str(root))[1]


def test_an_outside_writer_in_the_repository_holds_the_rule(
    tmp_path: Path, release_core: Path
) -> None:
    document = _validate(tmp_path, release_core, {"boot.ts": BOOT})
    assert "refusal" not in document, document
    frame = document["frame"]
    assert frame["rules"]["REQUIRES"][1] in {"FAIL", "UNKNOWN"}, frame["rules"]
    held = [
        gap
        for gap in frame["collection_gaps"]
        if gap["reason"] == "Script global open is replaced by a file outside the scan roots"
    ]
    assert held, frame["collection_gaps"]
    places = {
        f"{place['path']}:{place['line']}"
        for gap in held
        for evidence in gap["evidence"]
        if (place := frame["locations"].get(evidence))
    }
    assert "boot.ts:2" in places, places


def test_without_the_outside_writer_the_rule_passes_under_the_printed_assumption(
    tmp_path: Path, release_core: Path
) -> None:
    document = _validate(tmp_path, release_core, {})
    frame = document["frame"]
    assert frame["rules"]["REQUIRES"][1] == "PASS", frame["rules"]
    assert frame["premise"] == PREMISE
