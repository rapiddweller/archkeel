# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-97: every rule kind the Dart profile calls decided really decides, both ways.

A decided rule kind is a promise that PASS means "no violation among the edges", so each kind
gets a package that must pass and the one-line change that must fail it, read through `report`
exactly as a user sees the verdict. A rule that could only pass on Dart (because the scanner
never produced the record it matches) would pass every PASS case here and fail its FAIL twin.
"""

from pathlib import Path

import pytest
from test_dart_directives import component, dart_package, report_dart, rule

# The ui library every case starts from: one own import of core, one external package.
_UI = "import 'package:app/core/api.dart' show Api;\nimport 'package:dio/dio.dart';\n\nclass B {}\n"


def _components() -> list[dict[str, object]]:
    return [
        component("core", public=["app.core.api"]),
        component("ui", requires=[{"component": "core", "rationale": "Probe."}]),
        component("data"),
    ]


_CASES: dict[str, tuple[list[dict[str, object]], dict[str, str], dict[str, str]]] = {
    # kind: (rules, files that PASS, files added on top that FAIL)
    "forbidden_dependency": (
        [
            rule(
                "RULE",
                "forbidden_dependency",
                source="app.core",
                target="app.ui",
                include_type_checking=True,
            )
        ],
        {},
        {"lib/core/impl.dart": "import 'package:app/ui/b.dart';\n\nclass Impl {}\n"},
    ),
    "forbidden_dependency_dart_io": (
        [
            rule(
                "RULE",
                "forbidden_dependency",
                source="app.core",
                target="dart.io",
                include_type_checking=True,
            )
        ],
        {
            "lib/core/impl.dart": "import 'dart:async';\n\nclass Impl {}\n",
            "lib/data/store.dart": "import 'dart:io';\n\nclass Store {}\n",
        },
        {"lib/core/impl.dart": "import 'dart:io' show File;\n\nclass Impl {}\n"},
    ),
    "complete_requires": (
        [rule("RULE", "complete_requires")],
        {},
        {"lib/data/store.dart": "import 'package:app/core/api.dart';\n\nclass Store {}\n"},
    ),
    "no_component_cycles": (
        [rule("RULE", "no_component_cycles")],
        {},
        {"lib/core/impl.dart": "import '../ui/b.dart';\n\nclass Impl {}\n"},
    ),
    "complete_assignment": (
        [rule("RULE", "complete_assignment", source="app")],
        {},
        {"lib/extra/tool.dart": "class Tool {}\n"},
    ),
    "root_layout": (
        [
            rule(
                "RULE",
                "root_layout",
                root="app",
                allowed_children=["app.core", "app.ui", "app.data"],
            )
        ],
        {},
        {"lib/extra.dart": "class Extra {}\n"},
    ),
    "sibling_isolation": (
        [rule("RULE", "sibling_isolation", members=["app.core.api", "app.core.impl"])],
        {"lib/core/hidden.dart": "import 'api.dart';\nimport 'impl.dart';\n\nclass Hidden {}\n"},
        {"lib/core/impl.dart": "import 'api.dart';\n\nclass Impl {}\n"},
    ),
    "external_dependency_scope": (
        [
            rule(
                "RULE",
                "external_dependency_scope",
                dependency="dio",
                allowed_sources=["app.ui"],
            )
        ],
        {},
        {"lib/data/store.dart": "import 'package:dio/src/client.dart';\n\nclass Store {}\n"},
    ),
    "external_dependency_scope_dart": (
        [
            rule(
                "RULE",
                "external_dependency_scope",
                dependency="dart",
                allowed_sources=["app.data"],
            )
        ],
        {"lib/data/store.dart": "import 'dart:io';\n\nclass Store {}\n"},
        {"lib/core/impl.dart": "import 'dart:convert';\n\nclass Impl {}\n"},
    ),
    "complete_external_scope": (
        [
            rule("RULE", "complete_external_scope", source="app"),
            rule(
                "SCOPE",
                "external_dependency_scope",
                dependency="dio",
                allowed_sources=["app.ui"],
            ),
        ],
        {},
        {"lib/data/store.dart": "import 'package:hive/hive.dart';\n\nclass Store {}\n"},
    ),
    "interface_boundary": (
        [rule("RULE", "interface_boundary")],
        {},
        {"lib/ui/c.dart": "import 'package:app/core/impl.dart' show Impl;\n\nclass C {}\n"},
    ),
}


@pytest.mark.parametrize("case", sorted(_CASES))
def test_decided_rule_passes_on_a_clean_package(tmp_path: Path, case: str) -> None:
    rules, passing, _ = _CASES[case]
    root = dart_package(
        tmp_path / "pkg",
        {"lib/ui/b.dart": _UI, **passing},
        components=_components(),
        rules=rules,
    )
    result, observation, _ = report_dart(root)
    assert result.exit_code == 0, result.diagnostics
    assert observation is not None
    assert list(observation.records("violations") or ()) == []
    assert result.declared_rules == "PASS"


@pytest.mark.parametrize("case", sorted(_CASES))
def test_decided_rule_fails_on_the_violating_edge(tmp_path: Path, case: str) -> None:
    rules, passing, failing = _CASES[case]
    root = dart_package(
        tmp_path / "pkg",
        {"lib/ui/b.dart": _UI, **passing, **failing},
        components=_components(),
        rules=rules,
    )
    result, observation, _ = report_dart(root)
    assert result.exit_code == 0, result.diagnostics
    assert observation is not None
    violated = {
        (item.kind, rule_id)
        for item in observation.records("violations") or ()
        for rule_id in item.rule_ids
    }
    assert (str(rules[0]["kind"]), "RULE") in violated, violated
    assert result.declared_rules == "FAIL"


def test_forbidden_dependency_on_dart_io_names_the_importer(tmp_path: Path) -> None:
    rules, passing, failing = _CASES["forbidden_dependency_dart_io"]
    root = dart_package(
        tmp_path / "pkg",
        {"lib/ui/b.dart": _UI, **passing, **failing},
        components=_components(),
        rules=rules,
    )
    _, observation, _ = report_dart(root)
    assert observation is not None
    (violation,) = observation.records("violations") or ()
    # The shown name joins the target, the subject shape a Python symbol import already has.
    assert violation.subjects == ("app.core.impl", "dart.io.File")


@pytest.mark.parametrize(
    ("public", "shown", "violates"),
    [
        (["app.core.api:Api"], "Api", False),
        (["app.core.api:Api"], "Other", True),
        (["app.core.api"], "Api, ApiError", False),
        (["app.core.impl"], "Api", True),
    ],
)
def test_interface_boundary_with_show_is_decided_per_name(
    tmp_path: Path, public: list[str], shown: str, violates: bool
) -> None:
    root = dart_package(
        tmp_path / "pkg",
        {"lib/ui/b.dart": f"import 'package:app/core/api.dart' show {shown};\n\nclass B {{}}\n"},
        components=[
            component("core", public=public),
            component("ui", requires=[{"component": "core", "rationale": "Probe."}]),
            component("data"),
        ],
        rules=[rule("RULE", "interface_boundary")],
    )
    result, observation, _ = report_dart(root)
    assert result.exit_code == 0, result.diagnostics
    assert observation is not None
    assert result.declared_rules == ("FAIL" if violates else "PASS")
    assert not [
        item
        for item in observation.records("unknowns") or ()
        if item.kind == "interface_symbol_limit"
    ]
