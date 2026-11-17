# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A member patch of a standard global holds the rule (#1674, AD-788).

Module `a` calls `Math.max(1, 2)`. A write `Math.max = hidden`, with `hidden` a function of
component `b`, makes that call run `b` (node v26: `Math.max = () => 777; Math.max(1, 2)` gives
777). In a scanned file and in a repository file outside the scan roots the write must hold
`REQUIRES`; a literal value keeps the PASS.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from core_support import run
from corpus_support import commit_tree
from test_collector_false_pass_sources import BASE

from archkeel.cli import core_only

HIDDEN = "export function hidden(): any { return 777; }\n"


def _validate(tmp_path: Path, release_core: Path, extra: dict[str, str]) -> dict:
    root = tmp_path / "repo"
    files = {**BASE, "src/a/a.ts": "export const m = Math.max(1, 2);\n", **extra}
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    commit_tree(root)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: release_core)
        return run("validate", "--root", str(root))[1]


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param({"src/b/b.ts": HIDDEN + "Math.max = hidden as any;\n"}, id="scanned"),
        pytest.param(
            {
                "src/b/b.ts": HIDDEN,
                "boot.ts": "import { hidden } from './src/b/b';\nMath.max = hidden;\n",
            },
            id="outside",
        ),
    ],
)
def test_a_member_patch_of_a_standard_global_cannot_pass(
    tmp_path: Path, release_core: Path, extra: dict[str, str]
) -> None:
    document = _validate(tmp_path, release_core, extra)
    assert "refusal" not in document, document
    assert document["frame"]["rules"]["REQUIRES"][1] in {"FAIL", "UNKNOWN"}, document["frame"]


def test_a_literal_member_write_keeps_the_pass(tmp_path: Path, release_core: Path) -> None:
    document = _validate(tmp_path, release_core, {"src/b/b.ts": HIDDEN + "(Math as any).x = 1;\n"})
    assert document["frame"]["rules"]["REQUIRES"][1] == "PASS", document["frame"]
