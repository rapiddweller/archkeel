# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A value read with a run-time key and called later holds the rule (#1525, #1547, AD-508).

Module `a` calls `window.open()`. Module `b` reads `o[k]`, keeps the value and calls it later.
With `o = () => 1` and `k = 'constructor'` the value is `Function`, and the call runs a text that
replaces `open` (node v26 runs each plant with a text that overwrites a global). So `REQUIRES` is
FAIL or UNKNOWN, never PASS. The data plant reads `o[k]` only to test it: it keeps its PASS.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from core_support import run
from corpus_support import commit_tree
from test_collector_false_pass_sources import BASE

from archkeel.cli import core_only

PLANTS = {
    # The three plants of the audit (#1525).
    "lookup-stored": "export function run(o: any, k: string, t: string) "
    "{ const f = o[k]; f(t)(); }",
    "lookup-passed": "function g(f: any, t: string) { f(t)(); }\n"
    "export function run(o: any, k: string, t: string) { g(o[k], t); }",
    "lookup-argument": "export function run(o: any, k: string, t: string) "
    "{ Function.prototype.call.call(o[k], null, t)(); }",
    # The forms of #1547.
    "lookup-call-member": "export function run(o: any, k: string, t: string) "
    "{ const p = o[k]; if (typeof p === 'function') { p.call(o, t)(); } }",
    "lookup-apply-member": "export function run(o: any, k: string, t: string) "
    "{ const p = o[k]; p.apply(o, [t])(); }",
    "lookup-array": "export function run(o: any, k: string, t: string) { [o[k]][0](t)(); }",
    "lookup-object": "export function run(o: any, k: string, t: string) "
    "{ const q = { p: o[k] }; q.p(t)(); }",
    "lookup-reflect-apply": "export function run(o: any, k: string, t: string) "
    "{ Reflect.apply(o[k], o, [t])(); }",
    "lookup-returned": "function g(o: any, k: string) { return o[k]; }\n"
    "export function run(o: any, k: string, t: string) { g(o, k)(t)(); }",
}


def _validate(tmp_path: Path, release_core: Path, b: str) -> dict:
    root = tmp_path / "repo"
    files = {**BASE, "src/a/a.ts": "window.open();\n", "src/b/b.ts": "export {};\n" + b}
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    commit_tree(root)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: release_core)
        return run("validate", "--root", str(root))[1]


@pytest.mark.parametrize("name", PLANTS)
def test_a_looked_up_value_that_is_called_later_cannot_pass(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    document = _validate(tmp_path, release_core, PLANTS[name])
    assert "refusal" not in document, document
    assert document["frame"]["rules"]["REQUIRES"][1] in {"FAIL", "UNKNOWN"}, name


def test_a_looked_up_value_that_is_only_tested_keeps_its_pass(
    tmp_path: Path, release_core: Path
) -> None:
    b = "export function has(o: any, k: string) { return typeof o[k] === 'function'; }"
    document = _validate(tmp_path, release_core, b)
    assert document["frame"]["rules"]["REQUIRES"][1] == "PASS", document
