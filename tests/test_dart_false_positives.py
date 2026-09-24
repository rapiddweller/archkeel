# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-97: nothing the Dart profile is unsure about may read as a violation.

The directive forms that look unusual to an import-graph reader (conditional alternatives,
`part` files, `deferred` imports, `export`) are ordinary Dart and add exactly their real edges;
text after the header is code, not a directive. Each case below is a clean package under strict
rules, so any invented edge or invented module shows up as a violation and fails the PASS.
"""

from pathlib import Path

from test_dart_directives import (
    component,
    dart_package,
    edges,
    modules,
    report_dart,
    rule,
)

from archkeel.ir.model import Observation


def _components() -> list[dict[str, object]]:
    return [
        component("core", public=["app.core.api", "app.core.impl"]),
        component("ui", requires=[{"component": "core", "rationale": "Probe."}]),
        component("data"),
    ]


def _strict_rules() -> list[dict[str, object]]:
    return [
        rule("REQUIRES", "complete_requires"),
        rule("CYCLES", "no_component_cycles"),
        rule("ASSIGNMENT", "complete_assignment", source="app"),
        rule(
            "LAYOUT",
            "root_layout",
            root="app",
            allowed_children=["app.core", "app.ui", "app.data"],
        ),
        rule("INTERFACE", "interface_boundary"),
        rule(
            "UI-NO-DATA",
            "forbidden_dependency",
            source="app.ui",
            target="app.data",
            include_type_checking=True,
        ),
    ]


def _clean(tmp_path: Path, files: dict[str, str]) -> Observation:
    root = dart_package(tmp_path / "pkg", files, components=_components(), rules=_strict_rules())
    result, observation, _ = report_dart(root)
    assert result.exit_code == 0, result.diagnostics
    assert observation is not None
    assert list(observation.records("violations") or ()) == []
    assert result.declared_rules == "PASS"
    return observation


def test_conditional_alternatives_add_only_their_own_edges(tmp_path: Path) -> None:
    observation = _clean(
        tmp_path,
        {
            "lib/ui/b.dart": "import 'package:app/core/api.dart'\n"
            "    if (dart.library.io) 'package:app/core/impl.dart'\n"
            "    if (dart.library.js_interop) '../core/impl.dart';\n"
            "\nclass B {}\n",
            "lib/core/api.dart": "export 'impl.dart' if (dart.library.io) 'hidden.dart';\n"
            "\nclass Api {}\n",
        },
    )
    assert edges(observation, "app.ui.b") == {("app.core.api", None), ("app.core.impl", None)}


def test_part_files_are_neither_modules_nor_unassigned(tmp_path: Path) -> None:
    # The part lives where no component and no allowed root child is: were it a module,
    # complete_assignment and root_layout would both report it.
    observation = _clean(
        tmp_path,
        {
            "lib/ui/b.dart": "import 'package:app/core/api.dart';\n"
            "part '../generated/b.g.dart';\n"
            "\nclass B {}\n",
            "lib/generated/b.g.dart": "part of '../ui/b.dart';\n\nclass BGenerated {}\n",
        },
    )
    assert not any(module.startswith("app.generated") for module in modules(observation))


def test_deferred_import_is_one_ordinary_edge(tmp_path: Path) -> None:
    observation = _clean(
        tmp_path,
        {
            "lib/ui/b.dart": "import 'package:app/core/api.dart' deferred as api;\n"
            "import 'package:app/core/impl.dart' deferred as impl show Impl;\n"
            "\nclass B {}\n",
        },
    )
    assert edges(observation, "app.ui.b") == {("app.core.api", None), ("app.core.impl", "Impl")}


def test_export_of_a_public_library_is_no_violation(tmp_path: Path) -> None:
    observation = _clean(
        tmp_path,
        {
            "lib/ui/b.dart": "export 'package:app/core/api.dart';\n"
            "export 'package:app/core/impl.dart' show Impl;\n"
            "\nclass B {}\n",
            "lib/ui/c.dart": "import 'b.dart';\n\nclass C {}\n",
        },
    )
    assert edges(observation, "app.ui.b") == {("app.core.api", None), ("app.core.impl", "Impl")}


def test_directive_text_after_the_header_adds_no_edge(tmp_path: Path) -> None:
    observation = _clean(
        tmp_path,
        {
            "lib/ui/b.dart": "import 'package:app/core/api.dart';\n"
            "\n"
            "// import 'package:app/data/store.dart';\n"
            "/* export 'package:app/data/store.dart'; */\n"
            "const note = \"import 'package:app/data/store.dart';\";\n"
            "\n"
            "class B {\n"
            "  // part 'missing.dart';\n"
            "  final String uri = 'package:app/data/store.dart';\n"
            "}\n"
            "\n"
            "/// import '../data/store.dart';\n"
            "void main() {}\n",
        },
    )
    assert edges(observation, "app.ui.b") == {("app.core.api", None)}
    assert "app.data.store" not in {target for target, _ in edges(observation)}
