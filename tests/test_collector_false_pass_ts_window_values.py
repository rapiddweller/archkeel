# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A write through a value that the platform can make the window holds the rule (#1524, AD-766).

Module `a` calls `window.open()`. Module `b` writes a member with a run-time key, or writes
members by reflection, into an event target, the `this` of a method that a listener receives, or
such a value passed on, returned or stored. In a browser each plant replaces `open` (the audit of
#1524 ran them in node with browser objects). So `REQUIRES` is FAIL or UNKNOWN, never PASS. A
write into a value that the file makes keeps its PASS.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from core_support import run
from corpus_support import commit_tree
from test_collector_false_pass_sources import BASE

from archkeel.cli import core_only

KEY = "const k = ['op','en'].join('');\n"
PLANTS = {
    # The plants of the audit (#1524), as in draft #1550.
    "event-target": "addEventListener('load', ev => { ev.target[k] = () => {}; });",
    "event-src-element": "addEventListener('load', ev => { ev.srcElement[k] = () => {}; });",
    "this-double-alias": "class C { m() { let a: any = this; let b = a; b[k] = () => {}; } }\n"
    "addEventListener('load', new C().m);",
    "super-result": "class C extends EventTarget { m() { const s: any = super.valueOf(); "
    "s[k] = () => {}; } }\naddEventListener('load', new C().m);",
    "this-argument": "function g(w: any) { w[k] = () => {}; }\nclass C { m() { g(this); } }\n"
    "addEventListener('load', new C().m);",
    "window-parameter": "function f(w: any) { w[k] = () => {}; }\n"
    "addEventListener('load', ev => f(ev.target));",
    "window-result": "function f(ev: any) { return ev.target; }\n"
    "addEventListener('load', ev => { f(ev)[k] = () => {}; });",
    "window-property": "addEventListener('load', ev => { const h = { w: ev.target as any }; "
    "h.w[k] = () => {}; });",
    # Reflective writes of the same class.
    "reflect-set": "addEventListener('load', ev => "
    "{ Reflect.set(ev.target as any, k, () => {}); });",
    "define-property": "addEventListener('load', ev => "
    "{ Object.defineProperty(ev.target, k, { value: () => {} }); });",
    "assign": "addEventListener('load', ev => { Object.assign(ev.target as any, { open: 1 }); });",
    # Indirect reflective writes.
    "call-member": "addEventListener('load', ev => "
    "Object.assign.call(null, ev.target, { open: 1 }));",
    "define-getter": "addEventListener('load', ev => "
    "(ev.target as any).__defineGetter__(k, () => 1));",
    "through-global-this": "addEventListener('load', ev => "
    "globalThis.Object.assign(ev.target, { open: 1 }));",
}


def _validate(tmp_path: Path, release_core: Path, b: str) -> dict:
    root = tmp_path / "repo"
    files = {**BASE, "src/a/a.ts": "window.open();\n", "src/b/b.ts": "export {};\n" + KEY + b}
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    commit_tree(root)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: release_core)
        return run("validate", "--root", str(root))[1]


@pytest.mark.parametrize("name", PLANTS)
def test_a_write_through_a_window_value_cannot_pass(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    document = _validate(tmp_path, release_core, PLANTS[name])
    assert "refusal" not in document, document
    assert document["frame"]["rules"]["REQUIRES"][1] in {"FAIL", "UNKNOWN"}, name


def test_a_write_into_a_value_that_the_file_makes_keeps_its_pass(
    tmp_path: Path, release_core: Path
) -> None:
    b = "const cache: any = {};\naddEventListener('load', () => { cache[k] = 1; });"
    document = _validate(tmp_path, release_core, b)
    assert document["frame"]["rules"]["REQUIRES"][1] == "PASS", document
