# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A code address that a framework can render from data holds the rule (#1662, AD-810).

A framework outside the scan roots renders an address from data (`<a href={url}>`). When the text
is a `javascript:` address, a click runs it, and it can replace the global `open` that component
`a` calls. The printed assumption says that such addresses hold no code. The visible evidence
against it holds the rule, and the gap names the place: a string or a template of the scanned
sources with a code address, and a JSON or YAML file below a scan root that holds one. Without such
a text the rule passes under the printed assumption.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from core_support import run
from corpus_support import commit_tree
from test_collector_false_pass_sources import BASE

from archkeel.cli import core_only

PREMISE = (
    "code outside the scan roots hands in no global or platform object and replaces no global, "
    "and addresses that a framework renders from data hold no javascript: code; "
    "the runtime supplies any host global proved by a project declaration"
)
JSX = '{"compilerOptions":{"allowJs":true,"jsx":"preserve"},"include":["src"]}'

# Each text that a framework can render as an address, with the place that the gap must name.
EVIDENCE: dict[str, tuple[dict[str, str], str]] = {
    "string": ({"src/b/b.ts": "export const help = 'javascript:open=()=>{}';\n"}, "src/b/b.ts:1"),
    "template": (
        {"src/b/b.ts": "export const go = (x: string) => `javascript:${x}`;\n"},
        "src/b/b.ts:1",
    ),
    "upper-case": ({"src/b/b.ts": "export const help = 'JavaScript:open=1';\n"}, "src/b/b.ts:1"),
    "vbscript": ({"src/b/b.ts": "export const help = 'vbscript:open';\n"}, "src/b/b.ts:1"),
    "html-data": (
        {"src/b/b.ts": "export const page = 'data:text/html,<script>open=1</script>';\n"},
        "src/b/b.ts:1",
    ),
    "jsx-attribute": (
        {
            "tsconfig.json": JSX,
            "src/b/view.tsx": 'export const L = () => <a href="javascript:open=()=>{}">x</a>;\n',
        },
        "src/b/view.tsx:1",
    ),
    "json": (
        {"src/b/links.json": '{\n  "help": "javascript:open=()=>{}"\n}\n'},
        "src/b/links.json:2",
    ),
    "yaml": ({"src/b/links.yaml": "home: /\nhelp: javascript:open=()=>{}\n"}, "src/b/links.yaml:2"),
}

# Data and markup without a code address keep the proof.
QUIET: dict[str, dict[str, str]] = {
    "bound-address": {
        "tsconfig.json": JSX,
        "src/b/view.tsx": "export const L = ({ url }: { url: string }) => <a href={url}>x</a>;\n",
    },
    "plain-data": {"src/b/links.json": '{"help": "https://example.com/help", "home": "/"}\n'},
}


def _validate(tmp_path: Path, release_core: Path, extra: dict[str, str]) -> dict[str, Any]:
    root = tmp_path / "repo"
    files = {**BASE, "src/a/a.ts": "window.open();\n", "src/b/b.ts": "export {};\n", **extra}
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    commit_tree(root)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: release_core)
        return run("validate", "--root", str(root))[1]


def _places(frame: dict[str, Any]) -> set[str]:
    return {
        f"{place['path']}:{place['line']}"
        for gap in frame["collection_gaps"]
        for evidence in gap["evidence"]
        if (place := frame["locations"].get(evidence))
    }


@pytest.mark.parametrize("name", sorted(EVIDENCE))
def test_a_code_address_in_the_scan_holds_the_rule(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    files, place = EVIDENCE[name]
    document = _validate(tmp_path, release_core, files)
    assert "refusal" not in document, document
    frame = document["frame"]
    assert frame["rules"]["REQUIRES"][1] in {"FAIL", "UNKNOWN"}, (name, frame["rules"])
    assert place in _places(frame), (name, frame["collection_gaps"])


@pytest.mark.parametrize("name", sorted(QUIET))
def test_without_a_code_address_the_rule_passes_under_the_printed_assumption(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    document = _validate(tmp_path, release_core, QUIET[name])
    frame = document["frame"]
    assert frame["rules"]["REQUIRES"][1] == "PASS", (name, frame["rules"], frame["collection_gaps"])
    assert frame["premise"] == PREMISE
