# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Inputs of size n for each construct class that the native syntax walk handles (AD-323).

Each shape is a function from a count n to the bytes of one source file. The size of the file
grows with n, and so does the number of the construct. `test_collector_native_scaling.py` times
the collector on n and 2n and bounds the ratio. A walk with a loop over the siblings, the
ancestors or the line of each node is quadratic on the shape that stresses it, and the ratio shows.

`COVERAGE` names, for each construct class, the shapes that hold it. `KIND_CLASSES` puts each
kind of `kinds.rs` into one class. `FIELD_COVERAGE` names the shapes for each fact of the dump and
each field of a definition. `test_collector_native_scaling.py` checks that every kind, every field
and every shape appears, so a new kind or a new fact without a shape fails there.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Shape:
    make: Callable[[int], bytes]
    # The count that takes about 0.15 s in the debug build; the test doubles it until it is slow
    # enough to measure.
    base: int
    suffix: str = ".ts"


def _join(template: str, n: int, sep: str = "\n") -> str:
    return sep.join(template.replace("{i}", str(i)) for i in range(n))


def _text(make: Callable[[int], str]) -> Callable[[int], bytes]:
    return lambda n: make(n).encode()


SHAPES: dict[str, Shape] = {
    # A run of comments or decorators in a body: the run is scanned for each child.
    "class-comment-run": Shape(_text(lambda n: "class C {\n" + "// c\n" * n + "m() {}\n}"), 171700),
    "class-decorator-run": Shape(_text(lambda n: "class C {\n" + "@d\n" * n + "m() {}\n}"), 49700),
    "enum-comment-run": Shape(_text(lambda n: "enum E {\n" + "// c\n" * n + "A\n}"), 180500),
    "interface-comment-run": Shape(
        _text(lambda n: "interface I {\n" + "// c\n" * n + "a: number;\n}"), 179400
    ),
    "class-decorated-members": Shape(
        _text(lambda n: "class C {\n" + _join("@d({i}) m{i}() {}", n) + "\n}"), 10000
    ),
    "class-decorator-comment-mix": Shape(
        _text(lambda n: "class C {\n" + "@d\n// c\n" * n + "m() {}\n}"), 37100
    ),
    # Members of a body.
    "class-methods": Shape(
        _text(lambda n: "class C {\n" + _join("m{i}(a: number): void {}", n) + "\n}"), 7700
    ),
    "class-fields": Shape(_text(lambda n: "class C {\n" + _join("f{i} = {i};", n) + "\n}"), 19900),
    "class-private-static": Shape(
        _text(
            lambda n: "class C {\n" + _join("static #p{i} = 1; private q{i}?: string;", n) + "\n}"
        ),
        8100,
    ),
    "class-implements": Shape(
        _text(lambda n: "class C extends B implements " + _join("I{i}", n, ", ") + " {}"), 56300
    ),
    "class-constructor-properties": Shape(
        _text(
            lambda n: "class C { constructor(" + _join("public a{i}: number", n, ", ") + ") {} }"
        ),
        11500,
    ),
    "class-string-names": Shape(
        _text(lambda n: "class C {\n" + _join("'a\\u{41}{i}'() {} '{i}'() {}", n) + "\n}"), 5800
    ),
    "enum-members": Shape(_text(lambda n: "enum E {\n" + _join("A{i} = {i},", n) + "\n}"), 22900),
    "interface-members": Shape(
        _text(lambda n: "interface I {\n" + _join("a{i}: number; b{i}?(x: T): U;", n) + "\n}"),
        7500,
    ),
    "type-union": Shape(_text(lambda n: "type T = " + _join("A{i}", n, " | ") + ";"), 65800),
    "overloads": Shape(
        _text(lambda n: _join("function f(a: number): void;", n) + "\nfunction f(a: any) {}"), 10100
    ),
    # Parameters and patterns.
    "parameters": Shape(
        _text(lambda n: "function f(" + _join("a{i}: number", n, ", ") + ") {}"), 21900
    ),
    "parameters-object-pattern": Shape(
        _text(lambda n: "function f({ " + _join("a{i}", n, ", ") + " }) {}"), 48100
    ),
    "parameters-array-pattern": Shape(
        _text(lambda n: "function f([" + _join("a{i} = {i}", n, ", ") + "]) {}"), 41000
    ),
    "parameters-defaults-rest": Shape(
        _text(lambda n: "function f(" + _join("a{i} = {i}", n, ", ") + ", ...r) {}"), 21000
    ),
    "variable-patterns": Shape(
        _text(lambda n: _join("const { a{i}, b{i}: [c{i}] } = o{i};", n)), 10100
    ),
    "pattern-nest": Shape(_text(lambda n: "var " + "[" * n + "x" + "]" * n + " = y;"), 75000),
    # Nests: scopes, frames and qualified names.
    "nested-functions": Shape(
        _text(lambda n: "".join(f"function f{i}(){{" for i in range(n)) + "}" * n), 17100
    ),
    "nested-classes": Shape(
        _text(lambda n: "".join(f"class C{i}{{m(){{" for i in range(n)) + "}}" * n), 9700
    ),
    "nested-namespaces": Shape(
        _text(lambda n: "".join(f"namespace N{i} {{ const k{i} = 1; " for i in range(n)) + "}" * n),
        14500,
    ),
    "nested-arrows": Shape(_text(lambda n: "const f = " + "a => " * n + "1;"), 73300),
    "nested-blocks-var": Shape(
        _text(lambda n: "function f() " + "{ " * n + "var a = 1;" + "}" * n), 106700
    ),
    "nested-blocks-let": Shape(_text(lambda n: "{ let a = 1; " * n + "}" * n), 23800),
    "nested-arrays": Shape(_text(lambda n: "const o = " + "[" * n + "]" * n + ";"), 84800),
    "member-chain": Shape(_text(lambda n: "a" + ".b" * n + ";"), 118800),
    "binary-chain": Shape(_text(lambda n: "const x = " + "1 + " * n + "1;"), 91400),
    "nested-jsx": Shape(
        lambda n: ("const x = " + "<a>" * n + "</a>" * n + ";").encode(), 50300, ".tsx"
    ),
    # Writes at depth: the write lookup climbs the frames.
    "writes-at-depth": Shape(
        _text(
            lambda n: (
                "import a from './a';\n"
                + "".join(f"function f{i}(){{ x = {i}; " for i in range(n))
                + "}" * n
            )
        ),
        10900,
    ),
    # Each function writes a name of its own that no frame binds: the lookup of each write climbs
    # the whole chain, and a memo that kept every climb held n squared entries (memory too).
    "writes-distinct-names": Shape(
        _text(
            lambda n: (
                "import a from './a';\n"
                + "".join(f"function f{i}(){{ x{i} = {i}; " for i in range(n))
                + "}" * n
            )
        ),
        12000,
    ),
    # Imported names, written in nests. Only the root binds an imported name, so a write of it was
    # the one that climbed the frames. A climb for each write, or an entry for each frame and name,
    # was quadratic in time and in memory.
    "writes-imports-all-at-bottom": Shape(
        _text(
            lambda n: (
                _join("import i{i} from './m{i}';", n)
                + "\n"
                + "".join(f"function f{i}(){{ " for i in range(n))
                + "".join(f"i{i} = {i}; " for i in range(n))
                + "}" * n
            )
        ),
        1600,
    ),
    "writes-import-at-own-depth": Shape(
        _text(
            lambda n: (
                _join("import i{i} from './m{i}';", n)
                + "\n"
                + "".join(f"function f{i}(){{ i{i} = {i}; " for i in range(n))
                + "}" * n
            )
        ),
        1600,
    ),
    "writes-same-import-at-depth": Shape(
        _text(
            lambda n: (
                "import a from './a';\n"
                + "".join(f"function f{i}(){{ a = {i}; " for i in range(n))
                + "}" * n
            )
        ),
        3000,
    ),
    "writes-imports-in-siblings": Shape(
        _text(
            lambda n: (
                _join("import i{i} from './m{i}';", n)
                + "\n"
                + _join("function g{i}() { i{i} = {i}; }", n)
            )
        ),
        1500,
    ),
    "writes-flat": Shape(
        _text(lambda n: "import a from './a';\n" + _join("x{i} = {i}; a++;", n)), 15800
    ),
    "rebound-names": Shape(_text(lambda n: _join("x{i} = {i};", n)), 30900),
    # Var hoisting and scope frames at one level.
    "var-hoisting": Shape(
        _text(lambda n: "function f() {\n" + _join("{ var a{i} = {i}; }", n) + "\n}"), 21500
    ),
    "for-in-frames": Shape(
        _text(lambda n: _join("for (var k{i} in o) {} for (let l{i} of o) {}", n)), 8100
    ),
    "catch-frames": Shape(_text(lambda n: _join("try {} catch ({ e{i} }) {}", n)), 18000),
    "switch-frames": Shape(
        _text(lambda n: "switch (x) {\n" + _join("case {i}: let s{i}; break;", n) + "\n}"), 20300
    ),
    "functions-flat": Shape(
        _text(lambda n: _join("function f{i}(a, b) { return a + b; }", n)), 7000
    ),
    "generators-async": Shape(
        _text(lambda n: _join("async function* g{i}() {} function* h{i}() {}", n)), 9000
    ),
    "function-expressions": Shape(
        _text(
            lambda n: _join(
                "const f{i} = function named{i}(a) {}; const g{i} = function* () {};", n
            )
        ),
        11400,
    ),
    "class-expressions": Shape(
        _text(lambda n: _join("const c{i} = class K{i} { m() {} };", n)), 10400
    ),
    # Imports, exports, re-exports, default exports.
    "imports-default": Shape(_text(lambda n: _join("import a{i} from './m{i}';", n)), 1000),
    "imports-named": Shape(
        _text(lambda n: _join("import { a{i}, type b{i}, c{i} as d{i} } from './m{i}';", n)), 900
    ),
    "imports-one-statement": Shape(
        _text(lambda n: "import { " + _join("a{i} as b{i}", n, ", ") + " } from './m';"), 22200
    ),
    "imports-namespace-require": Shape(
        _text(
            lambda n: _join("import * as n{i} from './m{i}'; import e{i} = require('./r{i}');", n)
        ),
        500,
    ),
    "exports-declarations": Shape(
        _text(
            lambda n: _join(
                "export const a{i} = {i}; export function f{i}() {} export class K{i} {}", n
            )
        ),
        4200,
    ),
    "exports-clause": Shape(
        _text(
            lambda n: _join("const a{i} = 1;", n) + "\nexport { " + _join("a{i}", n, ", ") + " };"
        ),
        13300,
    ),
    "reexports": Shape(
        _text(lambda n: _join("export { a{i} } from './m{i}'; export * from './n{i}';", n)), 500
    ),
    "reexports-local-names": Shape(
        _text(
            lambda n: _join(
                "function x{i}() {} class K{i} {}\n"
                "export { x{i} } from './m'; export { K{i} as L{i} } from './n';",
                n,
            )
        ),
        1000,
    ),
    "export-default-class": Shape(
        _text(lambda n: "export default class {\n" + _join("m{i}() {}", n) + "\n}"), 29700
    ),
    "constants-arrays": Shape(
        _text(lambda n: _join("const a{i} = [1, 'x', id] as const;", n)), 24000
    ),
    # Ambient declarations.
    "declare-global": Shape(
        _text(
            lambda n: (
                "declare global {\n"
                + _join("const g{i}: number; function h{i}(): void;", n)
                + "\n}"
            )
        ),
        11000,
    ),
    "declare-top-level": Shape(
        _text(lambda n: _join("declare const d{i}: number; declare function e{i}(): void;", n)),
        6800,
    ),
    # Object literals, arrow functions, template literals.
    "object-members": Shape(
        _text(
            lambda n: (
                "const o = {\n"
                + _join("a{i}: 1, m{i}() {}, [k{i}]: 2, get g{i}() { return 1; },", n)
                + "\n};"
            )
        ),
        7300,
    ),
    "arrows-flat": Shape(_text(lambda n: _join("const f{i} = (a) => a;", n)), 12700),
    "templates-flat": Shape(_text(lambda n: _join("const t{i} = `x${a}y${b}z`;", n)), 11300),
    "template-one": Shape(_text(lambda n: "const t = `" + "x${a}" * n + "`;"), 51700),
    # Lines: length, astral characters, line ends.
    "one-line-functions": Shape(
        _text(lambda n: "".join(f"function f{i}(a,b){{return a+b;}}" for i in range(n))), 7100
    ),
    "one-line-imports": Shape(
        _text(lambda n: "".join(f"import a{i} from './m';" for i in range(n))), 2300
    ),
    "one-line-astral": Shape(
        _text(lambda n: "".join(f"const s{i} = '😀'; function f{i}() {{}} " for i in range(n))),
        7400,
    ),
    "one-line-non-ascii": Shape(
        _text(lambda n: "".join(f"const é{i} = 'ü'; class Ñ{i} {{}} " for i in range(n))), 8300
    ),
    "one-line-then-ascii-lines": Shape(
        _text(
            lambda n: (
                "".join(f"function f{i}() {{}}" for i in range(n))
                + "\n"
                + _join("const c{i} = 1;", 200)
            )
        ),
        14300,
    ),
    "alternating-long-lines": Shape(
        _text(
            lambda n: "\n".join(
                (
                    "".join(f"function a{j}_{i}() {{}}" for j in range(40))
                    if i % 2 == 0
                    else "".join(f"const é{j}_{i} = '😀';" for j in range(40))
                )
                for i in range(n // 40 + 1)
            )
        ),
        15100,
    ),
    "crlf-lines": Shape(_text(lambda n: _join("const a{i} = 1;", n, "\r\n")), 20500),
    "lone-cr-lines": Shape(_text(lambda n: _join("const a{i} = 1;", n, "\r")), 20300),
    "unicode-line-separators": Shape(_text(lambda n: _join("const a{i} = 1;", n, " ")), 20100),
    "one-character-lines": Shape(_text(lambda n: ";\n" * n), 97600),
    "empty-lines": Shape(_text(lambda n: "\n" * n + "const a = 1;"), 1200000),
    "tabs-and-marks": Shape(
        _text(lambda n: "".join(f"\tconst a{i} = 'é'; " for i in range(n))), 16600
    ),
    "long-comment-line": Shape(_text(lambda n: "// " + "x" * (n * 8) + "\nconst a = 1;"), 150000),
    "long-string-line": Shape(
        _text(lambda n: "const s = '" + "😀" * n + "'; function f() {}"), 400000
    ),
    "triple-slash": Shape(_text(lambda n: _join("/// <reference path='./m{i}.d.ts' />", n)), 12000),
    # Statements, expressions and modifiers that no shape above holds.
    "statements-flat": Shape(
        _text(
            lambda n: _join(
                "function f{i}() { if (a === b) { return {i}; }"
                " else if (c !== d || e == f || g != h) { x += {i}; (p{i}) = 1; } }",
                n,
            )
        ),
        4000,
    ),
    "expressions-flat": Shape(
        _text(
            lambda n: _join(
                "const e{i} = new C(a!, b?.c, d as T, e satisfies U, null, true, false, 1.5,"
                " this, !x, -y, o[k{i}], delete o.k, typeof z, h(a, b));",
                n,
            )
        ),
        3500,
    ),
    "jsx-attributes": Shape(
        _text(lambda n: _join('const x{i} = <a b="c" ns:d={e} {...f}>{g}</a>;', n)), 8000, ".tsx"
    ),
    "class-static-accessors": Shape(
        _text(
            lambda n: (
                "class C {\n"
                + _join(
                    "static { x = {i}; } get g{i}() { return 1; } set g{i}(v) {} override m{i}() {}"
                    " readonly r{i} = 1;",
                    n,
                )
                + "\n}"
            )
        ),
        3000,
    ),
    "abstract-classes": Shape(
        _text(
            lambda n: _join(
                "abstract class A{i} { abstract m(): void; protected abstract p: number; }", n
            )
        ),
        6000,
    ),
    "declare-modules": Shape(
        _text(
            lambda n: _join(
                "declare module 'm{i}' { export const x: number; } module M{i} {}"
                " namespace A{i}.B.C {}",
                n,
            )
        ),
        5000,
    ),
    "import-alias-export-star": Shape(
        _text(lambda n: _join("export * as n{i} from './m{i}'; import A{i} = B.C{i};", n)), 2000
    ),
    "optional-rest-parameters": Shape(
        _text(lambda n: _join("function f{i}(a?: number, ...r: string[]) {}", n)), 6000
    ),
    "generics-and-type-queries": Shape(
        _text(
            lambda n: _join(
                "const t{i} = f<T, U>(x); type Q{i}<T> = typeof y; let v{i}: Q{i}<T>;", n
            )
        ),
        5000,
    ),
    "for-while-with": Shape(
        _text(
            lambda n: _join(
                "for (let i = 0; i < n; i++) { continue; } while (x) { break; }"
                " with (o{i}) { y = 1; }",
                n,
            )
        ),
        5000,
    ),
    "shorthand-and-assignment-patterns": Shape(
        _text(
            lambda n: _join(
                "const o{i} = { a, b, ...c }; ({ d = 1, e } = o{i}); const { f, g } = o{i};", n
            )
        ),
        4000,
    ),
    "interfaces-flat": Shape(
        _text(lambda n: _join("interface I{i} extends J{i}, K { a: number; }", n)), 8000
    ),
    "hashbang": Shape(
        _text(lambda n: "#!/usr/bin/env node\n" + _join("const a{i} = 1;", n)), 20000
    ),
    "require-calls": Shape(
        _text(lambda n: _join("const r{i} = require('./m{i}'); const d{i} = import('./d{i}');", n)),
        700,
    ),
    # Sites (PR 4.3a-2): the scope, the shadowed names and the free names of a site were found by
    # a climb over the ancestors for each node, and a path or a receiver text by a copy of a chain.
    "sites-calls-at-depth": Shape(
        _text(lambda n: "".join(f"function f{i}(){{ c{i}(g{i}); " for i in range(n)) + "}" * n),
        8000,
    ),
    "sites-calls-in-arrow-nest": Shape(
        _text(
            lambda n: (
                "const f = "
                + "".join(f"(p{i}) => {{ var v{i}; c{i}(p{i}, v{i}); return " for i in range(n))
                + "0"
                + "; }" * n
                + ";"
            )
        ),
        5000,
    ),
    "sites-nested-calls": Shape(_text(lambda n: "f(" * n + "x" + ")" * n + ";"), 60000),
    "sites-with-nest": Shape(_text(lambda n: "with (o) { " * n + "f();" + "}" * n), 30000),
    "sites-member-chain-call": Shape(_text(lambda n: "a" + ".b" * n + "();"), 100000),
    "sites-chained-calls": Shape(_text(lambda n: "a" + ".b()" * n + ";"), 20000),
    "sites-calls-with-chains": Shape(_text(lambda n: _join("a{i}.b.c.d(e{i}.f.g);", n)), 5000),
    "sites-new-expressions": Shape(
        _text(lambda n: _join("const v{i} = new A{i}.B(c{i});", n)), 6000
    ),
    "sites-publication-chain": Shape(
        _text(lambda n: "".join(f"window.p{i} = " for i in range(n)) + "1;"), 20000, ".js"
    ),
    "sites-computed-access": Shape(_text(lambda n: "a" + "[k]" * n + ";"), 60000),
    "sites-computed-calls": Shape(_text(lambda n: "a" + "[0]()" * n + ";"), 20000),
    "sites-subscript-flat": Shape(_text(lambda n: _join("a{i}[b{i}][c{i}](d{i});", n)), 6000),
    "sites-many-free-names": Shape(_text(lambda n: "f(" + _join("x{i}", n, ", ") + ");"), 40000),
    "sites-many-bound-names": Shape(
        _text(
            lambda n: _join("var v{i};", n, " ") + "\n" + _join("function g{i}() { v{i}(); }", n)
        ),
        4000,
    ),
    "sites-free-names-in-frames": Shape(
        _text(lambda n: _join("function g{i}(a{i}) { var b{i}; a{i}(b{i}, c{i}); }", n)), 4000
    ),
    "sites-args-wide": Shape(_text(lambda n: "f(" + _join("g{i}(h{i})", n, ", ") + ");"), 12000),
    "sites-escapes": Shape(
        _text(lambda n: _join("typeof w{i}; delete o{i}.p; x{i}++; f(g{i}, h{i});", n)), 3000
    ),
    "sites-many-shadowed-names": Shape(
        _text(
            lambda n: (
                "function f() { "
                + _join("var v{i};", n, " ")
                + " "
                + _join("v{i}();", n, " ")
                + " }"
            )
        ),
        12000,
    ),
    # n nested arrow functions that each declare a name, with n sites at the bottom: the names that
    # a site shadows are the union over the chain, and a set for each site was n squared entries.
    "sites-shadow-nest-arrows": Shape(
        _text(
            lambda n: (
                "const f = "
                + "".join(f"(p{i}) => {{ var v{i}; return " for i in range(n))
                + "["
                + _join("c{i}(v{i})", n, ", ")
                + "]"
                + "; }" * n
                + ";"
            )
        ),
        2500,
    ),
    "sites-comparisons-or-chain": Shape(
        _text(lambda n: "const r = " + " || ".join(f"x === 'v{i}'" for i in range(n)) + ";"), 9000
    ),
    "sites-comparisons-flat": Shape(_text(lambda n: _join("if (x{i} === 'a{i}') {}", n)), 8000),
    "sites-comparison-wrappers": Shape(
        _text(lambda n: "x === " + "(" * n + "'a'" + " as const)" * n + ";"), 9000
    ),
    "sites-switch-cases": Shape(
        _text(lambda n: "switch (x) {\n" + _join("case 'c{i}': y{i}(); break;", n) + "\n}"), 9000
    ),
    "sites-templates-comparisons": Shape(
        _text(lambda n: _join("x == `t{i}`; x != `u${y}{i}`; z === (`v{i}`);", n)), 6000
    ),
    "sites-in-decorator-run": Shape(
        _text(lambda n: "class C {\n" + _join("@d(f{i}())", n, "\n") + "\nm() {}\n}"), 15000
    ),
    "sites-in-decorator-comment-mix": Shape(
        _text(lambda n: "class C {\n" + _join("// c\n@d(f{i}())", n, "\n") + "\nm() {}\n}"), 9000
    ),
    "sites-after-comment-run": Shape(
        _text(lambda n: "class C {\n" + "// c\n" * n + "m(a = f()) { g(); }\n}"), 100000
    ),
    "sites-script-wrappers": Shape(
        _text(lambda n: _join("(function (window) { window.f{i}(w{i}); })(window);", n)),
        4000,
        ".js",
    ),
    "sites-script-wrapper-nest": Shape(
        _text(lambda n: "(function (window) { " * n + "window.f();" + " })(window);" * n),
        8000,
        ".js",
    ),
    "sites-script-publications": Shape(
        _text(lambda n: _join("window.a{i} = window.b{i} || g{i};", n)), 6000, ".js"
    ),
    "sites-iife-many-args": Shape(
        _text(
            lambda n: (
                "(function (" + _join("w{i}", n, ", ") + ") { })(" + _join("window", n, ", ") + ");"
            )
        ),
        30000,
        ".js",
    ),
    "sites-shorthand-properties": Shape(
        _text(lambda n: "var o = { " + _join("a{i}", n, ", ") + " };"), 30000, ".js"
    ),
    "sites-type-positions": Shape(
        _text(lambda n: "type T = " + "A<" * n + "B" + ">" * n + ";"), 50000
    ),
    "sites-jsx-names": Shape(_text(lambda n: _join("<a b={c{i}} d:e={f{i}} />;", n)), 5000, ".tsx"),
}


# Construct class -> shapes that hold it.
COVERAGE: dict[str, tuple[str, ...]] = {
    "classes": (
        "class-methods",
        "class-implements",
        "class-expressions",
        "abstract-classes",
        "class-static-accessors",
        "nested-classes",
    ),
    "class members and modifiers": (
        "abstract-classes",
        "declare-top-level",
        "class-fields",
        "class-private-static",
        "class-decorated-members",
        "class-static-accessors",
        "generators-async",
        "object-members",
        "class-string-names",
    ),
    "comment and decorator runs in a body": (
        "class-comment-run",
        "class-decorator-run",
        "class-decorator-comment-mix",
        "enum-comment-run",
        "interface-comment-run",
    ),
    "parameters": (
        "parameters",
        "parameters-defaults-rest",
        "optional-rest-parameters",
        "class-constructor-properties",
    ),
    "patterns": (
        "parameters-object-pattern",
        "parameters-array-pattern",
        "variable-patterns",
        "pattern-nest",
        "shorthand-and-assignment-patterns",
    ),
    "interfaces, enums and types": (
        "interface-members",
        "interfaces-flat",
        "enum-members",
        "type-union",
        "generics-and-type-queries",
        "overloads",
    ),
    "functions": (
        "functions-flat",
        "function-expressions",
        "generators-async",
        "arrows-flat",
        "nested-arrows",
        "nested-functions",
    ),
    "scopes and blocks": (
        "nested-blocks-var",
        "nested-blocks-let",
        "catch-frames",
        "for-in-frames",
        "switch-frames",
        "for-while-with",
        "statements-flat",
        "var-hoisting",
    ),
    "variables": ("constants-arrays", "var-hoisting", "variable-patterns"),
    "writes at depth": (
        "writes-at-depth",
        "writes-distinct-names",
        "writes-flat",
        "rebound-names",
        "statements-flat",
        "expressions-flat",
        "writes-imports-all-at-bottom",
        "writes-import-at-own-depth",
        "writes-same-import-at-depth",
        "writes-imports-in-siblings",
    ),
    "imports": (
        "imports-default",
        "imports-named",
        "imports-one-statement",
        "imports-namespace-require",
        "import-alias-export-star",
    ),
    "exports and re-exports": (
        "exports-declarations",
        "exports-clause",
        "reexports",
        "reexports-local-names",
        "export-default-class",
        "import-alias-export-star",
    ),
    "ambient declarations and namespaces": (
        "declare-global",
        "declare-top-level",
        "declare-modules",
        "nested-namespaces",
    ),
    "expressions": (
        "expressions-flat",
        "member-chain",
        "binary-chain",
        "object-members",
        "nested-arrays",
        "statements-flat",
    ),
    "literals": (
        "class-string-names",
        "templates-flat",
        "template-one",
        "expressions-flat",
        "long-string-line",
        "shorthand-and-assignment-patterns",
    ),
    "jsx": ("jsx-attributes",),
    "nests of jsx and the references of PR 4.2": ("nested-jsx", "require-calls"),
    "comments and the start of a file": ("class-comment-run", "hashbang", "triple-slash"),
    "type-only imports": ("imports-named",),
    "call sites at depth": (
        "sites-calls-at-depth",
        "sites-calls-in-arrow-nest",
        "sites-nested-calls",
        "sites-with-nest",
    ),
    "member chains": (
        "sites-member-chain-call",
        "sites-chained-calls",
        "sites-calls-with-chains",
        "sites-new-expressions",
        "sites-publication-chain",
    ),
    "computed access": ("sites-computed-access", "sites-computed-calls", "sites-subscript-flat"),
    "free names": (
        "sites-many-free-names",
        "sites-many-bound-names",
        "sites-free-names-in-frames",
        "sites-args-wide",
        "sites-escapes",
    ),
    "shadowed names": (
        "sites-many-shadowed-names",
        "sites-shadow-nest-arrows",
        "sites-calls-in-arrow-nest",
    ),
    "string comparisons in long chains": (
        "sites-comparisons-or-chain",
        "sites-comparisons-flat",
        "sites-comparison-wrappers",
        "sites-switch-cases",
        "sites-templates-comparisons",
    ),
    "sites in comment and decorator runs": (
        "sites-in-decorator-run",
        "sites-in-decorator-comment-mix",
        "sites-after-comment-run",
    ),
    "sites of a script": (
        "sites-script-wrappers",
        "sites-script-wrapper-nest",
        "sites-script-publications",
        "sites-iife-many-args",
        "sites-shorthand-properties",
    ),
    "sites in types and jsx": ("sites-type-positions", "sites-jsx-names"),
    "line shapes": (
        "one-line-functions",
        "one-line-imports",
        "one-line-astral",
        "one-line-non-ascii",
        "one-line-then-ascii-lines",
        "alternating-long-lines",
        "crlf-lines",
        "lone-cr-lines",
        "unicode-line-separators",
        "one-character-lines",
        "empty-lines",
        "tabs-and-marks",
        "long-comment-line",
    ),
}

# Each kind of `kinds.rs` (except `Other`) belongs to one construct class.
KIND_CLASSES: dict[str, tuple[str, ...]] = {
    "classes": (
        "ClassDeclaration Class ClassExpression ClassBody ClassHeritage ExtendsClause "
        "ImplementsClause AbstractClassDeclaration ClassStaticBlock"
    ).split(),
    "class members and modifiers": (
        "PublicFieldDefinition MethodDefinition Static Abstract Override Readonly Declare "
        "AccessibilityModifier PrivatePropertyIdentifier Get Set Async Asterisk Decorator "
        "ComputedPropertyName"
    ).split(),
    "parameters": (
        "FormalParameters RequiredParameter OptionalParameter RestParameter RestPattern Question"
    ).split(),
    "patterns": (
        "ArrayPattern ObjectPattern ObjectAssignmentPattern PairPattern AssignmentPattern "
        "ShorthandPropertyIdentifierPattern"
    ).split(),
    "interfaces, enums and types": (
        "InterfaceDeclaration InterfaceBody MethodSignature PropertySignature ExtendsTypeClause "
        "EnumDeclaration EnumAssignment TypeAliasDeclaration TypeAnnotation TypeArguments "
        "TypeParameter TypeQuery TypeIdentifier FunctionSignature"
    ).split(),
    "functions": (
        "FunctionDeclaration FunctionExpression GeneratorFunction GeneratorFunctionDeclaration "
        "ArrowFunction"
    ).split(),
    "scopes and blocks": (
        "StatementBlock CatchClause ForInStatement ForStatement SwitchBody SwitchCase "
        "WithStatement IfStatement ElseClause ReturnStatement"
    ).split(),
    "variables": "LexicalDeclaration VariableDeclaration VariableDeclarator Const Var".split(),
    "writes at depth": (
        "AssignmentExpression AugmentedAssignmentExpression UpdateExpression Delete "
        "ParenthesizedExpression"
    ).split(),
    "imports": (
        "ImportStatement ImportClause ImportSpecifier NamedImports NamespaceImport "
        "ImportRequireClause ImportAlias"
    ).split(),
    "exports and re-exports": (
        "ExportStatement ExportClause ExportSpecifier NamespaceExport Default"
    ).split(),
    "ambient declarations and namespaces": (
        "AmbientDeclaration InternalModule Module NestedIdentifier"
    ).split(),
    "expressions": (
        "CallExpression NewExpression MemberExpression SubscriptExpression Arguments "
        "BinaryExpression Equal NotEqual StrictEqual StrictNotEqual UnaryExpression Typeof "
        "AsExpression As SatisfiesExpression NonNullExpression OptionalChain "
        "OptionalChainOperator This Object Array Pair ExpressionStatement Program"
    ).split(),
    "literals": (
        "Identifier PropertyIdentifier ShorthandPropertyIdentifier Number String StringFragment "
        "EscapeSequence TemplateString TemplateSubstitution True False Null"
    ).split(),
    "jsx": "JsxAttribute JsxNamespaceName".split(),
    "comments and the start of a file": "Comment HashBangLine".split(),
    "type-only imports": ["Type"],
}

# Each fact of the dump and each field of a definition -> shapes that produce it.
FIELD_COVERAGE: dict[str, tuple[str, ...]] = {
    "definitions": ("class-methods", "functions-flat", "enum-members", "interfaces-flat"),
    "import_bindings": ("imports-named", "imports-default", "imports-namespace-require"),
    "module_exports": ("exports-declarations", "exports-clause", "reexports-local-names"),
    "rebound_names": ("rebound-names", "writes-flat"),
    "ambient_globals": ("declare-global",),
    "ambient_top_level": ("declare-top-level",),
    "module_file": ("exports-declarations", "imports-default"),
    "declaration_file": ("declare-top-level",),
    "script_mode": ("writes-at-depth", "rebound-names"),
    "script_bindings": ("variable-patterns", "var-hoisting", "nested-blocks-var"),
    "sites": ("sites-calls-at-depth", "sites-member-chain-call", "sites-computed-access"),
    "string_comparisons": ("sites-comparisons-or-chain", "sites-switch-cases"),
    "name": ("functions-flat",),
    "kind": ("class-methods", "enum-members", "type-union", "constants-arrays"),
    "span": ("one-line-astral", "tabs-and-marks", "crlf-lines", "long-comment-line"),
    "parent": ("nested-classes", "nested-functions", "class-methods"),
    "visibility": ("class-private-static", "exports-declarations"),
    "static": ("class-private-static",),
    "exported": ("exports-declarations", "exports-clause"),
    "annotation": ("class-fields", "interface-members", "constants-arrays"),
    "parameters": ("parameters", "parameters-defaults-rest", "optional-rest-parameters"),
    "returns": ("class-methods", "interface-members"),
    "bases": ("class-implements", "interfaces-flat"),
    "members": ("class-methods", "enum-members", "interface-members", "class-fields"),
    "decorators": ("class-decorated-members", "class-decorator-run"),
    "abstract": ("abstract-classes",),
    "members_complete": ("class-methods", "class-string-names"),
    "overload_signature": ("overloads",),
    "top_level": ("functions-flat", "nested-functions"),
    "signature_complete": ("parameters", "optional-rest-parameters"),
    "parent_line": ("nested-classes", "nested-functions"),
    "parent_column": ("nested-classes", "one-line-then-ascii-lines"),
    "is_async": ("generators-async",),
    "decorator_sources": ("class-decorated-members", "class-decorator-comment-mix"),
}

# Kinds of `_NodeKind` that the grammar never produces: `kinds_tests.rs` lists them too. No shape
# can hold them, so they are covered by name only.
NAME_ONLY = frozenset({"ClassExpression", "RestParameter"})
