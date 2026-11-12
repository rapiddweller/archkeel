# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-400: whole collection assembly calls the real Python oracle."""
import os
import shutil
import sys
from pathlib import Path
import pytest
from conftest import install_rust_toolchain

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import dart_collection_parity as parity  # noqa: E402


@pytest.fixture(scope="module")
def binary() -> Path:
    cargo = shutil.which("cargo")
    if cargo is None:
        if os.environ.get("CI"): pytest.fail("CI must provide cargo")
        pytest.skip("cargo is not installed")
    install_rust_toolchain(cargo)
    return parity.build(release=False)


def case(tmp_path: Path, files: dict[str, str]) -> parity._Collection:
    (tmp_path / "pubspec.yaml").write_text("name: shop\nenvironment:\n  sdk: '^3.12'\n")
    (tmp_path / "lib").mkdir(exist_ok=True)
    for rel, text in files.items():
        target = tmp_path / "lib" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return parity.prepared(parity.Corpus("probe", tmp_path, ("lib",), "shop"))


def test_a_class_has_complete_collection_state(binary: Path, tmp_path: Path) -> None:
    c = case(tmp_path, {"a.dart": "class A {}"})
    actual, expected = parity.compare(binary, c)
    assert parity.canonical(actual) == parity.canonical(expected)


BASE = (
    "class Base { final int x; Base(this.x); int f() => x; } "
    "mixin M { void mix() {} } class Service { static int run() => 1; } "
    "enum Mode { one, two } typedef Alias = Base; void helper() {}"
)
EXPRESSIONS = [
    "helper();", "Service.run();", "Base(1);", "new Base(1);", "Mode.one;",
    "var v = Base(1); v.f();", "Base v = Base(1); v.f();", "var v; v = Base(1); v.f();",
    "Base? v; v?.f();", "final v = Base(1); final w = v; w.f();",
    "final f = helper; f();", "var x = 0; x++; ++x; x += 1; x = 2;",
    "var x = 0; final y = x;", "var x = 0; { var x = 1; x++; } x++;",
    "final x = () => helper(); x();", "final x = (int a) { helper(); return a; }; x(1);",
    "[1,2].map((x) => Base(x)).toList();", "final x = Base(1).f();",
    "Base(1).f();", "final x = [Base(1)]; x.first.f();", "unknown();",
    "dynamic d; d.unknown();", "final x = Mode.one; x.name;", "Service.run;",
    "final x = () { var y = Base(1); return y.f(); }; x();",
]
PROBES = [f"import 'base.dart'; void flow() {{ {text} }}" for text in EXPRESSIONS]
PROBES += [f"import 'base.dart'; class Owner {{ void flow() {{ {text} }} }}" for text in EXPRESSIONS]
PROBES += [f"import 'base.dart'; void flow(int value) {{ void local() {{ {text} }} local(); }}" for text in EXPRESSIONS]
PROBES += [
    "import 'base.dart' as api; void f() { api.helper(); api.Base(1).f(); }",
    "import 'base.dart' show Base, helper; void f() { helper(); Base(1); Service.run(); }",
    "import 'base.dart' show Base, helper show Base; void f() { helper(); Base(1); }",
    "import 'base.dart' hide Base show Base; void f() { Base(1); }",
    "import 'base.dart' show Base hide Base; void f() { Base(1); }",
    "export 'base.dart' show Base, helper;", "export 'base.dart' hide Base;",
    "import 'base.dart' if (dart.library.io) 'other.dart'; void f() { helper(); }",
    "export 'base.dart' if (dart.library.html) 'other.dart' show Base;",
    "import 'base.dart' deferred as api; void f() { api.helper(); }",
    "import 'dart:async'; Future<void> f() async {}", "import 'package:outside/a.dart'; void f() {}",
    "import 'package:shop/base.dart'; void f() { Base(1); }",
    "import 'missing.dart'; class A {}", "import '../outside.dart'; class A {}",
    "import 'base.dart'; class Child extends Base with M { Child(super.x); }",
    "import 'base.dart'; class Child implements Base { int x = 1; int f() => x; }",
    "import 'base.dart'; class Child extends Alias { Child(super.x); }",
    "import 'base.dart'; class Child with Base {}", "import 'base.dart'; class Child with M {}",
    "class A {} class A {}", "class A { int x=1; int x=2; void f(){} void f(){} }",
    "class A { int get x=>1; set x(int value){} } void f(){ final a=A(); a.x++; }",
    "class A { factory A() = B; } class B implements A { B(); } void f(){ A(); }",
    "class A { A.named(); } void f(){ A.named(); A(); }", "class A<T> { A(); } void f(){ A<int>(); }",
    "extension E on String { int get x => length; }", "extension type E(int value) {}",
    "const x=1; final y=2; late int z; void f() { z = x+y; }",
    "typedef F = int Function(int); int f(int x) => x; F alias = f;",
    "part 'other.dart'; class Owner {}", "part of 'missing.dart'; class Orphan {}",
    "// @dart=2.12\nclass A {}", "// @dart=3.12\nclass A {}", "// @dart=4.0\nclass A {}",
    "class Broken {", "\ufeffclass A {}\r\n", "enum E { a, b; int f()=>index; }",
    "class A { static void f(){} } void f(){ A.f(); }",
    "class A { void f(){ this.f(); } }", "class A { A(this.x); final int x; }",
    "void f(){ final (a,b)=(1,2); print(a+b); }",
    "void f(){ switch(1) { case 1: break; default: break; } }",
    "void f(){ try { unknown(); } catch(error) { print(error); } }",
    "void f(){ for(final x in [1,2]) { print(x); } }",
]


@pytest.mark.parametrize("source", PROBES, ids=[f"edge-{index}" for index in range(len(PROBES))])
def test_original_edge_probe_is_byte_equal(binary: Path, tmp_path: Path, source: str) -> None:
    c = case(tmp_path, {"a.dart": source, "base.dart": BASE, "other.dart": "void helper() {} class Base {}"})
    actual, expected = parity.compare(binary, c)
    assert parity.canonical(actual) == parity.canonical(expected)


def test_any_gap_revokes_full_scope(binary: Path, tmp_path: Path) -> None:
    c = case(tmp_path, {"a.dart": "import 'missing.dart'; class A {}"})
    actual, expected = parity.compare(binary, c)
    assert actual["gaps"] and actual["full_scope"] is False
    assert parity.canonical(actual) == parity.canonical(expected)


def test_missing_site_answer_is_a_named_gap(binary: Path, tmp_path: Path) -> None:
    c = case(tmp_path, {"a.dart": "void f() { unknown(); }"})
    value = parity.layer_input(c)
    value["resolver"]["sites"] = []
    actual = parity.native(binary, value)
    assert actual["full_scope"] is False and not actual["symbols"]
    assert "CollectionInputGap:" in actual["gaps"][0]["data"]["message"]
