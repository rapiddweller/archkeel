# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Inputs of size n for each construct class that the native syntax walk handles (AD-323).

Each shape is a function from a count n to the bytes of one source file. The size of the file
grows with n, and so does the number of the construct. `test_collector_native_scaling.py` times
the collector on n and 2n and bounds the ratio. A walk with a loop over the siblings, the
ancestors or the line of each node is quadratic on the shape that stresses it, and the ratio shows.
The `sites-*` shapes live in `scaling_site_shapes.py` and the coverage tables in
`scaling_coverage.py`; `SHAPES` holds both sets of shapes.
"""

from __future__ import annotations

from scaling_shape_kit import Shape, as_bytes, join_lines
from scaling_site_shapes import SITE_PARTS, SITE_SHAPES, SITE_TIMED

__all__ = ["SHAPES", "SITE_PARTS", "SITE_TIMED", "Shape"]

_GENERAL: dict[str, Shape] = {
    # A run of comments or decorators in a body: the run is scanned for each child.
    "class-comment-run": Shape(
        as_bytes(lambda n: "class C {\n" + "// c\n" * n + "m() {}\n}"), 171700
    ),
    "class-decorator-run": Shape(
        as_bytes(lambda n: "class C {\n" + "@d\n" * n + "m() {}\n}"), 49700
    ),
    "enum-comment-run": Shape(as_bytes(lambda n: "enum E {\n" + "// c\n" * n + "A\n}"), 180500),
    "interface-comment-run": Shape(
        as_bytes(lambda n: "interface I {\n" + "// c\n" * n + "a: number;\n}"), 179400
    ),
    "class-decorated-members": Shape(
        as_bytes(lambda n: "class C {\n" + join_lines("@d({i}) m{i}() {}", n) + "\n}"), 10000
    ),
    "class-decorator-comment-mix": Shape(
        as_bytes(lambda n: "class C {\n" + "@d\n// c\n" * n + "m() {}\n}"), 37100
    ),
    # Members of a body.
    "class-methods": Shape(
        as_bytes(lambda n: "class C {\n" + join_lines("m{i}(a: number): void {}", n) + "\n}"), 7700
    ),
    "class-fields": Shape(
        as_bytes(lambda n: "class C {\n" + join_lines("f{i} = {i};", n) + "\n}"), 19900
    ),
    "class-private-static": Shape(
        as_bytes(
            lambda n: (
                "class C {\n" + join_lines("static #p{i} = 1; private q{i}?: string;", n) + "\n}"
            )
        ),
        8100,
    ),
    "class-implements": Shape(
        as_bytes(lambda n: "class C extends B implements " + join_lines("I{i}", n, ", ") + " {}"),
        56300,
    ),
    "class-constructor-properties": Shape(
        as_bytes(
            lambda n: (
                "class C { constructor(" + join_lines("public a{i}: number", n, ", ") + ") {} }"
            )
        ),
        11500,
    ),
    "class-string-names": Shape(
        as_bytes(lambda n: "class C {\n" + join_lines("'a\\u{41}{i}'() {} '{i}'() {}", n) + "\n}"),
        5800,
    ),
    "enum-members": Shape(
        as_bytes(lambda n: "enum E {\n" + join_lines("A{i} = {i},", n) + "\n}"), 22900
    ),
    "interface-members": Shape(
        as_bytes(
            lambda n: "interface I {\n" + join_lines("a{i}: number; b{i}?(x: T): U;", n) + "\n}"
        ),
        7500,
    ),
    "type-union": Shape(
        as_bytes(lambda n: "type T = " + join_lines("A{i}", n, " | ") + ";"), 65800
    ),
    "overloads": Shape(
        as_bytes(
            lambda n: join_lines("function f(a: number): void;", n) + "\nfunction f(a: any) {}"
        ),
        10100,
    ),
    # Parameters and patterns.
    "parameters": Shape(
        as_bytes(lambda n: "function f(" + join_lines("a{i}: number", n, ", ") + ") {}"), 21900
    ),
    "parameters-object-pattern": Shape(
        as_bytes(lambda n: "function f({ " + join_lines("a{i}", n, ", ") + " }) {}"), 48100
    ),
    "parameters-array-pattern": Shape(
        as_bytes(lambda n: "function f([" + join_lines("a{i} = {i}", n, ", ") + "]) {}"), 41000
    ),
    "parameters-defaults-rest": Shape(
        as_bytes(lambda n: "function f(" + join_lines("a{i} = {i}", n, ", ") + ", ...r) {}"), 21000
    ),
    "variable-patterns": Shape(
        as_bytes(lambda n: join_lines("const { a{i}, b{i}: [c{i}] } = o{i};", n)), 10100
    ),
    "pattern-nest": Shape(as_bytes(lambda n: "var " + "[" * n + "x" + "]" * n + " = y;"), 75000),
    # Nests: scopes, frames and qualified names.
    "nested-functions": Shape(
        as_bytes(lambda n: "".join(f"function f{i}(){{" for i in range(n)) + "}" * n), 17100
    ),
    "nested-classes": Shape(
        as_bytes(lambda n: "".join(f"class C{i}{{m(){{" for i in range(n)) + "}}" * n), 9700
    ),
    "nested-namespaces": Shape(
        as_bytes(
            lambda n: "".join(f"namespace N{i} {{ const k{i} = 1; " for i in range(n)) + "}" * n
        ),
        14500,
    ),
    "nested-arrows": Shape(as_bytes(lambda n: "const f = " + "a => " * n + "1;"), 73300),
    "nested-blocks-var": Shape(
        as_bytes(lambda n: "function f() " + "{ " * n + "var a = 1;" + "}" * n), 106700
    ),
    "nested-blocks-let": Shape(as_bytes(lambda n: "{ let a = 1; " * n + "}" * n), 23800),
    "nested-arrays": Shape(as_bytes(lambda n: "const o = " + "[" * n + "]" * n + ";"), 84800),
    "member-chain": Shape(as_bytes(lambda n: "a" + ".b" * n + ";"), 118800),
    "binary-chain": Shape(as_bytes(lambda n: "const x = " + "1 + " * n + "1;"), 91400),
    "nested-jsx": Shape(
        lambda n: ("const x = " + "<a>" * n + "</a>" * n + ";").encode(), 50300, ".tsx"
    ),
    # Writes at depth: the write lookup climbs the frames.
    "writes-at-depth": Shape(
        as_bytes(
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
        as_bytes(
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
        as_bytes(
            lambda n: (
                join_lines("import i{i} from './m{i}';", n)
                + "\n"
                + "".join(f"function f{i}(){{ " for i in range(n))
                + "".join(f"i{i} = {i}; " for i in range(n))
                + "}" * n
            )
        ),
        1600,
    ),
    "writes-import-at-own-depth": Shape(
        as_bytes(
            lambda n: (
                join_lines("import i{i} from './m{i}';", n)
                + "\n"
                + "".join(f"function f{i}(){{ i{i} = {i}; " for i in range(n))
                + "}" * n
            )
        ),
        1600,
    ),
    "writes-same-import-at-depth": Shape(
        as_bytes(
            lambda n: (
                "import a from './a';\n"
                + "".join(f"function f{i}(){{ a = {i}; " for i in range(n))
                + "}" * n
            )
        ),
        3000,
    ),
    "writes-imports-in-siblings": Shape(
        as_bytes(
            lambda n: (
                join_lines("import i{i} from './m{i}';", n)
                + "\n"
                + join_lines("function g{i}() { i{i} = {i}; }", n)
            )
        ),
        1500,
    ),
    "writes-flat": Shape(
        as_bytes(lambda n: "import a from './a';\n" + join_lines("x{i} = {i}; a++;", n)), 15800
    ),
    "rebound-names": Shape(as_bytes(lambda n: join_lines("x{i} = {i};", n)), 30900),
    # Var hoisting and scope frames at one level.
    "var-hoisting": Shape(
        as_bytes(lambda n: "function f() {\n" + join_lines("{ var a{i} = {i}; }", n) + "\n}"), 21500
    ),
    "for-in-frames": Shape(
        as_bytes(lambda n: join_lines("for (var k{i} in o) {} for (let l{i} of o) {}", n)), 8100
    ),
    "catch-frames": Shape(as_bytes(lambda n: join_lines("try {} catch ({ e{i} }) {}", n)), 18000),
    "switch-frames": Shape(
        as_bytes(lambda n: "switch (x) {\n" + join_lines("case {i}: let s{i}; break;", n) + "\n}"),
        20300,
    ),
    "functions-flat": Shape(
        as_bytes(lambda n: join_lines("function f{i}(a, b) { return a + b; }", n)), 7000
    ),
    "generators-async": Shape(
        as_bytes(lambda n: join_lines("async function* g{i}() {} function* h{i}() {}", n)), 9000
    ),
    "function-expressions": Shape(
        as_bytes(
            lambda n: join_lines(
                "const f{i} = function named{i}(a) {}; const g{i} = function* () {};", n
            )
        ),
        11400,
    ),
    "class-expressions": Shape(
        as_bytes(lambda n: join_lines("const c{i} = class K{i} { m() {} };", n)), 10400
    ),
    # Imports, exports, re-exports, default exports.
    "imports-default": Shape(as_bytes(lambda n: join_lines("import a{i} from './m{i}';", n)), 1000),
    "imports-named": Shape(
        as_bytes(
            lambda n: join_lines("import { a{i}, type b{i}, c{i} as d{i} } from './m{i}';", n)
        ),
        900,
    ),
    "imports-one-statement": Shape(
        as_bytes(lambda n: "import { " + join_lines("a{i} as b{i}", n, ", ") + " } from './m';"),
        22200,
    ),
    "imports-namespace-require": Shape(
        as_bytes(
            lambda n: join_lines(
                "import * as n{i} from './m{i}'; import e{i} = require('./r{i}');", n
            )
        ),
        500,
    ),
    "exports-declarations": Shape(
        as_bytes(
            lambda n: join_lines(
                "export const a{i} = {i}; export function f{i}() {} export class K{i} {}", n
            )
        ),
        4200,
    ),
    "exports-clause": Shape(
        as_bytes(
            lambda n: (
                join_lines("const a{i} = 1;", n)
                + "\nexport { "
                + join_lines("a{i}", n, ", ")
                + " };"
            )
        ),
        13300,
    ),
    "reexports": Shape(
        as_bytes(lambda n: join_lines("export { a{i} } from './m{i}'; export * from './n{i}';", n)),
        500,
    ),
    "reexports-local-names": Shape(
        as_bytes(
            lambda n: join_lines(
                "function x{i}() {} class K{i} {}\n"
                "export { x{i} } from './m'; export { K{i} as L{i} } from './n';",
                n,
            )
        ),
        1000,
    ),
    "export-default-class": Shape(
        as_bytes(lambda n: "export default class {\n" + join_lines("m{i}() {}", n) + "\n}"), 29700
    ),
    "constants-arrays": Shape(
        as_bytes(lambda n: join_lines("const a{i} = [1, 'x', id] as const;", n)), 24000
    ),
    # Ambient declarations.
    "declare-global": Shape(
        as_bytes(
            lambda n: (
                "declare global {\n"
                + join_lines("const g{i}: number; function h{i}(): void;", n)
                + "\n}"
            )
        ),
        11000,
    ),
    "declare-top-level": Shape(
        as_bytes(
            lambda n: join_lines("declare const d{i}: number; declare function e{i}(): void;", n)
        ),
        6800,
    ),
    # Object literals, arrow functions, template literals.
    "object-members": Shape(
        as_bytes(
            lambda n: (
                "const o = {\n"
                + join_lines("a{i}: 1, m{i}() {}, [k{i}]: 2, get g{i}() { return 1; },", n)
                + "\n};"
            )
        ),
        7300,
    ),
    "arrows-flat": Shape(as_bytes(lambda n: join_lines("const f{i} = (a) => a;", n)), 12700),
    "templates-flat": Shape(
        as_bytes(lambda n: join_lines("const t{i} = `x${a}y${b}z`;", n)), 11300
    ),
    "template-one": Shape(as_bytes(lambda n: "const t = `" + "x${a}" * n + "`;"), 51700),
    # Lines: length, astral characters, line ends.
    "one-line-functions": Shape(
        as_bytes(lambda n: "".join(f"function f{i}(a,b){{return a+b;}}" for i in range(n))), 7100
    ),
    "one-line-imports": Shape(
        as_bytes(lambda n: "".join(f"import a{i} from './m';" for i in range(n))), 2300
    ),
    "one-line-astral": Shape(
        as_bytes(lambda n: "".join(f"const s{i} = '😀'; function f{i}() {{}} " for i in range(n))),
        7400,
    ),
    "one-line-non-ascii": Shape(
        as_bytes(lambda n: "".join(f"const é{i} = 'ü'; class Ñ{i} {{}} " for i in range(n))), 8300
    ),
    "one-line-then-ascii-lines": Shape(
        as_bytes(
            lambda n: (
                "".join(f"function f{i}() {{}}" for i in range(n))
                + "\n"
                + join_lines("const c{i} = 1;", 200)
            )
        ),
        14300,
    ),
    "alternating-long-lines": Shape(
        as_bytes(
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
    "crlf-lines": Shape(as_bytes(lambda n: join_lines("const a{i} = 1;", n, "\r\n")), 20500),
    "lone-cr-lines": Shape(as_bytes(lambda n: join_lines("const a{i} = 1;", n, "\r")), 20300),
    "unicode-line-separators": Shape(
        as_bytes(lambda n: join_lines("const a{i} = 1;", n, " ")), 20100
    ),
    "one-character-lines": Shape(as_bytes(lambda n: ";\n" * n), 97600),
    "empty-lines": Shape(as_bytes(lambda n: "\n" * n + "const a = 1;"), 1200000),
    "tabs-and-marks": Shape(
        as_bytes(lambda n: "".join(f"\tconst a{i} = 'é'; " for i in range(n))), 16600
    ),
    "long-comment-line": Shape(
        as_bytes(lambda n: "// " + "x" * (n * 8) + "\nconst a = 1;"), 150000
    ),
    "long-string-line": Shape(
        as_bytes(lambda n: "const s = '" + "😀" * n + "'; function f() {}"), 400000
    ),
    "triple-slash": Shape(
        as_bytes(lambda n: join_lines("/// <reference path='./m{i}.d.ts' />", n)), 12000
    ),
    # Statements, expressions and modifiers that no shape above holds.
    "statements-flat": Shape(
        as_bytes(
            lambda n: join_lines(
                "function f{i}() { if (a === b) { return {i}; }"
                " else if (c !== d || e == f || g != h) { x += {i}; (p{i}) = 1; } }",
                n,
            )
        ),
        4000,
    ),
    "expressions-flat": Shape(
        as_bytes(
            lambda n: join_lines(
                "const e{i} = new C(a!, b?.c, d as T, e satisfies U, null, true, false, 1.5,"
                " this, !x, -y, o[k{i}], delete o.k, typeof z, h(a, b));",
                n,
            )
        ),
        3500,
    ),
    "jsx-attributes": Shape(
        as_bytes(lambda n: join_lines('const x{i} = <a b="c" ns:d={e} {...f}>{g}</a>;', n)),
        8000,
        ".tsx",
    ),
    "class-static-accessors": Shape(
        as_bytes(
            lambda n: (
                "class C {\n"
                + join_lines(
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
        as_bytes(
            lambda n: join_lines(
                "abstract class A{i} { abstract m(): void; protected abstract p: number; }", n
            )
        ),
        6000,
    ),
    "declare-modules": Shape(
        as_bytes(
            lambda n: join_lines(
                "declare module 'm{i}' { export const x: number; } module M{i} {}"
                " namespace A{i}.B.C {}",
                n,
            )
        ),
        5000,
    ),
    "import-alias-export-star": Shape(
        as_bytes(lambda n: join_lines("export * as n{i} from './m{i}'; import A{i} = B.C{i};", n)),
        2000,
    ),
    "optional-rest-parameters": Shape(
        as_bytes(lambda n: join_lines("function f{i}(a?: number, ...r: string[]) {}", n)), 6000
    ),
    "generics-and-type-queries": Shape(
        as_bytes(
            lambda n: join_lines(
                "const t{i} = f<T, U>(x); type Q{i}<T> = typeof y; let v{i}: Q{i}<T>;", n
            )
        ),
        5000,
    ),
    "for-while-with": Shape(
        as_bytes(
            lambda n: join_lines(
                "for (let i = 0; i < n; i++) { continue; } while (x) { break; }"
                " with (o{i}) { y = 1; }",
                n,
            )
        ),
        5000,
    ),
    "shorthand-and-assignment-patterns": Shape(
        as_bytes(
            lambda n: join_lines(
                "const o{i} = { a, b, ...c }; ({ d = 1, e } = o{i}); const { f, g } = o{i};", n
            )
        ),
        4000,
    ),
    "interfaces-flat": Shape(
        as_bytes(lambda n: join_lines("interface I{i} extends J{i}, K { a: number; }", n)), 8000
    ),
    "hashbang": Shape(
        as_bytes(lambda n: "#!/usr/bin/env node\n" + join_lines("const a{i} = 1;", n)), 20000
    ),
    "require-calls": Shape(
        as_bytes(
            lambda n: join_lines(
                "const r{i} = require('./m{i}'); const d{i} = import('./d{i}');", n
            )
        ),
        700,
    ),
}

#: Every shape, the `sites-*` shapes last.
SHAPES: dict[str, Shape] = {**_GENERAL, **SITE_SHAPES}
