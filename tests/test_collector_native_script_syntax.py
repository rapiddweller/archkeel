# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-340 (PR 4.3a-4): the script facts of the native syntax port equal the Python parser.

Consumer: `native/typescript/src/script*.rs`, through the test-only dump. The facts are the nine
script fields of `Syntax` (`script_globals`, `script_writes`, `script_aliases`,
`script_factories`, `script_source_writes`, `script_write_paths`,
`script_top_level_write_paths`, `script_destructures`, `script_namespaces`). The oracle is
`parse.parse()`, unmodified.

The grid has one source for each branch of a producer. Each source is read as a global script
(`.js`) and as a TypeScript module (`.ts`), so that the facts that a module must not produce are
compared as well. Mutated copies of the grid and the real scripts of the repository reach the
branches that a human would not write.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

GRID: dict[str, str] = {
    "return-publication": (
        "var Scene = (function () { function create() {} return { create }; })();\n"
    ),
    "return-publication-twice": (
        "var Scene = (function () { return { a }; function a() {} return { b }; })();\n"
    ),
    "assignment-publication": "window.Scene = { create: function () {} };\n",
    "assignment-members": "window.Lib = { run, stop };\nfunction run() {}\nfunction stop() {}\n",
    "duplicate-keys": "window.A = { a, a: 1 };\nfunction a() {}\n",
    "spread-member": "window.A = { ...x };\n",
    "comment-member": "window.A = { /* note */ a };\nfunction a() {}\n",
    "global-this": "globalThis.X = { f: function () {} };\nX.f();\n",
    "wrapper-alias": (
        "(function (global) { function layout() {} global.Layout = { layout }; })(window);\n"
    ),
    "wrapper-two-aliases": (
        "(function (w, g) { w.A = { a }; g.B = { b }; function a() {} function b() {} })"
        "(window, globalThis);\n"
    ),
    "wrapper-return-before": ("(function (g) { g.A = {}; return; g.B = {}; })(window);\n"),
    "wrapper-arrow": "((g) => { g.A = { a }; function a() {} })(window);\n",
    "wrapper-async": "(async function (g) { g.A = {}; })(window);\n",
    "wrapper-shadowed": "(function (window) { window.A = { a }; function a() {} })(window);\n",
    "wrapper-argument-bound": (
        "var other = 1;\n(function (g) { g.A = { a }; function a() {} })(other);\n"
    ),
    "wrapper-with": "(function (g) { with (x) { g.A = {}; } })(window);\n",
    "this-escape": "function f() { this.x = 1; }\nvar o = { f };\nwindow.O = o;\n",
    "this-global": "this.value = 1;\nthis.fn = function () {};\n",
    "eval-call": "eval('x');\nvar f = new Function('a', 'return a');\n",
    "reflect": "Reflect.set(window, 'x', 1);\nObject.defineProperty(window, 'y', {});\n",
    "timers": "setTimeout('x', 1);\nsetTimeout(function () {}, 1);\nsetInterval(() => 1, 5);\n",
    "proto": "obj.__proto__.x = 1;\nObject.setPrototypeOf(a, b);\n",
    "computed-write": "window['a' + b] = 1;\nwindow[k] = 2;\nwindow['lit'] = 3;\n",
    "computed-read": (
        "var f = function () {};\nf['call']();\nwindow[name]();\nnew (window[name])();\n"
    ),
    "indexed-effect": "var o = {};\no['constructor']['x'];\no['eval'];\n",
    "pair-pattern": "var { [key]: a, 'eval': b, 'x': c, 'a\\u0062': d } = o;\n",
    "delete-update": "delete window.x;\nx++;\n--y;\nfor (k in window) {}\nfor (var j in o) {}\n",
    "declarations": (
        "var a = 1, b;\nfunction c() {}\nclass D {}\nlet e = () => 1;\nconst window2 = 1;\n"
    ),
    "declaration-window": "var window = {};\nfunction globalThis() {}\n",
    "declaration-nested": "function outer() { var inner = 1; function g() {} }\n",
    "call-arguments": "foo(window);\nfoo(window.bar);\nfoo(bar.baz);\nfoo(window, globalThis.x);\n",
    "write-alias": "const w = window;\nw.a.b = 1;\nw.c = 2;\nvar v = w;\nv.d.e = 3;\n",
    "write-alias-chain": "var a = window;\nvar b = a;\nb.x.y = 1;\n",
    "write-alias-this": "var self2 = this;\nself2.a.b = 1;\n",
    "write-alias-unknown": "var u = make();\nu.a.b = 1;\n",
    "write-subscript": "window.a[b] = 1;\nobj.a[b] = 2;\nmake()[b] = 3;\nmake().x = 4;\n",
    "top-level-path": "var cfg = {};\ncfg.a = 1;\ncfg.b.c = 2;\nlet z = {};\nz.q = 1;\n",
    "bound-path": "function f() { var cfg = {}; cfg.a = 1; }\n",
    "source-members": (
        "function run() {}\nconst go = () => 1;\nconst data = { k: 1 };\n"
        "window.Lib = { run, go, data };\n"
    ),
    "source-members-written": ("function run() {}\nrun = other;\nwindow.Lib = { run };\n"),
    "source-members-twice": ("function run() {}\nfunction run() {}\nwindow.Lib = { run };\n"),
    "source-members-let": "let run = function () {};\nwindow.Lib = { run };\n",
    "source-members-late": "window.Lib = { run };\nconst run = () => 1;\n",
    "alias-member": "const log = window.logger;\nlog();\nlog(1);\n",
    "alias-member-read": "const log = window.logger;\nvar x = log;\n",
    "alias-member-chained": "const log = window.logger;\nlog.call();\n",
    "alias-member-optional": "const log = window?.logger;\nlog();\n",
    "alias-member-shadowed": "const log = window.logger;\nfunction f(log) { log(); }\nlog();\n",
    "alias-factory": ("const lib = window.make();\nlib.a();\nlib.b;\n"),
    "alias-factory-escape": ("const lib = window.make();\nlib.a();\nwindow.Out = { lib };\n"),
    "alias-factory-written": "const lib = window.make();\nlib.a = 1;\n",
    "alias-factory-bare": "const lib = window.make();\nvar y = lib;\n",
    "alias-factory-deep": "const lib = window.a.make();\nlib.a();\n",
    "alias-factory-optional": "const lib = window.make();\nlib?.a();\n",
    "alias-var": "var log = window.logger;\nlog();\n",
    "alias-escape-sibling": "const log = window.logger;\nwindow.Out = { log };\n",
    "alias-bad-name": "const lo\\u0067 = window.logger;\nlog();\n",
    "destructure": "const { a, b: c } = window.lib;\n",
    "destructure-rest": "const { a, ...rest } = window.lib;\n",
    "destructure-default": "const { a = 1 } = window.lib;\n",
    "destructure-rebound": "const { a } = window.lib;\nvar a;\n",
    "destructure-computed": "const { [k]: a } = window.lib;\n",
    "destructure-let": "let { a } = window.lib;\n",
    "destructure-not-root": "const { a } = lib.sub;\n",
    "factory": (
        "function make() { return { a, b: window.x.y, c: helper }; "
        "function a() {} const c2 = 1; }\n"
        "const helper = () => 1;\n"
    ),
    "factory-local": (
        "function make() { const inner = () => 1; function a() {} return { a, inner, other }; }\n"
    ),
    "factory-two-returns": (
        "function make() { if (x) { return { a }; } return { b }; "
        "function a() {} function b() {} }\n"
    ),
    "factory-async": "async function make() { return { a }; function a() {} }\n",
    "factory-nested": "function outer() { function make() { return { a }; } return make; }\n",
    "namespace": "var NS;\n(function (NS) { NS.a = 1; })(NS || (NS = {}));\n",
    "namespace-extra-write": (
        "var NS;\n(function (NS) { NS.a = 1; })(NS || (NS = {}));\nNS = other;\n"
    ),
    "namespace-window-write": ("var NS;\n(function (NS) { })(NS || (NS = {}));\nwindow.NS = 1;\n"),
    "namespace-wrong-name": "var NS;\n(function (X) { })(NS || (NS = {}));\n",
    "namespace-async": "var NS;\n(async function (NS) { })(NS || (NS = {}));\n",
    "namespace-initialised": "var NS = 1;\n(function (NS) { })(NS || (NS = {}));\n",
    "namespace-two": (
        "var A;\n(function (A) { })(A || (A = {}));\nvar B;\n(function (B) { })(B || (B = {}));\n"
    ),
    "namespace-spaced": "var NS;\n// note\n(function (NS) { })(NS || (NS = {}));\n",
    "scope-with": "with (x) { a = 1; }\nwindow.A = { b };\nfunction b() {}\n",
    "scope-catch": "try {} catch (e) { window.E = { e }; }\n",
    "scope-for": "for (let i = 0; i < 1; i++) { window.F = { i }; }\n",
    "scope-class": "class C { m() { this.x = 1; } static s() { this.y = 2; } }\n",
    "scope-static-block": "class C { static { this.z = 1; } }\n",
    "scope-generator": "function* g() { this.a = 1; }\nvar h = function* () {};\n",
    "scope-destructured-params": "function f({ a }, [b], c = 1, ...d) { a.x = 1; }\n",
    "typeof-escape": "typeof window;\nvar t = window;\nfoo(window);\nwindow.x;\n",
    "bad-identifier": "var a\\u{110000} = 1;\nvar b\\u0062 = 2;\n",
    "string-escape-key": "var o = { 'a\\u{110000}': 1 };\nvar p = { 'ok': 1 };\n",
    "typed": "export function f(a: number): number { return a; }\nwindow.x = 1;\n",
    "empty": "",
    "comments-only": "// nothing\n/* more */\n",
    "syntax-error": "window.A = { a: ;\nfunction (\n",
}

MODULE_ONLY: dict[str, str] = {
    "module-publication": "export const a = 1;\nwindow.Scene = { create: function () {} };\n",
    "module-declarations": "import x from './x';\nvar a = 1;\nfunction f() {}\nwindow.f = f;\n",
    "module-alias": "export {};\nconst log = window.logger;\nlog();\n",
    "module-return": "export {};\nvar S = (function () { return { a }; function a() {} })();\n",
}


def _write(root: Path, name: str, suffix: str, text: str) -> tuple[str, Path]:
    path = root / f"{name}{suffix}"
    path.write_text(text, encoding="utf-8")
    return f"src/{name}{suffix}", path


def _files(
    root: Path, sources: dict[str, str], suffixes: tuple[str, ...]
) -> list[tuple[str, Path]]:
    (root / "src").mkdir(parents=True, exist_ok=True)
    found = []
    for name, text in sources.items():
        for suffix in suffixes:
            path = root / "src" / f"{name}{suffix}"
            path.write_text(text, encoding="utf-8")
            found.append((f"src/{name}{suffix}", path))
    return found


def _mutate(rng: random.Random, text: str) -> str:
    """One edit of a source: cut a piece, repeat a piece, or swap a word for another of the file."""
    if len(text) < 4:
        return text
    words = [w for w in text.replace("(", " ").replace(")", " ").split() if w.isidentifier()]
    start = rng.randrange(len(text) - 2)
    end = min(len(text), start + rng.randrange(1, 12))
    match rng.randrange(4):
        case 0:
            return text[:start] + text[end:]
        case 1:
            return text[:end] + text[start:end] + text[end:]
        case 2 if words:
            return text[:start] + rng.choice(words) + text[end:]
        case _:
            return (
                text[:start] + rng.choice(["window", "this", "{", "}", ";", "=", "."]) + text[end:]
            )


SCRIPTS_OF_THE_REPOSITORY = (
    "src/archkeel/studio/ui",
    "tests/golden/typescript/sources",
    "fixtures",
)


@pytest.mark.parametrize("name", sorted(MODULE_ONLY))
def test_a_module_gives_no_publication(tmp_path: Path, dump_binary: Path, name: str) -> None:  # noqa: F811
    """Only a global script publishes: `script_globals` stays empty in a module."""
    from test_collector_native_syntax import _native

    files = _files(tmp_path, {name: MODULE_ONLY[name]}, (".ts",))
    syntax = _native(dump_binary, files)[0]["syntax"]
    assert syntax["script_globals"] == []
    assert syntax["script_aliases"] == []
