# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-400: whole collection assembly calls the real Python oracle."""

import copy
import os
import shutil
import subprocess
import sys
import time
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
        if os.environ.get("CI"):
            pytest.fail("CI must provide cargo")
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
    "helper();",
    "Service.run();",
    "Base(1);",
    "new Base(1);",
    "Mode.one;",
    "var v = Base(1); v.f();",
    "Base v = Base(1); v.f();",
    "var v; v = Base(1); v.f();",
    "Base? v; v?.f();",
    "final v = Base(1); final w = v; w.f();",
    "final f = helper; f();",
    "var x = 0; x++; ++x; x += 1; x = 2;",
    "var x = 0; final y = x;",
    "var x = 0; { var x = 1; x++; } x++;",
    "final x = () => helper(); x();",
    "final x = (int a) { helper(); return a; }; x(1);",
    "[1,2].map((x) => Base(x)).toList();",
    "final x = Base(1).f();",
    "Base(1).f();",
    "final x = [Base(1)]; x.first.f();",
    "unknown();",
    "dynamic d; d.unknown();",
    "final x = Mode.one; x.name;",
    "Service.run;",
    "final x = () { var y = Base(1); return y.f(); }; x();",
]
PROBES = [f"import 'base.dart'; void flow() {{ {text} }}" for text in EXPRESSIONS]
PROBES += [
    f"import 'base.dart'; class Owner {{ void flow() {{ {text} }} }}" for text in EXPRESSIONS
]
PROBES += [
    f"import 'base.dart'; void flow(int value) {{ void local() {{ {text} }} local(); }}"
    for text in EXPRESSIONS
]
PROBES += [
    "import 'base.dart' as api; void f() { api.helper(); api.Base(1).f(); }",
    "import 'base.dart' show Base, helper; void f() { helper(); Base(1); Service.run(); }",
    "import 'base.dart' show Base, helper show Base; void f() { helper(); Base(1); }",
    "import 'base.dart' hide Base show Base; void f() { Base(1); }",
    "import 'base.dart' show Base hide Base; void f() { Base(1); }",
    "export 'base.dart' show Base, helper;",
    "export 'base.dart' hide Base;",
    "import 'base.dart' if (dart.library.io) 'other.dart'; void f() { helper(); }",
    "export 'base.dart' if (dart.library.html) 'other.dart' show Base;",
    "import 'base.dart' deferred as api; void f() { api.helper(); }",
    "import 'dart:async'; Future<void> f() async {}",
    "import 'package:outside/a.dart'; void f() {}",
    "import 'package:shop/base.dart'; void f() { Base(1); }",
    "import 'missing.dart'; class A {}",
    "import '../outside.dart'; class A {}",
    "import 'base.dart'; class Child extends Base with M { Child(super.x); }",
    "import 'base.dart'; class Child implements Base { int x = 1; int f() => x; }",
    "import 'base.dart'; class Child extends Alias { Child(super.x); }",
    "import 'base.dart'; class Child with Base {}",
    "import 'base.dart'; class Child with M {}",
    "class A {} class A {}",
    "class A { int x=1; int x=2; void f(){} void f(){} }",
    "class A { int get x=>1; set x(int value){} } void f(){ final a=A(); a.x++; }",
    "class A { factory A() = B; } class B implements A { B(); } void f(){ A(); }",
    "class A { A.named(); } void f(){ A.named(); A(); }",
    "class A<T> { A(); } void f(){ A<int>(); }",
    "extension E on String { int get x => length; }",
    "extension type E(int value) {}",
    "const x=1; final y=2; late int z; void f() { z = x+y; }",
    "typedef F = int Function(int); int f(int x) => x; F alias = f;",
    "part 'other.dart'; class Owner {}",
    "part of 'missing.dart'; class Orphan {}",
    "// @dart=2.12\nclass A {}",
    "// @dart=3.12\nclass A {}",
    "// @dart=4.0\nclass A {}",
    "class Broken {",
    "\ufeffclass A {}\r\n",
    "enum E { a, b; int f()=>index; }",
    "class A { static void f(){} } void f(){ A.f(); }",
    "class A { void f(){ this.f(); } }",
    "class A { A(this.x); final int x; }",
    "void f(){ final (a,b)=(1,2); print(a+b); }",
    "void f(){ switch(1) { case 1: break; default: break; } }",
    "void f(){ try { unknown(); } catch(error) { print(error); } }",
    "void f(){ for(final x in [1,2]) { print(x); } }",
]


@pytest.mark.parametrize("source", PROBES, ids=[f"edge-{index}" for index in range(len(PROBES))])
def test_original_edge_probe_is_byte_equal(binary: Path, tmp_path: Path, source: str) -> None:
    c = case(
        tmp_path,
        {"a.dart": source, "base.dart": BASE, "other.dart": "void helper() {} class Base {}"},
    )
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


@pytest.mark.parametrize("answer", ["directives", "names", "sites", "constructions"])
def test_repeated_resolver_answer_stops_without_partial_records(
    binary: Path, tmp_path: Path, answer: str
) -> None:
    c = case(
        tmp_path,
        {
            "a.dart": "import 'b.dart'; class A extends B {} void f(){ B(); }",
            "b.dart": "class B {}",
        },
    )
    value = parity.layer_input(c)
    value["resolver"][answer].append(copy.deepcopy(value["resolver"][answer][0]))
    actual = parity.native(binary, value)
    assert not actual["full_scope"] and not actual["symbols"] and not actual["imports"]
    assert (
        len(actual["gaps"]) == 1 and "CollectionInputGap:" in actual["gaps"][0]["data"]["message"]
    )


@pytest.mark.parametrize("answer", ["directives", "names", "constructions"])
def test_required_resolver_answer_cannot_be_omitted(
    binary: Path, tmp_path: Path, answer: str
) -> None:
    c = case(
        tmp_path,
        {
            "a.dart": "import 'b.dart'; class A extends B {} void f(){ B(); }",
            "b.dart": "class B {}",
        },
    )
    value = parity.layer_input(c)
    value["resolver"][answer] = []
    actual = parity.native(binary, value)
    assert not actual["full_scope"] and not actual["symbols"]
    assert "CollectionInputGap:" in actual["gaps"][0]["data"]["message"]


def test_same_count_with_a_different_site_cannot_hide_a_site(binary: Path, tmp_path: Path) -> None:
    c = case(tmp_path, {"a.dart": "void f(){ unknown(); }"})
    value = parity.layer_input(c)
    value["resolver"]["sites"][0]["sites"][0]["site"]["expression"] = "different"
    actual = parity.native(binary, value)
    assert not actual["full_scope"] and not actual["symbols"]
    assert "CollectionInputGap:" in actual["gaps"][0]["data"]["message"]


@pytest.mark.parametrize("sdk", ["^3.12", "^4.0", ">=2.0 <3.0", "any", "not-a-version", None])
def test_sdk_support_controls_inventories(binary: Path, tmp_path: Path, sdk: str | None) -> None:
    case(tmp_path, {"a.dart": "class A { int x = 1; void f() {} }"})
    (tmp_path / "pubspec.yaml").write_text(
        "name: shop\n" + (f"environment:\n  sdk: '{sdk}'\n" if sdk is not None else "")
    )
    c = parity.prepared(parity.Corpus("sdk", tmp_path, ("lib",), "shop"))
    actual, expected = parity.compare(binary, c)
    assert parity.canonical(actual) == parity.canonical(expected)
    if sdk not in ("^3.12", None):
        assert not actual["full_scope"] and "member_inventories" not in actual["symbols"][0]["data"]


@pytest.mark.parametrize(
    "source",
    [
        "//\n@dart=4.0\nclass A {}",
        "//\r\n@dart=4.0\nclass A {}",
        "/* code */\r// @dart=4.0\nclass A {}",
        "//\u001c@dart=4.0\nclass A {}",
        "// @dart=2.0012.0000\nclass A {}",
        "// @dart=3.12\n// @dart=4.0\nclass A {}",
        "// @dart=\nclass A {}",
        "// @dart=3.13\nclass A {}",
        "// @dart=2.11\nclass A {}",
    ],
)
def test_language_override_has_the_python_match_rules(
    binary: Path, tmp_path: Path, source: str
) -> None:
    c = case(tmp_path, {"a.dart": source})
    actual, expected = parity.compare(binary, c)
    assert parity.canonical(actual) == parity.canonical(expected)


@pytest.mark.parametrize("part_version", ["2.12", "3.12"])
def test_parts_share_the_library_and_main_override(
    binary: Path, tmp_path: Path, part_version: str
) -> None:
    c = case(
        tmp_path,
        {
            "main.dart": "// @dart=3.12\npart 'part.dart'; class A {}",
            "part.dart": f"// @dart={part_version}\npart of 'main.dart'; class B extends A {{}}",
        },
    )
    actual, expected = parity.compare(binary, c)
    assert parity.canonical(actual) == parity.canonical(expected)
    assert len(actual["files"]) == 1 and len(actual["symbols"]) == 2


def test_empty_selection_cannot_claim_full_scope(binary: Path, tmp_path: Path) -> None:
    c = case(tmp_path, {})
    actual, expected = parity.compare(binary, c)
    assert not actual["full_scope"]
    assert parity.canonical(actual) == parity.canonical(expected)


def test_a_hostile_identifier_stops_in_bounded_time(binary: Path, tmp_path: Path) -> None:
    value = parity.layer_input(case(tmp_path, {"a.dart": "class A {}"}))
    value["files"][0]["file"]["syntax"]["definitions"][0]["name"] = "x" * (4 * 1024 * 1024)
    start = time.monotonic()
    actual = parity.native(binary, value)
    assert time.monotonic() - start < 10
    assert not actual["full_scope"] and not actual["symbols"] and not actual["evidence"]
    assert (
        len(actual["gaps"]) == 1 and "CollectionWorkLimit:" in actual["gaps"][0]["data"]["message"]
    )


@pytest.mark.parametrize("field", ["ignored", "resolver.ignored", "files.ignored"])
def test_unknown_fields_are_rejected(binary: Path, tmp_path: Path, field: str) -> None:
    value = parity.layer_input(case(tmp_path, {"a.dart": "class A {}"}))
    owner = (
        value
        if field == "ignored"
        else value["resolver"]
        if field.startswith("resolver")
        else value["files"][0]
    )
    owner["ignored"] = True
    run = subprocess.run(
        [str(binary), "--dump-collection"],
        input=parity.canonical(value),
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert run.returncode != 0 and not run.stdout and "unknown field" in run.stderr


def test_nested_untyped_json_is_rejected_without_a_walk(binary: Path) -> None:
    run = subprocess.run(
        [str(binary), "--dump-collection"],
        input='{"files":' + "[" * 500 + "0" + "]" * 500 + "}",
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert run.returncode != 0 and not run.stdout


def test_collection_work_has_one_input_budget_and_a_pinned_charge(
    binary: Path, tmp_path: Path
) -> None:
    c = case(tmp_path, {"a.dart": "class A {}"})
    actual = parity.native(binary, parity.layer_input(c))
    assert actual["work"] == 11541


def test_excess_language_digits_give_a_named_gap(binary: Path, tmp_path: Path) -> None:
    value = parity.layer_input(case(tmp_path, {"a.dart": "class A {}"}))
    value["files"][0]["content"] = "// @dart=3.12." + "0" * 4301 + "\nclass A {}"
    actual = parity.native(binary, value)
    assert not actual["full_scope"]
    assert any("LanguageVersionDigitLimit:" in gap["data"]["message"] for gap in actual["gaps"])


def test_parts_without_a_main_override_have_a_named_order_gap(binary: Path, tmp_path: Path) -> None:
    c = case(
        tmp_path,
        {
            "main.dart": "part 'a.dart'; part 'b.dart'; class A {}",
            "a.dart": "// @dart=2.12\npart of 'main.dart'; class B {}",
            "b.dart": "// @dart=3.12\npart of 'main.dart'; class C {}",
        },
    )
    actual = parity.native(binary, parity.layer_input(c))
    assert not actual["full_scope"]
    assert any("LanguageVersionOrderGap:" in gap["data"]["message"] for gap in actual["gaps"])
