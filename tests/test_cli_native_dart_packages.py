# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-500, AD-800: a second local package cannot hide a Dart import edge.

Each plant has a real cycle a -> b -> o -> a. The edge b -> o goes through
`package:other/o.dart`, and `other` is a local package below `packages/other`. The survey must
name the key, the file or the import that maps `other`, so that no rule passes without that edge.
Since AD-800 the survey proves the package map: the cycle rule has a receipt only when no import
names a package that the map does not prove external.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_cli_native_dart_imports import GRAPH, _commit
from test_cli_native_python_imports import RULE, component, rows, verdict

HEAD = "name: shop\nenvironment:\n  sdk: ^3.4.0\n"
FILES = {
    "lib/a.dart": "import 'package:shop/b.dart';\n",
    "lib/b.dart": "import 'package:other/o.dart';\n",
    "packages/other/lib/o.dart": "import 'package:shop/a.dart';\n",
}
# Each form maps the package `other` to a local directory: YAML reads the same key. A read key
# makes the import of `other` a gap (AD-800); a key that the survey cannot read keeps the
# whole-scope gap.
FORMS = {
    "double-quoted-key": (
        'dependencies:\n  other:\n    "path": packages/other\n',
        "DartLocalPackage",
    ),
    "single-quoted-key": (
        "dependencies:\n  other:\n    'path': packages/other\n",
        "DartLocalPackage",
    ),
    "flow-mapping": ('dependencies: {"other": {"path": packages/other}}\n', "DartLocalPackage"),
    "explicit-key": (
        "dependencies:\n  other:\n    ? path\n    : packages/other\n",
        "DartLocalPackage",
    ),
    "explicit-quoted-key": (
        'dependencies:\n  other:\n    ? "path"\n    : packages/other\n',
        "DartLocalPackage",
    ),
    "escaped-key": (
        'dependencies:\n  other:\n    "pa\\x74h": packages/other\n',
        "DartPathDependency",
    ),
    "quoted-workspace": ('"workspace":\n  - packages/other\n', "DartWorkspace"),
    "quoted-resolution": ("'resolution': workspace\n", "DartLocalPackage"),
    "override": ("dependency_overrides:\n  other:\n    path: packages/other\n", "DartLocalPackage"),
    "local-git": ("dependencies:\n  other:\n    git: packages/other\n", "DartLocalPackage"),
    # `other` is declared by no dependency; the local `tool` can declare it by its own path.
    "transitive-through-a-local-package": (
        "dependencies:\n  tool:\n    path: packages/tool\n",
        "DartUndeclaredPackage",
    ),
}


def project(root: Path, pubspec: str, files: dict[str, str], rules: list[dict[str, Any]]) -> Path:
    for name, text in {"pubspec.yaml": pubspec, **files}.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (root / "archkeel.toml").write_text(
        '[scan]\nlanguage = "dart"\nroots = ["lib", "packages/other/lib"]\n'
        'namespace = "shop"\ncontract = "architecture-contract.json"\n'
    )
    contract = {
        "schema_version": "2.2.0",
        "components": [
            component("a", ["shop.a"], ["b"], exact=True),
            component("b", ["shop.b"], ["o"], exact=True),
            component("o", ["shop.o"], ["a"], exact=True),
        ],
        "rules": rules,
    }
    (root / "architecture-contract.json").write_text(json.dumps(contract))
    (root / "p").write_text(GRAPH)
    _commit(root)
    return root


def rules(*, interface: bool = False) -> list[dict[str, Any]]:
    found = [
        {**RULE, "id": "CYCLES", "kind": "no_component_cycles"},
        {**RULE, "id": "ASSIGN", "kind": "complete_assignment", "source": "shop"},
    ]
    if interface:
        found.append({**RULE, "id": "BOUNDARY", "kind": "interface_boundary"})
    return found


def held(result: dict[str, Any], gap: str) -> None:
    found = rows(result)
    assert found["CYCLES"] == "UNKNOWN", result["frame"]["explained"]
    # AD-634: a package key leaves the edges of every library unknown, not the files; a second
    # package in a scan root can own its files, so it holds the rule on the files too.
    files = "UNKNOWN" if gap == "DartNestedPackage" else "PASS"
    assert found["ASSIGN"] == files, result["frame"]["explained"]
    assert gap in json.dumps(result["frame"]["collection_gaps"]), result["frame"]["scope"]


@pytest.mark.parametrize("form", sorted(FORMS))
def test_each_yaml_form_of_a_local_package_is_a_named_gap(
    release_core: Path, tmp_path: Path, form: str
) -> None:
    text, gap = FORMS[form]
    root = project(tmp_path, HEAD + text, FILES, rules())
    held(verdict(release_core, root, "report"), gap)


def test_a_package_file_above_a_scan_root_is_a_named_gap(
    release_core: Path, tmp_path: Path
) -> None:
    files = {**FILES, "packages/other/pubspec.yaml": "name: other\n"}
    root = project(tmp_path, HEAD, files, rules())
    held(verdict(release_core, root, "report"), "DartNestedPackage")


@pytest.mark.parametrize("interface", [False, True])
def test_a_dart_cycle_rule_without_a_package_gap_stays_unknown(
    release_core: Path, tmp_path: Path, interface: bool
) -> None:
    # AD-500 kept this rule UNKNOWN until a package-map proof exists. AD-800 is that proof: with
    # no import of another package and no dependency, the map is complete, so the guard now holds
    # the rule only where the proof is missing: here `b` imports `other`, which a local package of
    # the root can declare by its own path (`DartUndeclaredPackage`).
    pubspec = HEAD + "dependencies:\n  tool:\n    path: packages/tool\n"
    files = {
        **FILES,
        "lib/b.dart": "import 'package:other/o.dart';\n",
        "packages/other/lib/o.dart": "",
    }
    root = project(tmp_path, pubspec, files, rules(interface=interface))
    found = rows(verdict(release_core, root, "report"))
    assert found["CYCLES"] == "UNKNOWN"
    assert found["ASSIGN"] == "PASS"


@pytest.mark.parametrize("cycle", [False, True])
def test_a_complete_package_map_gives_the_cycle_rule_its_receipt(
    release_core: Path, tmp_path: Path, cycle: bool
) -> None:
    # The AD-500 guard tree without a local dependency: the map is complete (AD-800). Truth:
    # `dart analyze` (Dart 3) reports no error in either tree; edges o -> a -> b, and b -> a only
    # in the cyclic tree.
    files = {
        "lib/a.dart": "import 'package:shop/b.dart';\n",
        "lib/b.dart": "import 'a.dart';\n" if cycle else "",
        "packages/other/lib/o.dart": "import '../../../lib/a.dart';\n",
    }
    root = project(tmp_path, HEAD, files, rules())
    found = rows(verdict(release_core, root, "report"))
    assert found["CYCLES"] == ("FAIL" if cycle else "PASS"), found
    assert found["ASSIGN"] == "PASS"


# #1539: an app inside a pub workspace. Truth (Dart 3.12, `dart pub get` and `dart analyze`): the
# app resolves `package:other` to the member `other/` (`rootUri` `../other`) and its own URIs to
# `app/lib`; `dart analyze` finds no issue.
WORKSPACE = "name: ws\nenvironment:\n  sdk: ^3.6.0\nworkspace:\n  - app\n  - other\n"
APP = "name: app\nenvironment:\n  sdk: ^3.6.0\nresolution: workspace\n"
OTHER = "name: other\nenvironment:\n  sdk: ^3.6.0\nresolution: workspace\n"


def workspace_project(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (root / "archkeel.toml").write_text(
        '[scan]\nlanguage = "dart"\nroots = ["app/lib"]\n'
        'namespace = "shop"\ncontract = "architecture-contract.json"\n'
    )
    contract = {
        "schema_version": "2.2.0",
        "components": [
            component("a", ["shop.a"], ["b"], exact=True),
            component("b", ["shop.b"], [], exact=True),
        ],
        "rules": rules(),
    }
    (root / "architecture-contract.json").write_text(json.dumps(contract))
    (root / "p").write_text(GRAPH)
    _commit(root)
    return root


@pytest.mark.parametrize(
    ("form", "expected", "gap"),
    [
        ("acyclic", "PASS", None),
        ("cycle", "FAIL", None),
        ("member-import", "UNKNOWN", "DartLocalPackage"),
        ("nested-without-workspace", "UNKNOWN", "DartNestedPackage"),
    ],
)
def test_an_app_inside_a_workspace_is_the_package_of_its_scan(
    release_core: Path, tmp_path: Path, form: str, expected: str, gap: str | None
) -> None:
    files = {
        "pubspec.yaml": WORKSPACE,
        "app/pubspec.yaml": APP,
        "other/pubspec.yaml": OTHER,
        "other/lib/o.dart": "class O {}\n",
        "app/lib/a.dart": "import 'package:app/b.dart';\nB? b;\n",
        "app/lib/b.dart": "class B {}\n",
    }
    if form == "cycle":
        files["app/lib/b.dart"] = "import 'a.dart';\nclass B {}\n"
    if form == "member-import":
        files["app/lib/b.dart"] = "import 'package:other/o.dart';\nclass B { O? o; }\n"
    if form == "nested-without-workspace":
        files["pubspec.yaml"] = "name: shop\nenvironment:\n  sdk: ^3.6.0\n"
        files["app/pubspec.yaml"] = "name: app\nenvironment:\n  sdk: ^3.6.0\n"
    result = verdict(release_core, workspace_project(tmp_path, files), "report")
    found = rows(result)
    assert found["CYCLES"] == expected, result["frame"]["explained"]
    gaps = json.dumps(result["frame"]["collection_gaps"])
    if gap is None:
        assert result["frame"]["scope"] == "complete", gaps
    else:
        assert gap in gaps, gaps
