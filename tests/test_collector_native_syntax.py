# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-323: the native walk reads the same syntax facts as `parse.parse()`.

Consumer: the later phases of the native collector, which build records on these facts. The oracle
is the unmodified Python `parse.parse()`. The `dump` feature of the native collector prints the
facts of each file as JSON, and this test compares them field by field with the fields of
`Syntax`: definitions, import bindings, module exports, rebound names, ambient names, the module
flags, the names bound at the top of the file, and the sites with the string comparisons (calls,
`new` expressions and references, with their scope, shadowed names, receiver, path and the free
and escape flags of a script). The release binary has no `dump` feature.
"""

from __future__ import annotations

import contextlib
import dataclasses
import enum
import json
import locale
import random
import subprocess
import tomllib
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from script_fields import SCRIPT_FIELDS

ROOT = Path(__file__).parents[1]
NATIVE = ROOT / "native"
STUDIO_UI = "src/archkeel/studio/ui"
FIXTURES = (
    "fixtures/H-typescript",
    "fixtures/H-uml-typescript",
    "fixtures/F-typescript-story",
    "fixtures/L-nest-realworld",
)
SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs")
# The fields of `Syntax` that the native walk produces.
FIELDS = (
    "definitions",
    "import_bindings",
    "module_exports",
    "rebound_names",
    "ambient_globals",
    "ambient_top_level",
    "module_file",
    "declaration_file",
    *SCRIPT_FIELDS,
    "sites",
    "string_comparisons",
)
# A private corpus: the folder of a local React UI. Only totals are printed.
PRIVATE_UI = "ARCHKEEL_PRIVATE_UI"
# The number of mutated copies of real files. The review of PR 4.2 used 3 000.
MUTANTS = "ARCHKEEL_SYNTAX_MUTANTS"

File = tuple[str, Path]


@contextlib.contextmanager
def _c_locale() -> Iterator[None]:
    """Run the oracle in the locale of the native process.

    The scanner of the TypeScript grammar calls C `iswspace`. The Python process takes its locale
    from the environment, and `iswspace(U+2028)` is true in `en_US.UTF-8` and false in `C`, the
    locale of the native collector. Then a line separator ends a statement for one parser and not
    for the other. A file without such a character gives the same tree in every locale.
    """
    saved = locale.setlocale(locale.LC_CTYPE)
    locale.setlocale(locale.LC_CTYPE, "C")
    try:
        yield
    finally:
        locale.setlocale(locale.LC_CTYPE, saved)


def _plain(value: object) -> object:
    """Turn a fact of `Syntax` into JSON data, so that a difference prints as text."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _in_document_order(bindings: object) -> object:
    """The import bindings with their statements in document order.

    `parse._import_bindings` reads the statements from `QueryCursor.captures`, which returns them
    in the order of a set of nodes. That order depends on the addresses of the nodes, so the
    native list cannot repeat it. The bindings of one statement stay together and in order.
    """
    assert isinstance(bindings, list)
    return sorted(bindings, key=lambda item: (item["span"]["line"], item["span"]["column"]))


def _native(binary: Path, files: list[File]) -> list[dict[str, object]]:
    request = "".join(json.dumps({"rel": rel, "file": str(path)}) + "\n" for rel, path in files)
    done = subprocess.run(
        [str(binary), "--dump"],
        input=request.encode(),
        capture_output=True,
        check=False,
        cwd=ROOT,
    )
    assert done.returncode == 0, done.stderr.decode(errors="replace")[:2000]
    return [json.loads(line) for line in done.stdout.splitlines()]


def _delta(path: str, native: object, python: object) -> Iterator[str]:
    """The first difference of each branch, with the path of its field."""
    if isinstance(native, dict) and isinstance(python, dict):
        for key in python.keys() | native.keys():
            yield from _delta(f"{path}.{key}", native.get(key), python.get(key))
    elif isinstance(native, list) and isinstance(python, list):
        if len(native) != len(python):
            yield f"{path}: {len(native)} native, {len(python)} python"
        for index, (mine, theirs) in enumerate(zip(native, python, strict=False)):
            yield from _delta(f"{path}[{index}]", mine, theirs)
    elif native != python:
        yield f"{path}: {native!r:.200} native, {python!r:.200} python"


class Result:
    """The totals of one comparison: differences and the facts that were compared."""

    def __init__(self) -> None:
        self.files = 0
        self.python_failed = 0
        self.python_failed_names: list[str] = []
        self.native_failed: list[str] = []
        self.differences: list[str] = []
        self.counts: Counter[str] = Counter()

    def add(self, rel: str, native: object, python: dict[str, object] | None) -> None:
        self.files += 1
        if python is None:
            self.python_failed += 1
            self.python_failed_names.append(rel)
            return
        for name in FIELDS:
            value = python[name]
            if isinstance(value, list):
                self.counts[name] += len(value)
        self.differences += list(_delta(rel, native, python))[:3]


def _sources(root: Path, under: str = ".") -> list[File]:
    base = root / under
    found = [
        path
        for path in base.rglob("*")
        if path.is_file() and path.name.endswith(SUFFIXES) and "node_modules" not in path.parts
    ]
    return sorted((path.relative_to(root).as_posix(), path) for path in found)


def _assert_equal(result: Result, expected_files: int | None = None) -> None:
    assert result.native_failed == []
    assert result.differences == [], "\n".join(result.differences[:20])
    if expected_files is not None:
        assert result.files == expected_files


# Statements that the random sources do not hold: scopes, hoisting and every kind of definition.
SYNTAX_PIECES = (
    "export class A<T> extends B<T> implements C, D { static s = 1; #p = 2; private q?: string; "
    "constructor(public a: number, private readonly b = 2) { super(); } get g() { return 1; } "
    "@dec() m(x: number, ...rest: string[]): void {} async *gen() {} 'quoted'() {} [k]() {} }",
    "abstract class Z { abstract f(): void; protected abstract readonly v: number; }",
    "export interface I extends J, K<string> { a: number; b?(x: T): U; readonly [k: string]: any }",
    "export enum E { A = 1, B, 'C' = 'c', D = A | B }",
    "declare enum DE { X }",
    "export type T<U> = U extends string ? 'a' : never;",
    "function over(a: number): void; function over(a: string): void; function over(a: any) {}",
    "export default function () {}",
    "export default class {}",
    "const c1 = 1, c2 = 'x', c3 = true, c4 = null, c5 = id, c6 = [1, 'a', id] as const;",
    "export const e1 = 2, e2 = [a, b];",
    "let l1 = 1; var v1 = 2; var [v2, v3] = arr; var { v4, v5: v6 } = obj;",
    "const { d1, d2: [d3] } = o, [d4, ...d5] = arr;",
    "function f(a, { b, c: [d] }, [e, ...g], h = 1, ...i) { var inner = 1; { function blk() {} } }",
    "const fn = function named(p) { return p; }; const ar = (q) => { let z = q; z = 2; };",
    "class K2 { static { var sv = 1; } m() { for (var fv of xs) {} for (let lv in ys) {} } }",
    "try { x(); } catch ({ message }) { y = message; } finally { w = 1; }",
    "for (var i = 0; i < 3; i++) { var fromLoop = i; } for (const [k, v] of m) {}",
    "label: for (;;) { break label; } switch (x) { case 1: let sw = 1; function sf() {} }",
    "with (obj) { prop = 1; } eval('x');",
    "declare global { const gv: number; var gw: string; function gf(): void; namespace GN {} }",
    "declare const dc: number; declare function df(): void; declare class DC {}",
    "declare module 'm';",
    "declare namespace NS.Inner { const x: number; } namespace Plain { export const y = 1; }",
    "module Legacy { var inner = 1; class InnerClass {} function innerFn() {} }",
    "import a1, { b1, type c1, d1 as e1 } from './m'; import * as ns1 from './n';",
    "import type T1 from './t'; import type { T2 } from './t'; import './side';",
    "import eq = require('./eq'); import alias = Some.Name;",
    "export { a1, b1 as renamed }; export { c1 }; export type { T2 }; export * from './re';",
    "export { x1 } from './re'; export * as star from './re';",
    "reassigned = 1; reassigned += 2; reassigned++; delete other.x; [pa, pb] = [1, 2];",
    "({ oa, ob: oc } = obj); for (fw in obj) {} for (fw of arr) {}",
    "function useImport() { a1 = 5; b1++; } ns1 = 3;",
    "const o2 = { method() {}, get prop() { return 1; }, [computed]: 1, arrow: () => {} };",
    "class WithDecorators { @a @b() prop = 1; @c() accessor = 2; @d method() {} }",
    "@Component({}) export class Decorated {}",
    "export @dec class Dec2 {}",
    "class Gen { *g() {} async am() {} static async *sg() {} 'constructor'() {} }",
    "class Esc { 'cons\\x74ructor'() {} \\u0061() {} }",
    "<div>{expr}</div>;",
    "x = <T,>(y: T) => y;",
    "export const arrowConst = (a: number): number => a, plainConst = 1;",
    "export = legacy;",
    "export as namespace Lib;",
    "type Obj = { a: number; b(): void; readonly c?: string };",
    "interface Merge { a: 1 } interface Merge { b: 2 }",
    "class Merge2 {} namespace Merge2 { export const k = 1; }",
    "function* gf() { yield 1; } async function af() {} async function* agf() {}",
    "({ a: { b: [c = 1, ...d] = [] } } = e);",
    "let { [key]: dyn } = obj;",
    "const \\u0061bc = 1;",
    "class Vis { protected pm() {} protected pf = 1; public pub = 2; private priv() {} }",
    "class Two { constructor() {} constructor(a: number) {} }",
    "class Ov { constructor(a: string); constructor(a: number); constructor(a: any) {} }",
    "class Dup { a = 1; a = 2; constructor(public a: number) {} }",
    "class PP { constructor(public x: number, protected y: string, private z?: boolean) {} }",
    "class Bad { constructor(public [a]: number) {} m(public q: number) {} }",
    "class Inj { constructor(@Inject() public svc: Service, readonly w = 1) {} }",
    "enum Ce { ['a'] = 1, b }",
    "class Acc { get x() { return 1; } set x(v) {} static get y() { return 2; } }",
    "class Idx { [key: string]: number; static [Symbol.iterator]() {} 123() {} 'str'() {} }",
    "interface Call { (a: number): string; new (b: string): Call; method?(): void }",
    "export abstract class Abs { abstract m(): void; protected abstract p: number; }",
    "export declare class Dcl { m(): void; static s: number }",
    "class Gn<T extends object = {}> extends Base<T>(mixin) implements I<T>, J {}",
    "import { zz } from './z'; export const zz = 1;",
    "export { yy }; const yy = 1; function yy() {}",
    "export default class Dflt {} export { Dflt as other };",
    # A decorator or a comment before a constructor with a parameter property: the run of siblings.
    "class D1 { @d constructor(public a: number) {} }",
    "class D2 { @d\n// c\n@e() /* b */ constructor(private readonly b = 1) {} m() {} }",
    "class D3 { // c\nconstructor(public a: number) {} @d m(x: number) {} }",
    "class D4 { @d @e f = 1; @d // c\n g() {} h() {} }",
    # The same name is written in two sibling scopes that bind it differently: a lookup that is
    # remembered by the name and not by the frame answers the second write with the first.
    "import a from './a';\nfunction f() { var a; a = 1; }\nfunction g() { a = 2; }",
    "import b from './b';\nfunction g() { b = 2; }\nfunction f() { var b; b = 1; }",
    "import c from './c';\nfunction f() { let c; { c = 1; } }\nfunction g() { { c = 2; } }",
    "import d from './d';\nfunction f() { function h() { d = 1; } var d; }\nfunction g() {d = 2;}",
    # A write of an imported name: the nearest binding decides, so the frames between count.
    "import m from './m';\nfunction f() { var q; function g() { q = 1; } }\n"
    "function h() { m = 2; }",
    "import a from './a';\nfunction f() { var a; function g() { a = 1; } }\n"
    "function h() { a = 2; }",
    "import a from './a';\nfunction f0() { let a; function f1() { function f2() { a = 1; } } }",
    "import a from './a';\nfunction f() { class C { m() { a = 1; } } }\n"
    "function g() { class a {} a = 2; }",
    "import e from './e';\ntry {} catch (e) { e = 1; }\n"
    "function f() { try {} catch (e) { } e = 2; }",
    "import p from './p';\nfunction f(p) { p = 1; }\nfunction g() { p = 2; }\n"
    "const k = (p) => { p = 3; };",
    "import d from './d';\ndeclare global { var d: number; }\n"
    "declare function df(d: number): void;\nd = 1;",
    "import n from './n';\nnamespace N { var n; n = 1; }\nnamespace M { n = 3; }\nn = 2;",
    "import w from './w';\nwith (o) { w = 1; }\nfunction f() { with (o) { var w; w = 2; } w = 3; }",
    "import a, { b, c as d } from './x';\n"
    "function f() { for (var b of x) { b = 1; } a++; d += 1; }",
    "import a from './a'; import b from './b';\n"
    "function f() { var b; { let a; a = 1; } b = 2; a = 3; }",
    # Sites: calls, `new`, references, receivers, paths, shadowed names, string comparisons.
    "function f(a, b = g(a)) { var loc = h.i.j(a, loc); loc = 2; return k[a].l(m?.n); }",
    "class S { x = 1; m(p) { this.x = p; this.y(p); super.z(); return new Other(p).run(); } }",
    "const o = { a, b: c, [d]: e, f() { return g(); }, get h() { return i; }, ...j };",
    "const arrow = (p, q) => { const inner = (r) => p(r, q, s); return inner(t); };",
    "const t1 = a.b.c.d, t2 = a['b'].c, t3 = a[b][c], t4 = (a.b).c, t5 = a().b.c, t6 = (a, b).c;",
    "if (kind === 'x' || 'y' !== kind || kind == (\"z\") || (kind as string) === `w` "
    "|| `a${b}` == k) {}",
    "switch (kind) { case 'a': case `b`: case (c): case 'd' as const: default: }",
    "x === 'one' && y !== ('two' as const) && z == ('three')! && w != 'four' satisfies string;",
    "x < 'no'; x + 'no'; x >= 'no'; x in 'no'; typeof x === 'string'; void 0 === 'u';",
    "let v: Foo.Bar<Baz> = <Qux>w; let u = w as Zed; let t = w satisfies Yes; type "
    "Alias = Other<One.Two>;",
    "typeof tq; let tq2: typeof imp.member; function ft<T extends Cons = Def>(x: T): Ret<T> {}",
    "function sh(a) { var b; { let c; function d() { return a + b + c + e; } } return d; }",
    "function outer() { var o1; return function () { var i1; return () => { var i2; "
    "return o1 + i1 + i2; }; }; }",
    "const meth = { m() { var q; return q + r; } }; class WithExpr { f = class { m() "
    "{ return n; } }; }",
    "namespace NS { var n1 = 1; export function nf() { return n1 + n2; } } module M2 { x(); }",
    "try { a(); } catch (e) { b(e); } finally { c(); } for (const i of xs) { d(i); } "
    "for (k in o) { e(k); }",
    "label: while (a) { b(); } do { c(); } while (d); if (e) f(); else g();",
    "(function (window) { var z = window.foo; z(1); window.bar = z; })(window);",
    "(function (w, g) { w.a = 1; g.b(w); })(window, globalThis);",
    "(() => { window.a = 1; })(); (async () => { window.b = 2; })(); !function () { "
    "window.c = 3; }();",
    "var w1 = (function (window) { return window.q; })(window);",
    "window.pub = 1; globalThis.pub2 = window.src; window.nested.deep = 2; self.sf = 3;",
    "window.f(1); window['g'](2); globalThis.h.i(3); window.a.b.c = d.e;",
    "delete window.x; typeof window.y; window.z++; window.w += 1; [window.v] = [1];",
    "with (obj) { f(g); h.i(j); } function wf() { with (o) { return k; } }",
    "const { da, db: dc } = window.src, [dd] = globalThis.arr, de = window.x.y;",
    "var sx = { a, b }; var { pa, pb } = sx; ({ pc, pd } = sx); f({ ea, eb });",
    '<A b={c} d="e" f:g={h}>{i}<J.K l={m.n} />{...o}</A>;',
    "@dec(arg) class Dc { @inj(tok) prop = other; @on('x') m(@p() a) { return a; } }",
    "new a.b.C(d); new (e.f)(); new g(h)(i); new j; new k.l;",
    "a?.b?.(c); a?.[b]; a!.b!.c(); (a as any).b(); (<any>a).c(); a.b!(); a.b?.c!();",
    "const dflt = (x = f(y), { z = g(x) } = {}) => x + z; function dg(p = h(p)) {}",
    "export default function (a) { return b(a); } export const ex = (c) => d(c);",
    "enum En { A = f(), B = C.D, E = 'e' } declare function df(a: Tp): Rt;",
    "abstract class Ab { abstract m(a: Tp): Rt; static s = ab(); constructor(private "
    "p = cd()) { ef(p); } }",
    "interface If { m(a: Tp): Rt; p: Ot<Pt>; readonly q?: Ur } declare module 'dm' { "
    "function dmf(): void; }",
    "declare global { function gf(a: Tp): void; } var gv = gg(); gg.hh = ii;",
    "a(b(c(d(e)))); f(g)(h)(i); j.k(l).m(n).o(p); (q, r)(s); t`u${v}w`; x.y`z`;",
    "var a1 = 1, a2 = f(a1), a3 = new G(a2), a4 = g.h(a3), [a5] = i(a4), { a6 } = j(a5);",
    "let cl = class Named { m() { return Named; } }; let fe = function nm() { return nm; };",
    # A re-export names no local binding: x and K stay private and not exported.
    "function x() {}\nclass K {}\nexport { x } from './m';\nexport { K as KK } from './n';",
)


def _mutants(files: list[File], count: int) -> list[tuple[str, bytes]]:
    """Seeded damage to real files: cuts, deleted spans, stray tokens and moved lines."""
    rng = random.Random(880)
    stray = (b"}", b"{", b"(", b"))", b"`${", b"<", b"/*", b"'", b"\\", b"class", b"=>", b"@")
    found: list[tuple[str, bytes]] = []
    for index in range(count):
        rel, path = files[rng.randrange(len(files))]
        data = path.read_bytes()
        cut = rng.randrange(len(data) + 1)
        match rng.randrange(5):
            case 0:
                data = data[:cut]
            case 1:
                data = data[:cut] + data[cut + rng.randrange(1, 200) :]
            case 2:
                data = data[:cut] + rng.choice(stray) + data[cut:]
            case 3:
                lines = data.split(b"\n")
                at = rng.randrange(len(lines))
                data = b"\n".join([*lines[: at + 1], lines[at], *lines[at + 1 :]])
            case _:
                lines = data.split(b"\n")
                one, two = rng.randrange(len(lines)), rng.randrange(len(lines))
                lines[one], lines[two] = lines[two], lines[one]
                data = b"\n".join(lines)
        found.append((f"m{index}/{rel}", data))
    return found


def _shape(name: str, count: int) -> bytes:
    """Files whose cost grows with the line length or the depth: a minified file and nests."""
    match name:
        case "one-line":
            return b"".join(b"function f%d(a,b){return a+b;}" % index for index in range(count))
        case "nested-functions":
            return b"".join(b"function f%d(){" % index for index in range(count)) + b"}" * count
        case "nested-classes":
            return b"class C%d{m(){" * count % tuple(range(count)) + b"}}" * count
        case _:
            raise AssertionError(name)


SHAPES = ("one-line", "nested-functions", "nested-classes")


def test_deeply_nested_patterns_give_their_names(tmp_path: Path, dump_binary: Path) -> None:
    depth = 30_000
    path = tmp_path / "pattern.ts"
    path.write_bytes(b"var " + b"[" * depth + b"x" + b"]" * depth + b" = y;\nvar z = 1;")
    reply = _native(dump_binary, [("src/pattern.ts", path)])[0]
    assert "syntax" in reply, reply
    assert "z" in reply["syntax"]["script_bindings"]  # type: ignore[index]


def _column_cases() -> dict[str, bytes]:
    """Lines that stress the UTF-16 column table (lines over 256 bytes) and the 1 600-byte cut.

    A column counts UTF-16 units: an astral character is two. The table is built for a long line
    and must restart for each line. An excerpt is the first 400 characters of the node, cut from
    its first 1 600 bytes. Every case has a definition after the character that matters.
    """
    letter = "\U0001d4d0"  # an astral letter that a name can hold
    pad = "/*" + "a" * 300 + "*/ "
    cases = {
        # The first astral character starts at byte 1 599 (2 + 1 595 + 2 bytes of the comment).
        "astral-at-byte-1599": ("/*" + "a" * 1595 + "*/" + "\U0001f600 function f() {}").encode(),
        "astral-at-byte-1600": ("/*" + "a" * 1596 + "*/" + "\U0001f600 function f() {}").encode(),
        "astral-after-pad": (pad + "\U0001f600" * 5 + " function f() {} class K {}").encode(),
        "astral-many-definitions": (
            pad + "".join(f"const s{i} = '\U0001f600'; function f{i}() {{}} " for i in range(40))
        ).encode(),
        "name-of-401-astral-letters": (
            f"class {letter * 401} {{}}\nfunction {letter * 401}() {{}}"
        ).encode(),
        "name-of-399-astral-letters": (
            f"class {letter * 399} {{}}\nclass {letter * 400} {{}}"
        ).encode(),
        "name-of-400-ascii-letters": (f"class {'a' * 400} {{}}\nclass {'b' * 401} {{}}").encode(),
        # A member name is the text of its span: 400 four-byte letters are 1 600 bytes.
        "member-named-by-401-astral-letters": (
            f"class K {{ {letter * 401}() {{}} {letter * 400} = 1; }}\n"
            f"interface I {{ {letter * 402}: number; }}\nenum E {{ {letter * 401} }}"
        ).encode(),
        "excerpt-with-two-byte-letters": (f"class {'é' * 450} {{}}").encode(),
        "excerpt-of-long-ascii": ("function f(" + "a, " * 400 + ") {}").encode(),
        "alternating-long-lines": "\n".join(
            (pad + f"function a{i}() {{}}")
            if i % 2 == 0
            else (pad + "\U0001f600" * 9 + f"function b{i}() {{}}")
            for i in range(9)
        ).encode(),
        "alternating-then-short-line": (
            pad + "\U0001f600 const a = 1;\nconst b = 2;\n" + pad + "const c = 3;"
        ).encode(),
        "tabs-and-combining": (
            pad + "\t\t" + "e\u0301" * 20 + " function f() {}\n\t" + pad + "\u0301function g() {}"
        ).encode(),
        "crlf-lines": "\r\n".join(
            pad + "\U0001f600 " + f"function f{i}() {{}}" for i in range(4)
        ).encode(),
        "lone-cr-lines": "\r".join(
            pad + "\U0001f600 " + f"function f{i}() {{}}" for i in range(4)
        ).encode(),
        "line-separators": "\u2028".join(
            pad + "\U0001f600 " + f"function f{i}() {{}}" for i in range(4)
        ).encode(),
        "invalid-utf8-in-long-line": (
            pad.encode()
            + b"\xff\xfe\xf0\x9f function f() {}\n"
            + pad.encode()
            + b"\xe2\x80 class K {}"
        ),
        "cut-inside-a-character": (
            "/*" + "a" * 1590 + "*/ " + "\U0001f600" * 3 + " class K {}"
        ).encode(),
        "long-line-then-crlf-ascii": (pad + "function f() {}\r\n" + "function g() {}\r\n").encode(),
        "table-boundary-255-256-257": "\n".join(
            "/*" + "a" * (width - 2) + "*/" + "\U0001f600 function f() {}"
            for width in (252, 253, 254, 255, 256, 257, 258)
        ).encode(),
    }
    return cases


def test_the_dump_binary_holds_the_markers(dump_binary: Path) -> None:
    # The control of the test above: the markers are in the binary that has the feature.
    data = dump_binary.read_bytes()
    assert b"--dump" in data
    assert b"dump request is not JSON" in data


def test_two_runs_give_the_same_bytes(tmp_path: Path, dump_binary: Path) -> None:
    files = _sources(ROOT, STUDIO_UI)[:40] + _sources(ROOT / FIXTURES[3])[:40]
    request = "".join(json.dumps({"rel": rel, "file": str(path)}) + "\n" for rel, path in files)
    runs = {
        subprocess.run(
            [str(dump_binary), "--dump"], input=request.encode(), capture_output=True, check=True
        ).stdout
        for _ in range(4)
    }
    assert len(runs) == 1


def test_the_release_binary_has_no_dump_feature(native_binary: Path) -> None:
    # `dump` is not a default feature, so the wheel build and `cargo build` do not compile it.
    manifest = tomllib.loads((NATIVE / "typescript" / "Cargo.toml").read_text())
    assert manifest["features"] == {"dump": []}
    data = native_binary.read_bytes()
    # Field names of `Syntax` can stay in debug information, so the markers are texts that only
    # `dump.rs` and `main.rs` hold when the feature is on.
    assert b"--dump" not in data
    assert b"dump request is not JSON" not in data
    done = subprocess.run(
        [str(native_binary), "--dump"], input=b"", capture_output=True, check=False
    )
    assert done.returncode != 0
    assert done.stdout == b""
