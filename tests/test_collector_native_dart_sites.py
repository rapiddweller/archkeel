# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#880 PR 8 slice 3b: the native Dart sites of each file equal the sites of Python `parse`.

Consumer: the Dart resolver, which reads the references, calls, creations, bindings and scopes
of each file. The gate compares the `--dump-syntax` JSON of the native collector with
`dataclasses.asdict(parse(content))`, sites included, byte for byte. The differences of AD-376
are tested one by one: the depth of each recursive Python walk and the work limit.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import install_rust_toolchain

ROOT = Path(__file__).parents[1]


def _load(name: str) -> object:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"tools/{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load("dart_discovery_parity")
parity = _load("dart_syntax_parity")

CASES: dict[str, str | bytes] = {
    "closures.dart": "void f() { var g = () { var h = (int x) => x; return h(1); }; g(); }\n",
    "local_functions.dart": "void f() { int g(int a) { int h() => a; return h(); } g(1); }\n",
    "cascades.dart": "void f(A a) { a..b = 1..c(); a?.d?.e(); a!.f; a?..g(); }\n",
    "compound.dart": "void f(List<int> l, int i) { l[0] += 1; l[i] = 2; x ??= 3; y -= z; }\n",
    "creations.dart": (
        "var a = new A<int>.named(1, b: 2);\nconst c = C();\n"
        "final d = A.b();\nvar e = const p.D<int>(x, y: [1, 2,]);\n"
    ),
    "typed_receivers.dart": (
        "class A { B b; C? c; void m(D d, e) { E x = E(); var y = 1;\n"
        "b.x; c?.y(); d[0]; x.z = 1; y.w; e.v(); A.s; } }\n"
    ),
    "prefixes.dart": "import 'a.dart' as p;\nvoid f(p.T t) { p.g(); p.A(); t.p; var q = p.v; }\n",
    "constructors.dart": (
        "class A extends B { final int x; A(this.x, {super.key}) : super();\n"
        "A.named(int y) : x = y; factory A.f() => A(1); const A.c([this.x = 0]);\n"
        "factory A.r(int a) = A.named; }\n"
    ),
    "accessors.dart": (
        "class A { int _x = 0; int get x => _x; set x(int v) { _x = v; }\n"
        "A operator +(A o) => this; bool operator ==(Object o) => o is A; }\n"
    ),
    "type_sites.dart": (
        "class A<T extends B> extends C<D> with E, F<G> implements H<I>, J {\n"
        "  K Function(L) k; M<N?>? m; void n<O>(P<O> p) {} }\n"
        "typedef Q = R<S>;\nmixin T on U implements V {}\n"
    ),
    "enum_extension.dart": (
        "enum E with M implements I { a(1), b(2); const E(this.v); final int v;\n"
        "int g() => v.abs(); }\nextension X on String { int get n => length + y(); }\n"
        "extension type Id(int v) { int twice() => v * 2; }\n"
    ),
    "comments.dart": "void f() { var x = g( /* c */ a , // d\n b, ); }\n",
    "interpolation.dart": "void f() { var s = 'a${b.c(d)}e$g'; var t = \"${h?.i}\"; }\n",
    "type_arguments.dart": (
        "void f() { var m = <String, List<int>>{}; var b = a < c && d > e;\n"
        "var g = h<int, List<Map<K, V>>>(1); }\n"
    ),
    "generic_calls.dart": "void f() { g<int>(1); a.b<C>(); d<E>.new; F<G>.h(); }\n",
    "bang.dart": "void f() { a!.b!.c(); d![0]!.e; (f as G).h(); i is J; }\n",
    "nested_parameters.dart": (
        "void f(void g(int x), [int Function(String s)? h, k = 1]) {}\n"
        "void m({required int a, int b = 2, void Function() c = _d}) {}\n"
    ),
    "default_closure.dart": "void f({int Function() g = _d, h = const [1]}) {}\nint _d() => 0;\n",
    "top_level_closure.dart": "final x = () { return y(); }();\nvar z = (int a) => a.b;\n",
    "switch.dart": (
        "int f(Object x) { var r = switch (x) { 1 => a(), int(:var v) => v.b, _ => c.d };\n"
        "switch (x) { case A(a: var q): q.r(); default: s(); } return r; }\n"
    ),
    "records.dart": "void f() { var r = (a: 1, b: c()); var (d, e) = r; r.a.g(); r.$1; }\n",
    "async.dart": (
        "Future<void> f() async { await a.b(); await for (var c in d()) { c.e; } }\n"
        "Iterable<int> g() sync* { yield h(); yield* i(); }\n"
    ),
    "vertical_tab.dart": "void f() { x\x0b=\x0b1; y \x0c+= 2; z\t=\n3; }\n",
    "unicode.dart": "void f() { var été = ünïcode.call(été); }\n",
    "combining_mark.dart": "void f() { var x = a ͅb + ²; }\n",
    "long_chain.dart": "void f() { a.b.c.d.e.f().g.h().i[0].j?.k!.l(); }\n",
    "callees.dart": "void f() { (a)(b); c()(); d[0](); e.f()(g); (h ?? i).j(); }\n",
    "static_types.dart": "void f() { List<int>.filled(1, 0); A<B>.c(); Map.of({}); }\n",
    "broken_call.dart": "void f() { g(a, ; h.i( }\n",
    "broken_body.dart": "class A { void m() { var x = y(\n",
    "async_block.dart": "f() async { { var a = b(); } } g() { { } { c(); } }\n",
    "multi_variable.dart": "void f() { int a = 1, b, c = d.e; late final x = y; var (p, q) = r; }\n",
    "loops.dart": (
        "void f(List<int> l) { for (var i = 0; i < l.length; i++) { l[i]; }\n"
        "for (final e in l) { e.g(); } while (h()) {} do { j(); } while (k); }\n"
    ),
    "catch.dart": "void f() { try { g(); } on E catch (e, s) { e.x; s.y(); } finally { h(); } }\n",
    "this_super.dart": "class A extends B { int a = 0; void m() { this.a = b; super.c(); this.d(); } }\n",
    "conditional_member.dart": "void f() { a?.b = c; d?.e ??= f; g?[0] = h; }\n",
    "typed_index.dart": "class A { List<B> d = []; void m() { d[0].x; d.first.y(); } }\n",
    "literal_receivers.dart": "void f() { 'a'.b(); 1.c; [2].d(); {3}.e; true.f; null?.g; }\n",
    "collections.dart": "void f() { var x = [...a, if (b) c() else d, for (var e in g) e.h, ...?i]; }\n",
    "invocation.dart": "void f() { (){ g(); }(); (() => h())(); }\n",
    "tear_offs.dart": "void f() { var a = A.new; var b = A<int>.named; var c = d.e; var g = h; }\n",
    "carriage_returns.dart": "void f() {\r  var a = b();\r\n  c.d = e;\r}\r",
    "astral.dart": "void f() { var s = '\U0001f600\U0001f600'; t.u(s); }\n",
    "invalid_utf8.dart": b"void f() { var s = '\xff\xfe'; t.u(s); v(\xe9); }\n",
    "method_then_field.dart": "class A { void m() {} int x = y(); final z = w.v; A(); int q = r(); }\n",
    "getter_then_field.dart": "class A { int get g => 1; static final h = i(); set j(int k) {} var l = m; }\n",
    "function_then_variable.dart": "void f() {} var x = g(); int h(int a) => a; final y = h(1).z;\n",
    "mixin_on.dart": "mixin M on A { void m() { a.b(); } }\n",
    "directives.dart": (
        "library a.b;\nimport 'a.dart' show B, C hide D;\nexport 'e.dart';\npart 'f.dart';\n"
        "void g() { B(); C.d(); }\n"
    ),
    "operators.dart": "void f() { var a = b + c * d / e ~/ g % h ?? i || j && k == l != m <= n >= o; }\n",
    "constructor_initializers.dart": (
        "class A { final int a; final B b; A(int x) : a = x.abs(), b = B(x), assert(x > 0); }\n"
    ),
    "function_types.dart": "void Function(int) f = (x) {}; typedef G = int Function(String);\n",
    "nested_classes_in_closure.dart": "var f = () { var g = () { var h = () => i.j(); }; };\n",
    # Three levels of parameters: the outermost one gives the scope, not the innermost one.
    "nested_parameters_deep.dart": "void f(void g(void h(int y))) {}\n",
    # A closure parameter takes the name of the nearest signature before the body, not the first.
    "closure_after_function.dart": "void a() {} void b() { var c = (int x) => x; }\n",
    # A comma before a dot stays; only a closer removes it.
    "dot_after_comma.dart": "void g() { var x = f(a, .b); }\n",
    # A typed parameter with the name of an import prefix is no typed receiver.
    "prefix_shadow.dart": "import 'a.dart' as p;\nvoid f(int p) { p.x; p.y(); }\n",
    # A statement inside a closure on the left side ends the search for the assignment.
    "use_boundary.dart": "void f() { a[() { b; return c; }()] = 1; }\n",
    # An error tree holds a typed definition outside a local declaration: no typed receiver.
    "definition_outside_declaration.dart": "void f() { A x = b } void g() { x.y(); }\n",
}


@pytest.fixture(scope="module")
def binary() -> Path:
    cargo = shutil.which("cargo")
    if cargo is None:
        if os.environ.get("CI"):
            pytest.fail("CI must provide cargo for the native collector tests.")
        pytest.skip("cargo is not installed; install Rust to test changes in native/.")
    install_rust_toolchain(cargo)
    built: Path = parity.build(release=False)  # type: ignore[attr-defined]
    return built


def _write(root: Path, name: str, content: str | bytes) -> Path:
    path = root / name
    path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return path


def _native(binary: Path, path: Path) -> dict[str, object]:
    [row] = parity.native_rows(binary, [path])  # type: ignore[attr-defined]
    value: dict[str, object] = row["syntax"]
    return value


def test_there_are_at_least_forty_hostile_site_sources() -> None:
    assert len(CASES) >= 40


@pytest.mark.parametrize("name", sorted(CASES))
def test_a_hostile_source_gives_the_python_sites(binary: Path, tmp_path: Path, name: str) -> None:
    path = _write(tmp_path, name, CASES[name])
    [(text, _, value)] = parity.native_syntax(binary, [path])  # type: ignore[attr-defined]
    expected, _ = parity.python_syntax(path.read_bytes())  # type: ignore[attr-defined]
    assert expected is not None
    # A bool first: pytest would compare two long texts with difflib, which takes minutes.
    same = text == expected
    assert same, parity.difference(expected, text)  # type: ignore[attr-defined]
    assert value["sites"], "each case must give sites"  # type: ignore[index]


# The recursive Python walks of the site code: `_walk` and `_source_tokens`. A nest of each kind
# reaches the tree depth where Python stops; `_walk` in `_parse_tree` stops first (AD-376).
NESTS = {
    "parentheses": ("void f() { var x = ", "(", "1", ")", "; }\n"),
    "closures": ("void f() { var x = ", "() { return ", "1", "; }", "; }\n"),
    "local_functions": ("void f() { ", "void g() { ", "", "}", " }\n"),
}


def _nest(name: str, levels: int) -> bytes:
    head, opening, middle, closing, tail = NESTS[name]
    return (head + opening * levels + middle + closing * levels + tail).encode()


def _python_in_tool_stack(content: bytes) -> str:
    """The Python result with the call stack of the parity tool: a fresh interpreter."""
    script = (
        "import sys; sys.path.insert(0, 'tools'); import dart_syntax_parity as p; "
        "text, _ = p.python_syntax(sys.stdin.buffer.read()); "
        "print('recursion' if text is None else text)"
    )
    run = subprocess.run(
        [sys.executable, "-c", script], input=content, capture_output=True, cwd=ROOT, check=True
    )
    return run.stdout.decode("utf-8").rstrip("\n")


def _tree_depth(content: bytes) -> int:
    from archkeel.analyzer.dart.parse import _PARSER

    stack = [(_PARSER.parse(content).root_node, 0)]
    deepest = 0
    while stack:
        node, depth = stack.pop()
        deepest = max(deepest, depth)
        stack.extend((child, depth + 1) for child in node.children)
    return deepest


# The first nest level where Python 3.11 stops in a fresh interpreter, measured on 2026-11-12;
# a deeper call stack stops Python one or two levels earlier. The tree depth is 986 to 989.
PYTHON_LIMITS = {"parentheses": 982, "closures": 246, "local_functions": 246}


@pytest.mark.parametrize("name", sorted(NESTS))
def test_each_recursive_walk_stops_python_below_where_native_names_the_depth(
    binary: Path, tmp_path: Path, name: str
) -> None:
    """AD-376: Python stops near tree depth 986; native names the file from depth 900 on."""
    limit = PYTHON_LIMITS[name]
    stopped = _nest(name, limit)
    assert _python_in_tool_stack(stopped) == "recursion"
    assert _tree_depth(stopped) > 900
    native = _native(binary, _write(tmp_path, "stopped.dart", stopped))
    messages = [item["message"] for item in native["concerns"]]  # type: ignore[attr-defined]
    assert messages == ["Dart source nests deeper than 900 levels."]
    assert native["sites"] == []


@pytest.mark.parametrize("name", sorted(NESTS))
def test_a_nest_just_below_the_native_depth_gives_the_python_sites(
    binary: Path, tmp_path: Path, name: str
) -> None:
    levels = next(k for k in range(PYTHON_LIMITS[name], 0, -1) if _tree_depth(_nest(name, k)) < 900)
    content = _nest(name, levels)
    path = _write(tmp_path, "deep.dart", content)
    [(text, _, value)] = parity.native_syntax(binary, [path])  # type: ignore[attr-defined]
    assert value["first_error"] is None  # type: ignore[index]
    expected = _python_in_tool_stack(content)
    same = text == expected
    assert same, parity.difference(expected, text)  # type: ignore[attr-defined]


def test_a_source_past_the_work_limit_gives_a_named_gap_and_no_sites(
    binary: Path, tmp_path: Path
) -> None:
    """AD-376: Python has no limit; native names a source whose site walks pass the limit."""
    nest = "f(" * 150 + "x" + ")" * 150
    content = "void g() {\n" + "".join(f"  {nest};\n" for _ in range(600)) + "}\n"
    native = _native(binary, _write(tmp_path, "work.dart", content))
    messages = [item["message"] for item in native["concerns"]]  # type: ignore[attr-defined]
    assert messages == [
        "The site analysis of this Dart source stops: the work passes the limit of the site walks."
    ]
    assert native["sites"] == []
    assert native["complete"] is False
    assert native["first_error"]["start_byte"] == 0  # type: ignore[index]


def test_the_copied_text_of_the_sites_counts_as_work(binary: Path, tmp_path: Path) -> None:
    """Each call of a nest copies the long string: the copies alone pass the limit."""
    text = "x" * 120_000
    content = "void g() { " + "f(" * 150 + f"'{text}'" + ")" * 150 + "; }\n"
    native = _native(binary, _write(tmp_path, "copies.dart", content))
    messages = [item["message"] for item in native["concerns"]]  # type: ignore[attr-defined]
    assert messages == [
        "The site analysis of this Dart source stops: the work passes the limit of the site walks."
    ]


def test_a_large_flat_source_stays_far_below_the_work_limit(binary: Path, tmp_path: Path) -> None:
    """The cache of siblings and the sweeps keep a long list linear; Python takes minutes."""
    content = "class A {\n  void m() {}\n" + "".join(f"  int f{i} = g{i}();\n" for i in range(20000))
    content += "  var l = [" + ", ".join(f"v{i}" for i in range(20000)) + "];\n}\n"
    path = _write(tmp_path, "flat.dart", content)
    [row] = parity.native_rows(binary, [path])  # type: ignore[attr-defined]
    assert row["syntax"]["concerns"] == []  # type: ignore[index]
    assert int(row["work_permille"]) < 200  # type: ignore[call-overload]


def test_the_dump_gives_the_fields_in_the_order_of_the_python_dataclasses(
    binary: Path, tmp_path: Path
) -> None:
    import dataclasses

    from archkeel.analyzer.dart.syntax import Site, Syntax

    path = _write(tmp_path, "a.dart", "void f() { g(); }\n")
    syntax = _native(binary, path)
    assert list(syntax) == [field.name for field in dataclasses.fields(Syntax)]
    [site] = syntax["sites"]  # type: ignore[misc]
    assert list(site) == [field.name for field in dataclasses.fields(Site)]
