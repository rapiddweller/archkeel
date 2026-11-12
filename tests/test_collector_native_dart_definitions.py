# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1079 (#880): the native Dart definitions use time and memory that grow with the size.

Consumer: the Dart collector, which reads the definitions of each file of a scan. The members,
the top-level variables, the parameters and the nesting of a hostile source must not hold the
collector for minutes or for gigabytes (AD-376). Each shape of the issue runs on the binary of
the test build, with a time bound; the work of the walks is counted against the limit of the
site walks, and a file past the limit gets a named gap. The output stays equal to Python.
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

DEFINITION_GAP = (
    "The definition analysis of this Dart source stops: "
    "the work passes the limit of the definition walks."
)
DEPTH = "Dart source nests deeper than 900 levels."


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


def _run(binary: Path, tmp_path: Path, content: str) -> dict[str, object]:
    """The `--dump-syntax` row of one source, within a time bound of 60 seconds."""
    path = tmp_path / "shape.dart"
    path.write_text(content, encoding="utf-8")
    run = subprocess.run(
        [str(binary), "--dump-syntax"],
        input=f"{path}\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    row: dict[str, object] = json.loads(run.stdout)
    return row


def _messages(row: dict[str, object]) -> list[str]:
    return [item["message"] for item in row["syntax"]["concerns"]]  # type: ignore[index]


def _peak_bytes(binary: Path, path: Path) -> int:
    """The peak resident memory of the binary: a fresh interpreter that runs only the binary."""
    script = (
        "import resource, subprocess, sys; "
        "subprocess.run([sys.argv[1], '--dump-syntax'], input=sys.argv[2] + '\\n', "
        "capture_output=True, text=True, check=True, timeout=120); "
        "print(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)"
    )
    run = subprocess.run(
        [sys.executable, "-I", "-c", script, str(binary), str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    unit = 1 if sys.platform == "darwin" else 1024
    return int(run.stdout) * unit


FIELDS_THEN_METHODS = (
    "class A {\n"
    + "".join(f"  int f{i} = {i};\n" for i in range(10_000))
    + "".join(f"  void m{i}() {{}}\n" for i in range(10_000))
    + "}\n"
)
VARIABLES_THEN_FUNCTIONS = "".join(f"var v{i} = {i};\n" for i in range(10_000)) + "".join(
    f"void g{i}() {{}}\n" for i in range(10_000)
)
# A function with many parameters: each parameter read the siblings and the group again.
MANY_PARAMETERS = "void f([" + ", ".join(f"int p{i} = {i}" for i in range(20_000)) + "]) {}\n"
ANNOTATED_MEMBERS = (
    "class A {\n" + "".join(f"  @o{i} void m{i}() {{}}\n" for i in range(10_000)) + "}\n"
)

SHAPES = {
    "fields_then_methods": (FIELDS_THEN_METHODS, lambda defs: len(defs[0]["members"]), 20_000),
    "variables_then_functions": (VARIABLES_THEN_FUNCTIONS, len, 20_000),
    "many_parameters": (MANY_PARAMETERS, lambda defs: len(defs[0]["parameters"]), 20_000),
    "annotated_members": (ANNOTATED_MEMBERS, lambda defs: len(defs[0]["members"]), 10_000),
}


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_a_shape_that_the_definitions_read_again_for_each_member_ends_in_bounded_time(
    binary: Path, tmp_path: Path, name: str
) -> None:
    """Each shape took 27 to 70 seconds on main: it must end with a low share of the limit."""
    content, count, expected = SHAPES[name]
    row = _run(binary, tmp_path, content)
    messages = _messages(row)
    assert DEFINITION_GAP not in messages, messages
    assert not any("stops" in message for message in messages), messages
    assert int(row["work_permille"]) < 500, row["work_permille"]  # type: ignore[call-overload]
    assert count(row["syntax"]["definitions"]) == expected  # type: ignore[index]


def test_the_members_of_a_large_class_are_counted_and_stay_below_the_limit(
    binary: Path, tmp_path: Path
) -> None:
    row = _run(binary, tmp_path, FIELDS_THEN_METHODS)
    assert _messages(row) == []
    assert int(row["work_permille"]) < 100  # type: ignore[call-overload]


def test_one_declaration_with_many_items_gives_the_named_gap(binary: Path, tmp_path: Path) -> None:
    """The annotation of each item starts at the declaration: 20 000 items copy the head 20 000
    times. Python does the same and writes gigabytes; native stops at the work limit."""
    for head in ("", "class A { ", "class A { static final "):
        items = ", ".join(f"v{i} = {i}" for i in range(20_000))
        tail = " }" if head else ""
        row = _run(binary, tmp_path, f"{head}int {items};{tail}\n")
        assert _messages(row) == [DEFINITION_GAP], head
        syntax = row["syntax"]
        assert syntax["definitions"] == []  # type: ignore[index]
        assert syntax["sites"] == []  # type: ignore[index]
        assert syntax["complete"] is False  # type: ignore[index]
        assert syntax["first_error"]["start_byte"] == 0  # type: ignore[index]


def test_nested_parentheses_are_not_parsed_past_the_bracket_bound(
    binary: Path, tmp_path: Path
) -> None:
    """5 MB of `(` took 33 to 45 seconds and 4.3 GB: Tree-sitter keeps about 1.2 KB for each open
    bracket. The bound of ten times the depth limit stops the parse before it starts."""
    depth = 2_500_000
    path = tmp_path / "nest.dart"
    path.write_text("var x = " + "(" * depth + "1" + ")" * depth + ";\n", encoding="utf-8")
    assert path.stat().st_size > 5_000_000
    peak = _peak_bytes(binary, path)
    assert peak < 200_000_000, peak
    [row] = parity.native_rows(binary, [path])  # type: ignore[attr-defined]
    syntax = row["syntax"]
    assert [item["message"] for item in syntax["concerns"]] == [DEPTH]
    assert syntax["definitions"] == []
    assert syntax["first_error"]["start_byte"] == 8 + 9_000


def test_a_nest_at_the_bracket_bound_still_gets_its_tree_concern(
    binary: Path, tmp_path: Path
) -> None:
    """9 000 open brackets are parsed (and the tree passes the depth limit); 9 001 are not."""
    for depth, at_bound in ((9_000, False), (9_001, True)):
        content = "var x = " + "(" * depth + "1" + ")" * depth + ";\n"
        [row] = parity.native_rows(  # type: ignore[attr-defined]
            binary, [_write(tmp_path, content)]
        )
        syntax = row["syntax"]
        assert [item["message"] for item in syntax["concerns"]] == [DEPTH]
        assert (syntax["definitions"] == []) is at_bound
        start = syntax["first_error"]["start_byte"]
        assert (start == 8 + 9_000) is at_bound, start


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "nest.dart"
    path.write_text(content, encoding="utf-8")
    return path


# The code paths that now read the siblings of a node from one cache, and the parameter group
# that is read once. Each source compares with Python byte for byte.
CASES = {
    "annotated_members.dart": (
        "class A {\n  /// doc\n  @o int a = 1;\n  @p\n  @q void m() {}\n"
        "  // c\n  A();\n  @r final x = 1, y;\n  @s A.n(this.x);\n}\n"
    ),
    "modifiers.dart": (
        "const a = 1, b = 2;\nfinal late c = 3;\nlate final int d = 4;\nstatic int e = 5;\n"
        "var f;\nint g, h = 1;\nconst int i = 1;\nlate String? j;\n"
    ),
    "class_members.dart": (
        "class A<T> extends B<T> with M implements I {\n"
        "  static const int a = 1, b = 2;\n  final int c;\n  late final d = a;\n"
        "  A(this.c); A.named(int c) : c = c; factory A.f() => A(1);\n"
        "  int get x => c; set x(int v) {} A operator +(A o) => this;\n"
        "  static void s() {} external void e(); abstract int z();\n}\n"
    ),
    "parameters.dart": (
        "void a(int x, [int y = 1, String? z, k]) {}\n"
        "void b({required int x, int y = 2, void Function(int) f = _g, h}) {}\n"
        "void c(void g(int a), [void Function(String s)? h]) {}\n"
        "void d(final int x, covariant Object y, super.z) {}\n"
        "void _g(int a) {}\n"
        "class A { A(this.a, [this.b = 1, super.c]); int a = 0, b = 0; }\n"
    ),
    "optional_groups.dart": (
        "void a(  [ int x = 1 ]) {}\nvoid b(\n\t{ int x = 1 }) {}\n"
        "void c([ int x = 1]) {}\nvoid d({ required int x}) {}\n"
        "void e([   \n\n   \t  int x, int y]) {}\n"
    ),
    "typedefs_and_enums.dart": (
        "typedef F = int Function(String);\ntypedef void G(int x);\nenum E { a, b, c }\n"
        "enum H with M implements I { x(1), y(2); const H(this.v); final int v; }\n"
        "mixin M { int m = 1; void f() {} }\nextension X on String { int get n => 1; }\n"
        "extension type T(int v) { int w() => v; }\n"
    ),
    "unnamed_classifier.dart": "class { int a; }\nclass B { }\nmixin { }\nenum { a }\n",
    "top_level_mixed.dart": (
        "int a = 1, b = 2;\nvoid f() {}\nint get g => 1;\nset s(int v) {}\nfinal c = f();\n"
        "class A {}\nvar d, e = 3;\nint h(int x) => x;\n"
    ),
    "many_on_one_line.dart": (
        "var a = 1; var b = 2; void f() {} class A { int x = 1; int y = 2; void m() {} } "
        "final c = 3; int g() => 1;\n"
    ),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_definitions_equal_the_python_definitions(
    binary: Path, tmp_path: Path, name: str
) -> None:
    path = tmp_path / name
    path.write_text(CASES[name], encoding="utf-8")
    [(text, _, value)] = parity.native_syntax(binary, [path])  # type: ignore[attr-defined]
    expected, _ = parity.python_syntax(path.read_bytes())  # type: ignore[attr-defined]
    assert expected is not None
    same = text == expected
    assert same, parity.difference(expected, text)  # type: ignore[attr-defined]
    assert value["definitions"], "each case must give definitions"  # type: ignore[index]
