# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-323: the native walk reads the same syntax facts as `parse.parse()`.

Consumer: the later phases of the native collector, which build records on these facts. The oracle
is the unmodified Python `parse.parse()`. The `dump` feature of the native collector prints the
facts of each file as JSON, and this test compares them field by field with the fields of
`Syntax`: definitions, import bindings, module exports, rebound names, ambient names, the module
flags and the names bound at the top of the file. The release binary has no `dump` feature.
"""

from __future__ import annotations

import contextlib
import dataclasses
import enum
import json
import locale
import os
import random
import subprocess
import time
import tomllib
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path

import pytest
from test_collector_native_imports import (
    COMMONJS,
    CONFIGS,
    PACKAGES,
    SOURCES,
    SPECIFIERS,
    _imports_of,
    _links,
    _pathological,
    _random_source,
    _write,
)

from archkeel.analyzer.typescript import parse
from archkeel.ir.facts_codec import encode_request
from archkeel.ir.protocol import (
    CollectionRequest,
    ProtocolVersion,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
)

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
    "script_mode",
    "script_bindings",
)
# A private corpus: the folder of a local React UI. Only totals are printed.
PRIVATE_UI = "ARCHKEEL_PRIVATE_UI"
# The number of mutated copies of real files. The review of PR 4.2 used 3 000.
MUTANTS = "ARCHKEEL_SYNTAX_MUTANTS"

File = tuple[str, Path]


@pytest.fixture(scope="session")
def dump_binary(native_binary: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The collector built with the test-only `dump` feature, in a target directory of its own."""
    assert native_binary.is_file()
    cargo = shutil.which("cargo") or "cargo"
    target = NATIVE / "target" / "dump"
    built = subprocess.run(
        [cargo, "build", "--locked", "--features", "dump", "--target-dir", str(target)],
        cwd=NATIVE,
        capture_output=True,
        text=True,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    name = "archkeel-typescript-collector" + (".exe" if os.name == "nt" else "")
    copy = tmp_path_factory.mktemp("native-dump") / name
    shutil.copy2(target / "debug" / name, copy)
    return copy


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


def _python(rel: str, data: bytes) -> dict[str, object] | None:
    """The facts of the oracle; `None` where it fails on the depth of the tree."""
    try:
        syntax = parse.parse(rel, data)
    except RecursionError:
        return None
    facts = {name: _plain(getattr(syntax, name)) for name in FIELDS}
    facts["import_bindings"] = _in_document_order(facts["import_bindings"])
    return facts


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


def compare(binary: Path, files: Iterable[File]) -> Result:
    """Compare the dump of the native collector with `parse.parse()` for each file."""
    listed = [(rel, path) for rel, path in files]
    result = Result()
    replies = _native(binary, listed)
    with _c_locale():
        for (rel, path), reply in zip(listed, replies, strict=True):
            assert reply["rel"] == rel
            if "syntax" not in reply:
                result.native_failed.append(f"{rel}: {reply.get('error')}")
                continue
            native = reply["syntax"]
            native["import_bindings"] = _in_document_order(native["import_bindings"])
            result.add(rel, native, _python(rel, path.read_bytes()))
    return result


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


@pytest.mark.parametrize("path", [*FIXTURES, STUDIO_UI])
def test_fixture_syntax_equals_the_python_parser(dump_binary: Path, path: str) -> None:
    root = ROOT / path
    files = _sources(root)
    assert len(files) >= 2
    result = compare(dump_binary, files)
    _assert_equal(result, len(files))
    # The comparison is not empty: these trees hold definitions and import bindings.
    assert result.counts["definitions"] > 0
    assert result.counts["import_bindings"] > 0
    assert result.python_failed == 0


def test_the_resolution_grid_syntax_equals_the_python_parser(
    tmp_path: Path, dump_binary: Path
) -> None:
    importer = _imports_of(SPECIFIERS)
    files = {
        **PACKAGES,
        **SOURCES,
        "tsconfig.json": CONFIGS["node10"],
        "src/importer.ts": importer,
        "src/importer.mts": importer,
        "src/importer.cts": importer,
        "src/sub/deep.ts": _imports_of(["./x", "../util", "pkg-a", "@app/x"]),
    }
    _write(tmp_path, files)
    result = compare(dump_binary, _sources(tmp_path))
    _assert_equal(result)
    assert result.counts["import_bindings"] >= 3 * len(SPECIFIERS)


def test_symlinked_sources_syntax_equals_the_python_parser(
    tmp_path: Path, dump_binary: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.ts").write_text("export const s = 1;\n")
    root = tmp_path / "repo"
    _write(
        root,
        {
            "src/real.ts": "export const r = 1;\n",
            "src/dir/x.ts": "export const x = 1;\n",
            "src/main.ts": _imports_of(["./link", "./dirlink/x", "./escape"]),
            "vendor/linked-pkg/index.js": "",
            "node_modules/.keep": "",
        },
    )
    (root / "node_modules").mkdir(exist_ok=True)
    (outside / "package.json").write_text("{}")
    _links(root, outside)
    names = ("src/real.ts", "src/dir/x.ts", "src/main.ts", "src/link.ts", "src/dirlink/x.ts")
    files = [(rel, root / rel) for rel in names]
    assert all(path.exists() for _, path in files)
    assert (root / "src/link.ts").is_symlink()
    result = compare(dump_binary, files)
    _assert_equal(result, len(names))
    assert result.counts["definitions"] >= 4


def test_random_sources_syntax_equals_the_python_parser(tmp_path: Path, dump_binary: Path) -> None:
    rng = random.Random(880)
    files: dict[str, str] = {"tsconfig.json": COMMONJS}
    for index in range(240):
        suffix = rng.choice([".ts", ".tsx", ".js", ".jsx", ".mts", ".cts"])
        head = "export {};\n" if suffix in (".js", ".jsx") else ""
        files[f"src/fuzz/f{index}{suffix}"] = head + _random_source(rng)
    _write(tmp_path, files)
    result = compare(dump_binary, _sources(tmp_path))
    _assert_equal(result, 240)


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


def test_syntax_pieces_equal_the_python_parser(tmp_path: Path, dump_binary: Path) -> None:
    rng = random.Random(881)
    files: dict[str, str] = {}
    for index, piece in enumerate(SYNTAX_PIECES):
        suffix = ".tsx" if "<div>" in piece else ".ts"
        files[f"src/p{index}{suffix}"] = piece + "\n"
    for index in range(300):
        suffix = rng.choice([".ts", ".tsx", ".js", ".mts", ".cts", ".d.ts", ".mjs", ".cjs"])
        body = "\n".join(rng.choice(SYNTAX_PIECES) for _ in range(rng.randint(2, 10)))
        if rng.random() < 0.5:
            body = "".join(rng.choice([body, ""]) for _ in range(1))
        files[f"src/mix{index}{suffix}"] = body + "\n"
    _write(tmp_path, files)
    result = compare(dump_binary, _sources(tmp_path))
    _assert_equal(result, len(files))
    assert result.counts["definitions"] > 500
    assert result.counts["rebound_names"] > 20
    assert result.counts["module_exports"] > 0


def test_mutated_sources_syntax_equals_the_python_parser(tmp_path: Path, dump_binary: Path) -> None:
    pieces = {f"p{index}.ts": piece for index, piece in enumerate(SYNTAX_PIECES)}
    real = _sources(ROOT, STUDIO_UI) + _sources(ROOT / FIXTURES[0]) + _sources(ROOT / FIXTURES[3])
    pieces_dir = tmp_path / "pieces"
    _write(pieces_dir, pieces)
    seeds = [*real, *_sources(pieces_dir)]
    count = int(os.environ.get(MUTANTS, "600"))
    written: list[File] = []
    for index, (rel, data) in enumerate(_mutants(seeds, count)):
        path = tmp_path / "mutants" / f"{index}{Path(rel).suffix}"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
        written.append((f"src/m{index}{Path(rel).suffix}", path))
    result = compare(dump_binary, written)
    _assert_equal(result, count)
    assert result.python_failed == 0


def test_hostile_sources_give_facts_where_python_fails_on_depth(
    tmp_path: Path, dump_binary: Path
) -> None:
    # Python recurses in `_walk` and stops with a RecursionError near a depth of 1 000. The native
    # walk is iterative and gives facts for the same tree (AD-323). Every other file is equal.
    files: list[File] = []
    for name, data in _pathological().items():
        path = tmp_path / name
        path.write_bytes(data)
        files.append((f"src/{name}", path))
    deep = {
        "deep-pattern.ts": b"const " + b"[" * 3000 + b"x" + b"]" * 3000 + b" = y;",
        "deep-object.ts": b"const " + b"{ a: " * 2000 + b"x" + b" }" * 2000 + b" = y;",
        "deep-class.ts": b"class A { m() { " * 800 + b"} }" * 800,
        "deep-functions.js": b"(function(){" * 3000 + b"})()" * 3000,
        "deep-assign.ts": b"a = " * 4000 + b"1;",
    }
    for name, data in deep.items():
        path = tmp_path / name
        path.write_bytes(data)
        files.append((f"src/{name}", path))
    result = compare(dump_binary, files)
    assert result.native_failed == []
    assert result.differences == [], "\n".join(result.differences[:20])
    assert result.files == len(files)
    # The deep files are the only ones that the oracle cannot read, and it cannot read at least one.
    deep_names = {f"src/{name}" for name in (*deep, "deep-parens.ts", "deep-arrays.ts")}
    deep_names |= {"src/deep-types.ts", "src/deep-blocks.ts"}
    assert result.python_failed_names
    assert set(result.python_failed_names) <= deep_names


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


@pytest.mark.parametrize("name", SHAPES)
def test_pathological_shapes_equal_the_python_parser(
    tmp_path: Path, dump_binary: Path, name: str
) -> None:
    # Python is quadratic on these shapes (614 s for 40 000 functions on one line) and stops with a
    # RecursionError on deep nests, so the oracle runs on sizes that it can read.
    files: list[File] = []
    for count in (1, 2, 7, 60, 200 if name == "one-line" else 90):
        path = tmp_path / f"{name}-{count}.ts"
        path.write_bytes(_shape(name, count))
        files.append((f"src/{path.name}", path))
    result = compare(dump_binary, files)
    _assert_equal(result, len(files))
    assert result.python_failed == 0
    assert result.counts["definitions"] > 100


# The time of the collector process (the debug build) grows linearly with the size: time(2n) over
# time(n) is about 2 for a linear walk and about 4 for a quadratic one. The facts of each definition
# once decoded the line before it and the whole text of its node, and kept the qualified name of
# each scope as a copy of its whole chain. In the release build 40 000 functions on one line took
# 33.6 s, 4 000 nested classes 14.9 s and 8 000 nested classes 61 s (1.3 GB), against 0.2 s and
# under 0.1 s for the collector of PR 4.2. The process, not the dump, is timed: the dump prints the
# qualified name of each definition, and that output is quadratic in the depth in Python too.
# `test_collector_native_scaling.py` runs the same method on every construct class.
PATHOLOGICAL = (("one-line", 20_000), ("nested-functions", 4_000), ("nested-classes", 4_000))
# The ratio of the times, and an absolute guard against a machine that is far too slow.
RATIO_BOUND = 3.0
GUARD_SECONDS = 60.0


def _process_time(binary: Path, root: Path, name: str, count: int) -> float:
    (root / "tsconfig.json").write_text('{"include":["src"]}')
    (root / "src").mkdir(exist_ok=True)
    (root / "src/a.ts").write_bytes(_shape(name, count))
    payload = encode_request(
        CollectionRequest(
            SnapshotInput(str(root), "a" * 40, False),
            SourceScope(("src",), "app"),
            TypeScriptSettings("tsconfig.json", False),
            ProtocolVersion.V8,
        )
    )
    best = float("inf")
    for _ in range(3):
        begin = time.perf_counter()
        done = subprocess.run([str(binary)], input=payload, capture_output=True, check=False)
        best = min(best, time.perf_counter() - begin)
        assert done.returncode == 0, done.stderr[-300:]
    return best


@pytest.mark.parametrize(("name", "count"), PATHOLOGICAL)
def test_pathological_shapes_grow_linearly(
    tmp_path: Path, native_binary: Path, name: str, count: int
) -> None:
    first = _process_time(native_binary, tmp_path, name, count)
    second = _process_time(native_binary, tmp_path, name, 2 * count)
    assert second < GUARD_SECONDS, f"{name} {2 * count}: {second:.1f} s"
    assert second / first < RATIO_BOUND, f"{name} {count}: {first:.2f} s, 2n {second:.2f} s"


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


def test_the_column_table_and_the_excerpt_cut_equal_the_python_parser(
    tmp_path: Path, dump_binary: Path
) -> None:
    files: list[File] = []
    for name, data in _column_cases().items():
        path = tmp_path / f"{name}.ts"
        path.write_bytes(data)
        files.append((f"src/{name}.ts", path))
    result = compare(dump_binary, files)
    _assert_equal(result, len(files))
    assert result.python_failed == 0
    # Each case holds definitions; the comparison is not empty.
    assert result.counts["definitions"] >= len(files)


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


def test_a_private_corpus_syntax_equals_the_python_parser(dump_binary: Path) -> None:
    folder = os.environ.get(PRIVATE_UI)
    if not folder or not Path(folder).is_dir():
        pytest.skip(f"{PRIVATE_UI} names no folder")
    root = Path(folder)
    files = _sources(root)
    result = compare(dump_binary, files)
    # Totals only: a private corpus must not leak a name into a report.
    print(
        f"private corpus: {result.files} files, {len(result.differences)} differences, "
        f"{result.python_failed} oracle failures, "
        + ", ".join(f"{name} {count}" for name, count in sorted(result.counts.items()))
    )
    assert result.native_failed == []
    assert len(result.differences) == 0
