# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#880 PR 8 slice 3a: the native Dart syntax of each file equals Python `parse`.

Consumer: the record code of the Dart collector, which reads the definitions, the directives,
the concerns and the first error of each file. `test_collector_native_dart_sites.py` tests the
sites. The gate compares the `--dump-syntax` JSON of the
native collector with `dataclasses.asdict(parse(content))`, byte for byte, on hostile sources
and on the fixtures and demos. The differences of AD-369 are tested one by one.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
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

MEMBERS = """\
/// A shop.
@immutable
abstract base class Shop<T extends Object, U> extends Base<T> with A, B<U> implements C, D {
  static const int limit = 3, other = 4;
  late final String? name;
  final _items = <T>[];
  Shop(this.name, {required int size, super.key, int count = 2, String? note}) : assert(size > 0);
  const Shop.empty() : name = null;
  Shop.other([int a = 1, int? b]) : this(null, size: a);
  factory Shop.make() = Shop<T, U>.empty;
  factory Shop.build(int x) { return Shop.empty(); }
  @override
  String get title => name ?? '';
  set title(String value) {}
  static void reset(void Function(int) callback, int f(String s)) {}
  external int size();
  T operator [](int index) => _items[index];
  void operator []=(int index, T value) {}
  bool operator ==(Object other) => true;
  Shop<T, U> operator -() => this;
  abstract void close();
}
"""

DECLARATIONS = """\
library shop.core;
import 'a.dart' show A, B hide C;
import 'b.dart' deferred as b;
import "c.dart" as c show D;
export 'd.dart' if (dart.library.io) 'd_io.dart' if (dart.library.html) 'd_web.dart';
import 'e' 'f.dart';
import r'g.dart';
import '\\u{1F600}.dart';
import 'h$x.dart';
import 'i.dart' if (dart.library.io) 'j$y.dart';
part 'k.dart';
part 'l$z.dart';
mixin M on A implements B {}
sealed class S {}
final class F = Object with M;
interface class I {}
enum Color<T> with M implements I { red, green(2), blue; const Color([int v = 0]); final x = 0; }
extension Ext on String { int get size => length; }
extension type Id(int value) implements Object {}
typedef Call = void Function(int);
typedef void Old(String s);
typedef Map2<K> = Map<K, K>;
int top = 1, other;
const String? _private = null;
late final Map<String, int> map;
var v;
String get name => '';
set name(String value) {}
external int native(int a);
Future<void> main(List<String> args) async {}
"""

CASES: dict[str, str | bytes] = {
    "members.dart": MEMBERS,
    "declarations.dart": DECLARATIONS,
    "part_of_name.dart": "part of shop.core;\n",
    "part_of_uri.dart": "part of 'declarations.dart';\n",
    "version_low.dart": "// @dart=2.11\nvoid main() {}\n",
    "version_spaces.dart": "\n\n  // @dart=3.13  \n\nclass A {}\n",
    "version_zeros.dart": "  //  @dart=02.012.5\t\r\nclass A {}\n",
    "version_ok.dart": "// @dart=3.1\nclass A {}\n",
    "version_bad.dart": "// @dart=3.x\n// @dart=3.0\n",
    "unclosed.dart": "class A {}\n/* open /* nested */\nclass B {}\n",
    "string_comment.dart": "var s = '/*'; var r = r'\\'; /* ok */\n",
    "latin1.dart": b"class A { String s = '\xe9t\xe9'; }\n",
    "truncated.dart": b"class A {}\n// \xe2\x82",
    "broken.dart": "class {\n void f( {\n}\n",
    "missing.dart": "class A { int x = 1 }\nvoid g() { f( }\n",
    "lines.dart": "class A {}\r\nclass B {}\rclass C {}\u2028class D {}\n",
    "columns.dart": "var s = '\U0001f600'; class \u00e9A {}\tclass B {}\n",
    "empty.dart": "",
    "blank.dart": " \n\t\n",
    "combinator.dart": "import 'a.dart' show;\nexport 'b.dart' hide A,;\n",
    "conditional.dart": "import 'a.dart' if (dart.library.io) b;\n",
    "interpolated.dart": 'import \'a${b}.dart\';\nexport """c.dart""";\n',
    "keyword_uri.dart": "import'a.dart';\nexport/*x*/'b.dart';\npart//y\n'c.dart';\n",
    # Python 3.11 `\w` is not `char::is_alphanumeric`: a combining mark ends a word (AD-369).
    "word_mark_late.dart": "class A { var x = 'late\u093e'; }\n",
    "word_mark_sealed.dart": "abstract /*sealed\u0345*/ class A {}\n",
    "word_mark_deferred.dart": "import 'a.dart' /*deferred as\u064b*/ as p;\n",
    "word_underscore.dart": "class A { final _late = 1; static var x_static = '_static'; }\n",
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


@pytest.mark.parametrize("name", sorted(CASES))
def test_a_hostile_source_gives_the_python_syntax(binary: Path, tmp_path: Path, name: str) -> None:
    path = _write(tmp_path, name, CASES[name])
    [(text, _, _)] = parity.native_syntax(binary, [path])  # type: ignore[attr-defined]
    expected, _ = parity.python_syntax(path.read_bytes())  # type: ignore[attr-defined]
    assert expected is not None
    assert text == expected, parity.difference(expected, text)  # type: ignore[attr-defined]


def test_a_code_point_that_unicode_14_does_not_assign_is_a_native_gap(
    binary: Path, tmp_path: Path
) -> None:
    """L-27, AD-369: Python 3.12 and later read U+10D40 with newer data; native names the file."""
    path = _write(tmp_path, "new.dart", "var s = 'x\U00010d40';\n")
    [(_, _, value)] = parity.native_syntax(binary, [path])  # type: ignore[attr-defined]
    syntax = value  # type: ignore[assignment]
    messages = [item["message"] for item in syntax["concerns"]]  # type: ignore[index]
    assert messages == [parity.UNASSIGNED]  # type: ignore[attr-defined]
    assert syntax["first_error"]["line"] == 1  # type: ignore[index]


def test_the_unicode_tables_equal_the_oracle_python_311() -> None:
    """L-27: the committed tables are what Python 3.11 with Unicode 14.0.0 says today."""
    tables = _load("dart_unicode_tables")
    assert tables.main(["--check"]) == 0  # type: ignore[attr-defined]


def test_a_surrogate_escape_is_not_a_plain_uri_in_native(binary: Path, tmp_path: Path) -> None:
    """AD-369: Python keeps a lone surrogate in the target; native names the URI a concern."""
    path = _write(tmp_path, "surrogate.dart", "import '\\uD800.dart';\n")
    [(_, _, value)] = parity.native_syntax(binary, [path])  # type: ignore[attr-defined]
    syntax = value  # type: ignore[assignment]
    assert syntax["directives"][0]["target"] is None  # type: ignore[index]
    kinds = [item["kind"] for item in syntax["concerns"]]  # type: ignore[index]
    assert kinds == ["unsupported_directive"]


def test_a_tree_deeper_than_the_limit_gives_a_syntax_concern(binary: Path, tmp_path: Path) -> None:
    """AD-369: Python stops the scan near depth 987; native gives a gap above depth 900."""
    shallow = _write(tmp_path, "shallow.dart", "var x = " + "(" * 850 + "1" + ")" * 850 + ";\n")
    deep = _write(tmp_path, "deep.dart", "var x = " + "(" * 2000 + "1" + ")" * 2000 + ";\n")
    rows = parity.native_syntax(binary, [shallow, deep])  # type: ignore[attr-defined]
    shallow_syntax, deep_syntax = (value for _, _, value in rows)
    assert shallow_syntax["first_error"] is None  # type: ignore[index]
    messages = [item["message"] for item in deep_syntax["concerns"]]  # type: ignore[index]
    assert messages == ["Dart source nests deeper than 900 levels."]
    assert deep_syntax["first_error"]["line"] == 1  # type: ignore[index]
    assert deep_syntax["complete"] is False  # type: ignore[index]


def test_the_fixtures_and_demos_give_the_python_syntax(binary: Path, tmp_path: Path) -> None:
    results = {}
    for name, root in parity.corpora(True, [], tmp_path):  # type: ignore[attr-defined]
        result = results.setdefault(name, parity.Result(name))  # type: ignore[attr-defined]
        parity.compare(binary, root, result, None)  # type: ignore[attr-defined]
    for result in results.values():
        assert not result.problems, parity.report(result)  # type: ignore[attr-defined]
        assert result.files == result.total == result.equal > 0


def test_the_dump_lines_are_json_with_a_time(binary: Path, tmp_path: Path) -> None:
    path = _write(tmp_path, "a.dart", "class A {}\n")
    [(text, nanos, _)] = parity.native_syntax(binary, [path])  # type: ignore[attr-defined]
    assert nanos >= 0
    assert set(json.loads(text)) == {
        "definitions",
        "directives",
        "sites",
        "concerns",
        "first_error",
        "complete",
        "language_version",
    }
