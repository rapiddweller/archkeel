# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-749: the Dart interface rule reads the publication surface of each import.

Each plant is a Dart package that `dart analyze` accepts with no issue (Dart 3.12). The rule
decides from the names that each directive binds, without the names of every dependency.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from test_cli_native_dart_imports import PUBSPEC, project
from test_cli_native_python_imports import RULE, component, rows, verdict

MODEL = "class Public {}\nclass Secret {}\n"
BOUNDARY = {**RULE, "id": "BOUNDARY", "kind": "interface_boundary"}
SYMBOL = {
    **RULE,
    "id": "SYMBOL",
    "kind": "forbidden_dependency",
    "source": "shop.data",
    "target": "shop.domain",
    "target_symbol": "Other",
    "include_type_checking": True,
}


def use(directive: str, name: str = "Public") -> str:
    return f"{directive}\n{name} make() => {name}();\n"


# Each plant: the files besides `pubspec.yaml`, the `public` list of `domain`, the package of
# `domain`, the extra rules, and the verdict of BOUNDARY.
PLANTS: dict[str, tuple[dict[str, str], list[str], str, list[dict[str, Any]], str]] = {
    # A `show` name that the component lists passes; any other name fails.
    "show-public": (
        {"lib/data/repo.dart": use("import 'package:shop/domain/model.dart' show Public;")},
        ["shop.domain.model:Public"],
        "shop.domain",
        [],
        "PASS",
    ),
    "show-secret": (
        {
            "lib/data/repo.dart": use(
                "import 'package:shop/domain/model.dart' show Secret;", "Secret"
            )
        },
        ["shop.domain.model:Public"],
        "shop.domain",
        [],
        "FAIL",
    ),
    "show-both": (
        {
            "lib/data/repo.dart": use(
                "import 'package:shop/domain/model.dart' show Public, Secret;"
            )
            + "Secret other() => Secret();\n"
        },
        ["shop.domain.model:Public"],
        "shop.domain",
        [],
        "FAIL",
    ),
    "prefix-secret": (
        {
            "lib/data/repo.dart": use(
                "import 'package:shop/domain/model.dart' as m show Secret;", "m.Secret"
            )
        },
        ["shop.domain.model:Public"],
        "shop.domain",
        [],
        "FAIL",
    ),
    "deferred-secret": (
        {
            "lib/data/repo.dart": "import 'package:shop/domain/model.dart'\n"
            "    deferred as m show Secret;\n"
            "Future<Object> make() async { await m.loadLibrary(); return m.Secret(); }\n"
        },
        ["shop.domain.model:Public"],
        "shop.domain",
        [],
        "FAIL",
    ),
    # The combinators apply in their order: `hide` before `show` removes the name. `dart analyze`
    # warns (`multiple_combinators`, `unused_shown_name`), and a use of `Secret` is an error.
    "hide-then-show": (
        {
            "lib/data/repo.dart": use(
                "import 'package:shop/domain/model.dart' hide Secret show Public, Secret;"
            )
        },
        ["shop.domain.model:Public"],
        "shop.domain",
        [],
        "PASS",
    ),
    # Without `show` the import binds each name of the library, and the survey reads no use of
    # them (4.0.1 AD-97): PASS when the module is listed, FAIL when no name of it can be public.
    "whole-listed": (
        {"lib/data/repo.dart": use("import 'package:shop/domain/model.dart';")},
        ["shop.domain.model"],
        "shop.domain",
        [],
        "PASS",
    ),
    "whole-unlisted": (
        {
            "lib/domain/api.dart": "export 'model.dart' show Public;\n",
            "lib/data/repo.dart": use("import 'package:shop/domain/model.dart';", "Secret"),
        },
        ["shop.domain.api:Public"],
        "shop.domain",
        [],
        "FAIL",
    ),
    # Kept gap: a `module:name` entry may be each name that the importer uses.
    "whole-named-entry": (
        {"lib/data/repo.dart": use("import 'package:shop/domain/model.dart';")},
        ["shop.domain.model:Public"],
        "shop.domain",
        [],
        "UNKNOWN",
    ),
    # Kept gap: the library re-exports, so a name of another module may be public.
    "whole-through-export": (
        {
            "lib/src/domain/api.dart": "export 'model.dart' show Public;\n",
            "lib/src/domain/model.dart": MODEL,
            "lib/data/repo.dart": use("import 'package:shop/src/domain/api.dart';"),
        },
        ["shop.src.domain.model:Public"],
        "shop.src.domain",
        [],
        "UNKNOWN",
    ),
    # A facade passes by its own entry: the first hop of the route.
    "facade-listed": (
        {
            "lib/domain/api.dart": "export 'model.dart' show Public;\n",
            "lib/data/repo.dart": use("import 'package:shop/domain/api.dart' show Public;"),
        },
        ["shop.domain.api:Public"],
        "shop.domain",
        [],
        "PASS",
    ),
    # Kept gap: the survey does not follow a route through an `export`, so a first hop that the
    # component does not list may still reach a listed later hop.
    "facade-route-open": (
        {
            "lib/src/domain/api.dart": "export 'model.dart' show Secret;\n",
            "lib/src/domain/model.dart": MODEL,
            "lib/data/repo.dart": use(
                "import 'package:shop/src/domain/api.dart' show Secret;", "Secret"
            ),
        },
        ["shop.src.domain.model:Public"],
        "shop.src.domain",
        [],
        "UNKNOWN",
    ),
    # A library outside `lib/src/` publishes each name that it exports (AD-608 for Dart).
    "publication-unlisted": (
        {"lib/domain/api.dart": "export 'model.dart' show Secret;\n"},
        ["shop.domain.model:Public", "shop.domain.api:Public"],
        "shop.domain",
        [],
        "FAIL",
    ),
    "publication-in-src": (
        {
            "lib/src/domain/api.dart": "export 'model.dart' show Secret;\n",
            "lib/src/domain/model.dart": MODEL,
        },
        ["shop.src.domain.model:Public"],
        "shop.src.domain",
        [],
        "PASS",
    ),
    # Kept gap: an `export` without `show` publishes names that the survey does not list.
    "publication-glob": (
        {"lib/domain/api.dart": "export 'model.dart';\n"},
        ["shop.domain.model:Public", "shop.domain.api:Public"],
        "shop.domain",
        [],
        "UNKNOWN",
    ),
    # A `target_symbol` verdict reads every dependency name, so it still holds the rule.
    "target-symbol-holds": (
        {"lib/data/repo.dart": use("import 'package:shop/domain/model.dart' show Public;")},
        ["shop.domain.model:Public"],
        "shop.domain",
        [SYMBOL],
        "UNKNOWN",
    ),
}


def files(name: str) -> dict[str, str]:
    """The files of a plant, `pubspec.yaml`, the domain model and a data library included."""
    own, _, package, _, _ = PLANTS[name]
    model = f"lib/{package.removeprefix('shop.').replace('.', '/')}/model.dart"
    return {"pubspec.yaml": PUBSPEC, model: MODEL, "lib/data/repo.dart": "class Repo {}\n", **own}


def _recommit(root: Path) -> None:
    names = {
        f"GIT_{who}_{key}": "t" for who in ("AUTHOR", "COMMITTER") for key in ("NAME", "EMAIL")
    }
    env = {**os.environ, **names}
    for step in (["add", "-A"], ["commit", "-qm", "contract"]):
        subprocess.run(["git", "-C", str(root), *step], check=True, env=env)


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_dart_interface_rule_reads_the_publication_surface(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    _, public, package, extra, expected = PLANTS[name]
    root = project(tmp_path, files(name))
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["components"] = [
        {**component("domain", [package]), "public": public},
        component("data", ["shop.data"], ["domain"]),
    ]
    contract["rules"] = [BOUNDARY, *extra]
    path.write_text(json.dumps(contract))
    _recommit(root)
    result = verdict(release_core, root)
    assert rows(result)["BOUNDARY"] == expected, result["frame"]["explained"]
