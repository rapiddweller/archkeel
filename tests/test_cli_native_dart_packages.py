# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-500: a second local package cannot hide a Dart import edge.

Each plant has a real cycle a -> b -> o -> a. The edge b -> o goes through
`package:other/o.dart`, and `other` is a local package below `packages/other`. The survey must
name the key or the file that maps `other`, so that no rule passes without that edge.
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
# Each form maps the package `other` to a local directory: YAML reads the same key.
FORMS = {
    "double-quoted-key": (
        'dependencies:\n  other:\n    "path": packages/other\n',
        "DartPathDependency",
    ),
    "single-quoted-key": (
        "dependencies:\n  other:\n    'path': packages/other\n",
        "DartPathDependency",
    ),
    "flow-mapping": ('dependencies: {"other": {"path": packages/other}}\n', "DartPathDependency"),
    "explicit-key": (
        "dependencies:\n  other:\n    ? path\n    : packages/other\n",
        "DartPathDependency",
    ),
    "explicit-quoted-key": (
        'dependencies:\n  other:\n    ? "path"\n    : packages/other\n',
        "DartPathDependency",
    ),
    "escaped-key": (
        'dependencies:\n  other:\n    "pa\\x74h": packages/other\n',
        "DartPathDependency",
    ),
    "quoted-workspace": ('"workspace":\n  - packages/other\n', "DartWorkspace"),
    "quoted-resolution": ("'resolution': workspace\n", "DartWorkspace"),
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
    assert found["ASSIGN"] == "UNKNOWN", result["frame"]["explained"]
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
    files = {**FILES, "lib/b.dart": "", "packages/other/lib/o.dart": ""}
    root = project(tmp_path, HEAD, files, rules(interface=interface))
    found = rows(verdict(release_core, root, "report"))
    assert found["CYCLES"] == "UNKNOWN"
    assert found["ASSIGN"] == "PASS"
