# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A write to a global through an alias of the global object gives no PASS (#880, #740).

Consumer: `archkeel validate` on a TypeScript project, through the release core. The contract
lets `a` use nothing. A file of `b` writes `open` onto the global object, and `a` calls
`window.open()` or `open()`. The call then reaches `b`, so the rule must give FAIL or UNKNOWN.
Each plant is one syntactic form of the write. The honest project must still give PASS, so that
the plants test the write and not a broken fixture.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from core_support import run
from corpus_support import commit_tree
from test_collector_false_pass_sources import BASE

from archkeel.cli import core_only

# A module file: `export {}` makes the file a module, so its top-level names stay local.
MODULE = "export {};\n"
WRITES = {
    "window": "window.open = () => {};",
    "globalThis": "globalThis.open = () => {};",
    "self": "self.open = () => {};",
    "frames": "frames.open = () => {};",
    "top": "top.open = () => {};",
    "parent": "parent.open = () => {};",
    "opener": "opener.open = () => {};",
    "window-window": "window.window.open = () => {};",
    "top-self": "top.self.open = () => {};",
    "globalThis-window": "globalThis.window.open = () => {};",
    "self-self": "self.self.open = () => {};",
    "frames-frames": "frames.frames.open = () => {};",
    "window-top": "window.top.open = () => {};",
    "window-parent": "window.parent.open = () => {};",
    "window-opener": "window.opener.open = () => {};",
    "frames-index": "frames[0].open = () => {};",
    "window-frames-index": "window.frames[0].open = () => {};",
    "self-frames-index": "self.frames[0].open = () => {};",
    "parent-frames-name": 'parent.frames["me"].open = () => {};',
    "computed-literal": 'window["open"] = () => {};',
    "computed-template": "window[`open`] = () => {};",
    "computed-unknown": "declare const key: string; window[key] = () => {};",
    "parent-computed": 'parent["open"] = () => {};',
    "assertion": "(window as any).open = () => {};",
    "parent-as": "(parent as any).open = () => {};",
    "satisfies": "(parent satisfies any).open = () => {};",
    "angle": "(<any>parent).open = () => {};",
    "non-null": "window!.open = () => {};",
    "parenthesized": "(top).open = () => {};",
    "delete": "delete (window as any).open;",
    "target-as": "(window.open as any) = () => {};",
    "target-non-null": "window.open! = () => {};",
    "target-angle": "(<any>window.open) = () => {};",
    "target-satisfies": "(window.open satisfies any) = () => {};",
    "target-parent-as": "(parent.open as any) = () => {};",
    "bare-non-null": "open! = () => {};",
    "bare-as": "(open as any) = () => {};",
    "default-view": "document.defaultView.open = () => {};",
    "default-view-assign": "Object.assign(document.defaultView!, { open: () => {} });",
    "content-window": "frameElement.contentWindow.open = () => {};",
    "escaped-member": "window.op\\u0065n = () => {};",
    "escaped-root": "p\\u0061rent.open = () => {};",
    "view-element-computed": "declare const k: string; (document.defaultView![0] as any)[k] = 1;",
    "timer-this-computed": (
        "declare const k: string; setTimeout(function (this: any) { this[k] = 1; });"
    ),
    "logical-window-computed": (
        "declare const k: string, x: any; (x || document.defaultView)[k] = 1;"
    ),
    "logical-window-escape": (
        "declare const x: any; Object.assign(x || document.defaultView, { open: 1 });"
    ),
    "function-this": "export function f(this: any) { this.open = () => {}; }",
    "timer-this": "setTimeout(function (this: any) { this.open = () => {}; });",
    "listener-this": 'addEventListener("load", function (this: any) { this.open = () => {}; });',
    "static-listener-this": (
        'class C { static m(this: any) { this.open = () => {}; } }\naddEventListener("load", C.m);'
    ),
    "alias-window": "const w = window; w.open = () => {};",
    "alias-parent": "const w = parent; w.open = () => {};",
    "alias-chain": "const w = top.window; w.open = () => {};",
    "assign": "Object.assign(window, { open: () => {} });",
    "assign-parent": "Object.assign(parent, { open: () => {} });",
    "define-property": 'Object.defineProperty(globalThis, "open", { value: () => {} });',
    "define-properties": "Object.defineProperties(top, { open: { value: () => {} } });",
    "reflect-set": 'Reflect.set(window, "open", () => {});',
    "reflect-define": 'Reflect.defineProperty(self, "open", { value: () => {} });',
    "compound": "(window as any).open ??= () => {};",
    "destructuring": "[parent.open] = [() => {}];",
    "object-destructuring": "({ open: top.open } = { open: () => {} });",
    "for-in": "for (parent.open in {}) {}",
    "increment": "(top as any).open++;",
    "indirect-eval": '(0, eval)("var open = 1");',
    "direct-eval": 'eval("window.open = 1");',
    "function-constructor": 'new Function("open = 1")();',
    "function-alias": 'const F = Function; F("open = 1")();',
    "constructor-chain": '({}).constructor.constructor("open = 1")();',
    "computed-constructor": '({})["constructor"]["constructor"]("open = 1")();',
    "timer-text": 'setTimeout("open = 1");',
    "interval-text": 'setInterval("open = 1");',
}
# A script (no `export`): its top-level declarations and `this` write to the global object.
SCRIPT_WRITES = {
    "script-var": "var open = 1;",
    "script-function": "function open() {}",
    "script-this": "this.open = 1;",
    "script-with": "with (window) { open = 1; }",
    "script-bare": "open = 1;",
    "script-parent": "parent.open = 1;",
    "script-alias-top": "var w = top; w.open = 1;",
    "script-this-chain": "this.window.open = 1;",
    "script-this-computed": 'this["open"] = 1;',
    "script-this-alias": "var g = this; g.open = 1;",
    "script-this-function": "function f(this: any) { this.open = 1; } f();",
    "script-this-return": "var g = (function (this: any) { return this; })(); g.open = 1;",
    "script-this-method": "var o = { m(this: any) { this.open = 1; } }; var m = o.m; m();",
    "script-delete-this": "delete (this as any).open;",
    "script-target-as": "(this.open as any) = 1;",
    "class-method-this": "class C { m() { this.open = 1; } }",
    "class-key-this": 'declare const k: string;\nclass K { [((this as any)[k] = 1, "k")]() {} }',
    "escaped-bare": "op\\u0065n = 1;",
    "script-enum": "enum open { A }",
    "script-namespace": "namespace open { export const x = 1; }",
}
# Forms that do not write onto the global object: a strict `this`, a local name, a type, a read.
EXACT = {
    "module-top-this": MODULE + "export const t = this;",
    "typeof-timer": MODULE + 'export const t = typeof setTimeout === "function";',
    "window-member-read": MODULE + "export const w = () => document.defaultView!.innerWidth;",
    "module-top-this-write": MODULE + "(this as any).open = 1;",
    "class-constructor-this": "class C { constructor() { (this as any).open = 1; } }",
    "class-static-this": "class D { static { (this as any).open = 1; } }",
    "class-field-this": "class E { f = () => { (this as any).open = 1; }; }",
    "local-parent": MODULE + "const parent = { open: 1 }; parent.open = 2;",
    "local-object": MODULE + "const o: any = {}; o.open = 1;",
    "timer-callback": MODULE + "setTimeout(() => {});",
    "timer-named": MODULE + "function tick() {}\nsetTimeout(tick, 100);",
    "interval-named": MODULE + "const poll = () => {};\nsetInterval(poll, 1000);",
    "timer-bind": MODULE + "export class T { t() {} go() { setTimeout(this.t.bind(this), 1); } }",
    "type-of-eval": MODULE + "export type E = typeof eval;",
    "constructor-name": MODULE + "export const n = (x: object) => x.constructor.name;",
    "this-constructor": MODULE + "export class C { m() { return (this.constructor as any).x; } }",
    "constructor-equal": MODULE + "export const p = (x: any) => x.constructor === Object;",
    "instanceof-function": MODULE + "export const f = (x: unknown) => x instanceof Function;",
    "function-prototype": MODULE + "export const call = Function.prototype.call;",
    "empty-html": MODULE + "export const clear = (e: any) => { e.innerHTML = ''; };",
    "data-call": MODULE + "const on: any = { a() {} }; export const go = (k: string) => on[k]();",
}
USES = {"window-call": "window.open();\n", "bare-call": "open();\n"}


def _project(tmp_path: Path, write: str, use: str) -> Path:
    root = tmp_path / "repo"
    files = {**BASE, "src/a/a.ts": use, "src/b/b.ts": write + "\n"}
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    commit_tree(root)
    return root


def _verdict(root: Path, binary: Path) -> tuple[int, dict[str, Any]]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: binary)
        return run("validate", "--root", str(root))


def _requires(document: dict[str, Any]) -> str | None:
    row = document.get("frame", {}).get("rules", {}).get("REQUIRES")
    return row[1] if row else None


def test_an_honest_project_gives_pass(tmp_path: Path, release_core: Path) -> None:
    root = _project(tmp_path, MODULE + "export const b = 1;", "export const a = 1;\n")
    code, document = _verdict(root, release_core)
    assert (code, document["status"]) == (0, "PASS"), document


@pytest.mark.parametrize("name", sorted(EXACT))
def test_a_form_that_writes_no_global_keeps_the_platform_global(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    code, document = _verdict(_project(tmp_path, EXACT[name], USES["window-call"]), release_core)
    assert (code, document["status"]) == (0, "PASS"), (name, document.get("frame"))


PLANTS = [(name, MODULE + text) for name, text in WRITES.items()] + list(SCRIPT_WRITES.items())


@pytest.mark.parametrize("use", sorted(USES))
@pytest.mark.parametrize(("name", "write"), PLANTS, ids=[name for name, _ in PLANTS])
def test_a_write_onto_the_global_object_gives_no_pass(
    tmp_path: Path, release_core: Path, name: str, write: str, use: str
) -> None:
    code, document = _verdict(_project(tmp_path, write, USES[use]), release_core)
    assert "refusal" not in document, (name, document.get("refusal"))
    assert document["status"] != "PASS", (name, use)
    assert code in {1, 2}, (name, use)
    status = _requires(document)
    assert status in {None, "FAIL", "UNKNOWN"}, (name, use, status)
