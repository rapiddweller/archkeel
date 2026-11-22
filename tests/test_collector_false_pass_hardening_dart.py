# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1048: a real violation in a Dart project is never PASS (see the TypeScript file).

`dart analyze` accepts and `dart run` runs each plant.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from test_collector_false_pass_hardening import (
    CYCLE_GRAPH,
    CYCLES,
    DART,
    DART_FILES,
    DART_GAP,
    INTERFACE,
    NO_A_TO_B,
    RULE,
    dart,
    needs_dart,
    never_pass,
    scan,
)

DART_MAIN = "import 'package:app/src/a/x.dart';\n\nvoid main() => print(y);\n"
B_VALUE = "const y = 'B-LOADED';\n"
DART_HIDDEN = {
    "conditional-import": {
        "lib/src/a/x.dart": "import 'stub.dart' if (dart.library.io) '../b/y.dart' as impl;\n\n"
        "const y = impl.y;\n",
        "lib/src/a/stub.dart": "const y = 'stub';\n",
        "lib/src/b/y.dart": B_VALUE,
    },
    "conditional-export": {
        "lib/src/a/x.dart": "export 'stub.dart' if (dart.library.io) '../b/y.dart';\n",
        "lib/src/a/stub.dart": "const y = 'stub';\n",
        "lib/src/b/y.dart": B_VALUE,
    },
    "part": {
        "lib/src/a/x.dart": "part '../b/y.dart';\n",
        "lib/src/b/y.dart": "part of '../a/x.dart';\n" + B_VALUE,
    },
}


def dart_truth(root: Path, expected: str) -> None:
    dart(root, "pub", "get", "--offline")
    dart(root, "analyze", "--fatal-infos")
    assert expected in dart(root, "run", "bin/main.dart")


@needs_dart
@pytest.mark.parametrize("gap", [True, False], ids=["with-gap", "no-gap"])
@pytest.mark.parametrize("name", sorted(DART_HIDDEN))
def test_a_hidden_dart_edge_is_never_pass(
    release_core: Path, tmp_path: Path, name: str, gap: bool
) -> None:
    files = {**DART_FILES, "bin/main.dart": DART_MAIN, **DART_HIDDEN[name]}
    rule_ = {**NO_A_TO_B, "source": "app.src.a", "target": "app.src.b"}
    root = scan(tmp_path / "plain", DART, files, [rule_])
    dart_truth(root, "B-LOADED")
    if gap:
        # The same code with a workspace key: the survey cannot read other packages.
        root = scan(tmp_path / "gap", DART, {**files, "pubspec.yaml": DART_GAP}, [rule_])
    assert never_pass(root, release_core, "A-NO-B") in {"FAIL", "UNKNOWN"}


@needs_dart
def test_a_forbidden_dart_assert_is_never_pass(release_core: Path, tmp_path: Path) -> None:
    files = {
        **DART_FILES,
        "lib/src/a/x.dart": "int f(int v) {\n  assert(v > 0);\n  return v;\n}\n",
        "lib/src/b/y.dart": "const y = 1;\n",
        "bin/main.dart": "import 'package:app/src/a/x.dart';\n\nvoid main() => f(0);\n",
    }
    rule_ = {
        **RULE,
        "id": "CONSTRUCT",
        "kind": "forbidden_construct",
        "source": "app.src.a",
        "constructs": ["assert"],
    }
    root = scan(tmp_path, DART, files, [rule_])
    dart(root, "pub", "get", "--offline")
    dart(root, "analyze", "--fatal-infos")
    checked = subprocess.run(
        ["dart", "run", "--enable-asserts", "bin/main.dart"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=240,
    )
    assert checked.returncode != 0 and "Failed assertion" in checked.stderr, checked.stderr
    assert never_pass(root, release_core, "CONSTRUCT") in {"FAIL", "UNKNOWN"}


@needs_dart
def test_a_dart_file_that_the_layout_does_not_allow_is_never_pass(
    release_core: Path, tmp_path: Path
) -> None:
    files = {
        **DART_FILES,
        "lib/src/a/x.dart": "const x = 1;\n",
        "lib/src/a/extra.dart": "const extra = 1;\n",
        "lib/src/b/y.dart": "const y = 1;\n",
    }
    rule_ = {
        **RULE,
        "id": "LAYOUT",
        "kind": "root_layout",
        "root": "app.src.a",
        "allowed_children": ["app.src.a.x"],
    }
    root = scan(tmp_path, DART, files, [rule_])
    dart(root, "analyze", "--fatal-infos")
    assert never_pass(root, release_core, "LAYOUT") == "FAIL"


@needs_dart
def test_a_private_dart_import_across_components_is_never_pass(
    release_core: Path, tmp_path: Path
) -> None:
    files = {
        **DART_FILES,
        "lib/src/a/x.dart": "import '../b/impl.dart';\n\nconst x = secret;\n",
        "lib/src/b/api.dart": "const api = 1;\n",
        "lib/src/b/impl.dart": "const secret = 2;\n",
        "bin/main.dart": "import 'package:app/src/a/x.dart';\n\nvoid main() => print(x);\n",
    }
    root = scan(tmp_path, DART, files, [INTERFACE], b_public="app.src.b.api")
    assert dart(root, "run", "bin/main.dart").strip() == "2"
    assert never_pass(root, release_core, "BOUNDARY") == "FAIL"


@needs_dart
@pytest.mark.parametrize("gap", [True, False], ids=["with-gap", "no-gap"])
def test_a_dart_cycle_behind_a_gap_is_never_pass(
    release_core: Path, tmp_path: Path, gap: bool
) -> None:
    files = {
        **DART_FILES,
        "lib/src/a/x.dart": "import '../b/y.dart';\n\nconst x = 1;\nconst z = y;\n",
        "lib/src/b/y.dart": "import '../a/x.dart';\n\nconst y = 2;\nconst w = x;\n",
        "bin/main.dart": "import 'package:app/src/a/x.dart';\n\nvoid main() => print(x);\n",
    }
    root = scan(tmp_path / "plain", DART, files, [CYCLES], graph=CYCLE_GRAPH)
    assert dart(root, "run", "bin/main.dart").strip() == "1"
    if gap:
        root = scan(
            tmp_path / "gap", DART, {**files, "pubspec.yaml": DART_GAP}, [CYCLES], graph=CYCLE_GRAPH
        )
    assert never_pass(root, release_core, "NO-CYCLES") == "FAIL"
