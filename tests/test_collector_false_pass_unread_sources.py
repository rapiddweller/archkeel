# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Code forms under the scan roots that the TypeScript profile does not read name a gap (#1528)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from core_support import run
from corpus_support import commit_tree
from test_collector_false_pass_sources import BASE

from archkeel.cli import core_only

UNREAD = {
    "vue": ('<script>import "../b/t";</script>', "Vue single-file components"),
    "svelte": ('<script>import "../b/t";</script>', "Svelte components"),
    "astro": ('---\nimport "../b/t";\n---\n<div/>', "Astro components"),
    "mdx": ('import { T } from "../b/t";\n\n# Example\n', "MDX documents"),
    "html": ('<script type="module">import "../b/t";</script>', "inline scripts of HTML pages"),
    "htm": ('<SCRIPT>import "../b/t";</SCRIPT>', "inline scripts of HTML pages"),
    "es6": ('import "../b/t";\n', ".es6 script suffix"),
}


def _validate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, release_core: Path, files: dict[str, str]
) -> dict[str, Any]:
    root = tmp_path / "repo"
    for name, text in {**BASE, "src/a/a.ts": "export const a = 1;\n", **files}.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    commit_tree(root)
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    document: dict[str, Any] = run("validate", "--root", str(root))[1]
    return document


@pytest.mark.parametrize("extension", sorted(UNREAD))
def test_an_unread_code_form_holds_the_rule_with_a_named_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, release_core: Path, extension: str
) -> None:
    text, form = UNREAD[extension]
    document = _validate(tmp_path, monkeypatch, release_core, {f"src/a/hidden.{extension}": text})
    assert document["frame"]["rules"]["REQUIRES"][1] == "UNKNOWN", document
    gaps = document["frame"]["explain"]["holds"]["gaps"]
    reasons = [gap["reason"] for gap in gaps if f"hidden.{extension}" in gap["reason"]]
    assert reasons and form in reasons[0], gaps


@pytest.mark.parametrize(
    "files",
    [
        {"src/a/page.html": "<p>No script here.</p>"},
        {"public/hidden.vue": '<script>import "../src/b/t";</script>'},
        {"public/index.html": '<script>import "../src/b/t";</script>'},
        {"src/a/style.css": "a {}"},
    ],
    ids=["page-without-script", "vue-outside-roots", "html-outside-roots", "style"],
)
def test_a_file_that_holds_no_code_under_the_roots_stays_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, release_core: Path, files: dict[str, str]
) -> None:
    document = _validate(tmp_path, monkeypatch, release_core, files)
    assert document["frame"]["rules"]["REQUIRES"][1] == "PASS", document
