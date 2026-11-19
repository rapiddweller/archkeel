# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""UML can compare a proven Dart literal type without inventing a written annotation."""

import json
from pathlib import Path

import pytest
from core_support import run
from test_cli_native_dart_uml_parts import ROOT, RULE

from archkeel.cli import core_only
from tools.fixture_tree import fixture_tree


@pytest.mark.parametrize(
    ("declaration", "library", "target_type", "expected"),
    [
        ("static const path = '/';", "", "String", "PASS"),
        ("static const path = '/';", "", "int", "FAIL"),
        ("static const Object path = '/';", "", "String", "FAIL"),
        ("static const Object path = '/';", "", "Object", "PASS"),
        ("static const path = '/';", "class String {}", "String", "UNKNOWN"),
        ("static const path = '/';", "class int {}", "int", "UNKNOWN"),
        ("static const path = '/';", "typedef Object String();", "String", "UNKNOWN"),
        (
            "static const path = '/';",
            "class Base {}\nmixin M {}\nclass String = Base with M;",
            "String",
            "UNKNOWN",
        ),
        ("static const path = '/';", "typedef Object int();", "int", "UNKNOWN"),
        ("static const path = '/';", "typedef String Callback();", "String", "PASS"),
        ("static const path = '/';", "import 'dart:core' hide String;", "String", "UNKNOWN"),
        (
            "static const path = '/';",
            "import 'empty.dart' if (dart.library.io) 'shadow.dart';",
            "String",
            "UNKNOWN",
        ),
        ("static const path = '/' == '/';", "", "String", "UNKNOWN"),
        ("static const path = '$stem/item';", "const stem = '/';", "String", "PASS"),
        ("static const path = '$stem/item';", "const stem = '/';", "int", "FAIL"),
        ("static const path = r'$stem/item';", "", "String", "PASS"),
        (r"static const path = '\$stem/item';", "", "String", "PASS"),
        ("static const path = '${1 + 2}';", "", "String", "PASS"),
        ("static const path = '$stem/item' == '/item';", "const stem = '/';", "String", "UNKNOWN"),
        ("static const path = '$stem/item'.length;", "const stem = '/';", "String", "UNKNOWN"),
        ("static final path = '$stem/item'.isEmpty;", "var stem = '/';", "String", "UNKNOWN"),
        (
            "static const path = '$stem/item';",
            "class String {}\nconst stem = '/';",
            "String",
            "UNKNOWN",
        ),
        ("static final path = f();", "String f() => '/';", "String", "UNKNOWN"),
    ],
)
def test_dart_literal_type(
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    declaration: str,
    library: str,
    target_type: str,
    expected: str,
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    for relative in ("docs/target.md", "pubspec.yaml", "archkeel.toml"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "models.dart").write_text(f"{library}\nclass Routes {{\n  {declaration}\n}}\n")
    (lib / "empty.dart").write_text("")
    (lib / "shadow.dart").write_text("class String {}\n")
    contract = json.loads((ROOT / "architecture-contract.json").read_bytes())
    uml = contract["declarations"]["uml"]
    _, owner, field = uml["entities"]
    owner.update(kind="class", qualified_name="catalog.models.Routes")
    field.update(
        kind="attribute", qualified_name="catalog.models.Routes.path", annotation=target_type
    )
    uml["scopes"] = []
    (tmp_path / "architecture-contract.json").write_text(json.dumps(contract))

    with fixture_tree(tmp_path) as root:
        code, result = run("report", "--root", str(root))
    frame = result["frame"]
    assert (code, frame["rules"][RULE][1]) == (
        {"PASS": 0, "FAIL": 1, "UNKNOWN": 2}[expected],
        expected,
    )
    assert frame["collection_gaps"] == []
    if expected == "FAIL":
        [detail] = frame["details"][RULE]
        cause = (
            "inferred type differs"
            if declaration.startswith("static const path = ")
            else "annotation differs"
        )
        assert detail["cause"] == cause
        assert [frame["locations"][site] for site in detail["evidence"]] == [
            {"path": "lib/models.dart", "line": 3}
        ]


@pytest.mark.parametrize(
    ("source", "target", "expected"),
    [
        ("class Item {}\nvoid build() { final item = Item(); }", "Item", "PASS"),
        ("class Item {}\nvoid build() { final item = Item(); }", "Object", "UNKNOWN"),
        ("class Item<T> {}\nvoid build() { final item = Item<int>(); }", "Item<int>", "UNKNOWN"),
        ("class Item {}\nvoid build() { final Object item = Item(); }", "Item", "FAIL"),
    ],
)
def test_dart_constructor_type(
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    source: str,
    target: str,
    expected: str,
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    for relative in ("docs/target.md", "pubspec.yaml", "archkeel.toml"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "models.dart").write_text(source)
    contract = json.loads((ROOT / "architecture-contract.json").read_bytes())
    uml = contract["declarations"]["uml"]
    _, owner, local = uml["entities"]
    owner.update(kind="function", qualified_name="catalog.models.build")
    local.update(kind="binding", qualified_name="catalog.models.build.item", annotation=target)
    uml["scopes"] = []
    (tmp_path / "architecture-contract.json").write_text(json.dumps(contract))
    with fixture_tree(tmp_path) as root:
        _, result = run("report", "--root", str(root))
    assert result["frame"]["rules"][RULE][1] == expected
