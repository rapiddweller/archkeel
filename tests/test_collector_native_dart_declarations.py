# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-390: compare the real Python declaration boundary, not a copy."""

from __future__ import annotations

import copy
import json
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
import dart_declarations_parity as parity  # noqa: E402
import dart_discovery_parity as discovery  # noqa: E402

SOURCES = [
    "",
    " ",
    "class A {}",
    "class _A {}",
    "abstract class A {}",
    "base class A {}",
    "final class A {}",
    "sealed class A {}",
    "interface class A {}",
    "mixin class A {}",
    "mixin A {}",
    "enum A { a, _b }",
    "enum A { a; int f() => 1; }",
    "typedef F = int Function(String);",
    "typedef F<T> = List<T>;",
    "int f() => 1;",
    "void f(int a) {}",
    "void f([int? a]) {}",
    "void f({required int a}) {}",
    "void f({int a = 4}) {}",
    "void f([int a = 4]) {}",
    "int get x => 1;",
    "set x(int a) {}",
    "int x = 1;",
    "const x = 1;",
    "final x = 1;",
    "const String x = 'value';",
    "var x = null;",
    "late int x;",
    "class A { int x = 1; }",
    "class A { final int x = 1; }",
    "class A { static const int x = 1; }",
    "class A { static int x = 1; }",
    "class A { int get x => 1; set x(int a) {} }",
    "class A { void f() {} }",
    "class A { static void f() {} }",
    "abstract class A { void f(); }",
    "class A { int operator +(A a) => 1; }",
    "class A { A(); }",
    "class A { A.named(); }",
    "class A<T> { A(); }",
    "class A<T,U> { A.named(); }",
    "class A { final int x; A(this.x); }",
    "class A { final int x; A({this.x = 3}); }",
    "class A { A(int a); }",
    "class A { factory A() => A.named(); A.named(); }",
    "class A { factory A(int a) = B; } class B implements A { B(int a); }",
    "class A { A(int a); } class B extends A { B(super.a); }",
    "class A { A([int a = 3]); } class B extends A { B([super.a]); }",
    "class A extends Missing { A(super.x); }",
    "class A { A(this.missing); }",
    "class A { void f() {} void f() {} }",
    "class A {} class A {}",
    "int f() => 1; int f() => 2;",
    "int get x => 1; set x(int a) {}",
    "extension A on String { int get x => length; }",
    "extension type A(int x) {}",
    "class A { int _x = 0; A._named(this._x); }",
    "const a = true, b = false;",
    "class A { int a=1, b=2; }",
    "enum A { a, b; const A(); }",
    "class A { external factory A(); }",
    "class A { late final String x; }",
    "void f(void Function(int) callback) {}",
    "class A { set x(int a) {} }",
    "class A { A(); } class A<T> { A.named(); }",
    "// BOM and CRLF\r\nclass A {}\r\n",
    "\ufeffclass A {}",
    "class A {",
    "import 'a.dart' if (dart.library.io) 'b.dart'; class A {}",
    "export 'a.dart' if (dart.library.html) 'c.dart'; class A {}",
    "class A { A(int a); } class B extends A { B(super.a, super.a); }",
    "class A { factory A(int a, int b) = Missing; }",
    "class A extends Missing { A(super.x, super.y); }",
]


@pytest.fixture(scope="module")
def binary() -> Path:
    cargo = shutil.which("cargo")
    if cargo is None:
        if os.environ.get("CI"):
            pytest.fail("CI must provide cargo")
        pytest.skip("cargo is not installed")
    install_rust_toolchain(cargo)
    return discovery.build(release=False)


def dump(binary: Path, value: object) -> dict:
    run = subprocess.run(
        [str(binary), "--dump-declarations"],
        input=json.dumps(value) + "\n",
        text=True,
        capture_output=True,
        check=True,
        timeout=20,
    )
    return json.loads(run.stdout)


def test_empty_boundary_is_exact_and_counts_work(binary: Path) -> None:
    result = dump(binary, {"files": []})
    assert result == {
        "symbols": [],
        "evidence": [],
        "gaps": [],
        "definition_ids": [],
        "definition_names": [],
        "scope_candidates": [],
        "symbol_by_name": [],
        "incomplete_inventory_ids": [],
        "work": 12,
    }


@pytest.mark.parametrize(
    "source", SOURCES, ids=[f"hostile-{index}" for index in range(len(SOURCES))]
)
def test_declaration_boundary_equals_python(binary: Path, tmp_path: Path, source: str) -> None:
    (tmp_path / "pubspec.yaml").write_text("name: shop\nenvironment:\n  sdk: '^3.12'\n")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib/a.dart").write_text(source)
    actual, expected = parity.from_source(binary, tmp_path)
    assert parity.canonical(parity.payload(actual)) == parity.canonical(expected)


def prepared(tmp_path: Path, source: str) -> tuple[dict, object]:
    (tmp_path / "pubspec.yaml").write_text("name: shop\nenvironment:\n  sdk: '^3.12'\n")
    (tmp_path / "lib").mkdir(exist_ok=True)
    (tmp_path / "lib/a.dart").write_text(source)
    corpus = discovery.Corpus("hostile", tmp_path, ("lib",), "shop")
    snapshot = parity.read_snapshot(discovery.request(corpus))
    syntax = {source.rel_path: parity.parse(source.content) for source in snapshot.sources}
    collection = parity.collection(corpus, snapshot, syntax)
    return parity.layer_input(collection), collection


@pytest.mark.parametrize(
    "fault",
    [
        "missing-resolution",
        "duplicate-resolution",
        "duplicate-path",
        "enum-length",
        "extra-resolution",
        "wrong-problem-path",
        "bad-span",
        "missing-parameter",
    ],
)
def test_inconsistent_input_has_one_named_gap_and_no_partial_records(
    binary: Path,
    tmp_path: Path,
    fault: str,
) -> None:
    value, _ = prepared(tmp_path, "class A { A(int x); } enum B { a }")
    file = value["files"][0]
    if fault == "missing-resolution":
        file["constructors"].clear()
    elif fault == "duplicate-resolution":
        file["constructors"] *= 2
    elif fault == "duplicate-path":
        value["files"] *= 2
    elif fault == "enum-length":
        file["syntax"]["definitions"][1]["enum_member_spans"] = []
    elif fault == "extra-resolution":
        resolution = copy.deepcopy(file["constructors"][0])
        resolution["start"] = 999
        file["constructors"].append(resolution)
    elif fault == "wrong-problem-path":
        file["constructors"][0]["problems"] = [
            {
                "path": "outside.dart",
                "kind": "UnsupportedParameter",
                "message": "unknown",
                "span": None,
            }
        ]
    elif fault == "missing-parameter":
        file["constructors"][0]["parameters"] = []
    else:
        file["syntax"]["definitions"][0]["span"]["end_byte"] = 999
    actual = dump(binary, value)
    assert not actual["symbols"] and not actual["definition_ids"] and not actual["evidence"]
    assert len(actual["gaps"]) == 1
    assert "DeclarationInputGap:" in actual["gaps"][0]["data"]["message"]


def test_generated_input_stops_within_ten_seconds(binary: Path, tmp_path: Path) -> None:
    value, _ = prepared(tmp_path, "int f() => 1;")
    definition = value["files"][0]["syntax"]["definitions"][0]
    value["files"][0]["syntax"]["definitions"] = [definition] * 30_000
    start = time.monotonic()
    actual = dump(binary, value)
    assert time.monotonic() - start < 10
    assert (
        not actual["symbols"] and not actual["scope_candidates"] and not actual["definition_names"]
    )
    assert len(actual["gaps"]) == 1
    assert "DeclarationWorkLimit:" in actual["gaps"][0]["data"]["message"]


def test_each_work_scan_and_copy_has_an_exact_charge(binary: Path, tmp_path: Path) -> None:
    value, _ = prepared(
        tmp_path, "class A<T> { int x = 1; A(this.x); int f(int y) => y; } int g() => 1;"
    )
    actual = dump(binary, value)
    assert actual["work"] == 335070


def test_files_sort_but_symbols_keep_publication_order(binary: Path, tmp_path: Path) -> None:
    value, collection = prepared(tmp_path, "class A { A(); void f() {} } int g() => 1; class B {}")
    other = copy.deepcopy(value["files"][0])
    other["rel"] = "lib/z.dart"
    other["module"] = "shop.z"
    value["files"] = [other, *value["files"]]
    actual = dump(binary, value)
    assert not actual["gaps"]
    assert [record["data"]["source_file"] for record in actual["symbols"]] == ["lib/a.dart"] * 5 + [
        "lib/z.dart"
    ] * 5
    first = actual["symbols"][:5]
    assert [record["kind"] for record in first] == [
        "method",
        "method",
        "class",
        "function",
        "class",
    ]
    assert first == parity.python(collection)["symbols"]


@pytest.mark.parametrize("index", range(64), ids=lambda index: f"filesystem-{index}")
def test_hostile_filesystem_keeps_every_selected_declaration(
    binary: Path,
    tmp_path: Path,
    index: int,
) -> None:
    metadata = [
        b"name: shop\n",
        b"name: shop\nname: later\n",
        b"\xef\xbb\xbfname: shop\n",
        b"name: shop\nenvironment: &sdk\n  sdk: '^3.12'\n",
        b"name: shop\r\nenvironment:\r\n  sdk: '^3.12'\r\n",
        b"name: shop\nenvironment: {sdk: '^3.12'}\n",
        b"name: [broken\n",
        b"\xff",
    ][index % 8]
    (tmp_path / "pubspec.yaml").write_bytes(metadata)
    lib = tmp_path / "lib"
    lib.mkdir()
    paths = [
        "a.dart",
        "odd path.dart",
        "é.dart",
        "A.dart",
        "nested/a.dart",
        "x-y.dart",
        "x_y.dart",
        ".dart",
    ]
    path = lib / paths[index % 8]
    path.parent.mkdir(parents=True, exist_ok=True)
    contents = [
        b"class A {}",
        b"",
        b"\xff",
        b"\xef\xbb\xbfclass A {}",
        b"class A {}\r\n",
        b"part of 'missing.dart'; class A {}",
        b"part 'missing.dart'; class A {}",
        b"import 'a.dart' if (dart.library.io) 'b.dart'; class A {}",
    ]
    path.write_bytes(contents[(index // 8) % 8])
    if index == 8:
        path.write_bytes(b"/" * (4 * 1024 * 1024 + 1))
    if index in {9, 10, 11}:
        if os.name == "nt":
            pytest.skip("symlink privileges are not available")
        target = lib / "loop"
        target.symlink_to(target if index == 9 else lib, target_is_directory=True)
        (lib / "link.dart").symlink_to(path)
    if index in {16, 17, 18}:
        nested = lib / "nested_package"
        nested.mkdir()
        (nested / "pubspec.yaml").write_text("name: nested\nworkspace: [member]\n")
        (nested / "a.dart").write_text("class Nested {}")
        dart_tool = tmp_path / ".dart_tool"
        dart_tool.mkdir()
        (dart_tool / "package_config.json").write_text(
            '{"configVersion":2,"packages":[{"name":"shop","rootUri":"../stale","packageUri":"lib/"}]}'
            if index == 16
            else "{stale"
        )
    if index == 24:
        (lib / "case.dart").write_text("class Lower {}")
        (lib / "CASE.dart").write_text("class Upper {}")
    if index == 25:
        (lib / "x-y.dart").write_text("class First {}")
        (lib / "x_y.dart").write_text("class Second {}")
    if index == 32:
        (lib / "b.dart").write_text("part of 'a.dart'; class B {}")
        (lib / "a.dart").write_text("part 'b.dart'; class A {}")
    corpus = discovery.Corpus("hostile", tmp_path, ("lib",), "shop")
    actual_snapshot = discovery.native(binary, corpus)
    try:
        snapshot = parity.read_snapshot(discovery.request(corpus))
    except parity.SnapshotError as error:
        assert discovery.same_error(actual_snapshot.get("error"), str(error))
        return
    assert "error" not in actual_snapshot
    selected = [source.rel_path for source in snapshot.sources]
    if actual_snapshot["selected_files"] != selected:
        assert index == 8
        assert any("size limit" in gap["data"]["message"] for gap in actual_snapshot["gaps"])
    else:
        result = discovery.Result("hostile")
        discovery.compare(corpus, binary, result, full=False)
        assert not result.problems
    actual, expected = parity.from_source(binary, tmp_path)
    assert parity.canonical(parity.payload(actual)) == parity.canonical(expected)


def test_unknown_dump_fields_stop_instead_of_disappearing(binary: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        dump(binary, {"files": [], "ignored": True})
