# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 rows for the Dart profile (AD-97), run on the `fixtures/G-dart` package.

Each row is one of the profile's three answers: a decided PASS or FAIL, an UNKNOWN the scan
counts instead of passing, or input it refuses with exit 2. `fixtures/reproduce_dart.py`
replays the same rows as that story.
"""

from __future__ import annotations

from pathlib import Path

from fixtures.demo_catalog_support import Variant, contract_measurement_budgets, contract_with_rule

DART_FIXTURE_DIR = Path(__file__).resolve().parent / "G-dart"
_DART_HEADER = (
    "// Archkeel\n// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.\n"
    "// SPDX-License-Identifier: MIT\n"
)


def _with_directives(relative: str, after: str, *directives: str) -> str:
    """The clean G-dart file with directive lines inserted after one of its own lines.

    Starting from the committed file keeps each overlay a one-line diff a reader can see,
    and raising on a missing anchor keeps a later fixture edit from silently changing a row.
    """
    text = (DART_FIXTURE_DIR / relative).read_text()
    anchor = f"{after}\n"
    if anchor not in text:
        raise ValueError(f"{relative} has no line {after!r}")
    return text.replace(anchor, anchor + "".join(f"{line}\n" for line in directives), 1)


_REPOSITORY = "lib/domain/repository.dart"
_HTTP_REPOSITORY = "lib/data/http_order_repository.dart"
_ORDER_TILE = "lib/presentation/order_tile.dart"
_DART_IO = "import 'dart:io';"
_DATA_IMPORT = "import 'package:shop/data/http_order_repository.dart';"
_PRESENTATION_IMPORT = "import 'package:shop/presentation/order_page.dart';"
_HTTP_IMPORT = "import 'package:http/http.dart' as http;"
_DRAFT_IMPORT = "import 'package:shop/domain/entities.dart' show OrderDraft;"
_UNSHOWN_REPOSITORY_IMPORT = "import 'package:shop/domain/repository.dart';"
_UTIL_STRINGS = _DART_HEADER + (
    "\nString initials(String name) => name.isEmpty ? '' : name[0].toUpperCase();\n"
)
_TYPING_BUDGET_BASELINE = """{
  "schema_version": "1.2.0",
  "budgets": {"typing_positions": 0},
  "violations": []
}
"""

VARIANTS: tuple[Variant, ...] = (
    Variant(
        id="dart-clean",
        section="clean",
        item="dart:clean",
        summary="The G-dart package as committed: four components, a facade library that "
        "re-exports with `export ... show`, a conditional import, a `part` file and a "
        "`deferred as` import. Every rule decides, so validate exits 0 and report reads PASS.",
        files={},
        expected_violations=(),
        expected_codes=(),
        fixture=DART_FIXTURE_DIR,
        expected_declared_rules="PASS",
    ),
    Variant(
        id="dart-forbidden-dart-io",
        section="class_a",
        item="dart:forbidden_dependency",
        summary="The domain's repository port imports dart:io, which a browser build does not "
        "have. dart: is the standard library and needs no scope rule, so only "
        "DEP-DOMAIN-NO-DART-IO fires.",
        files={_REPOSITORY: _with_directives(_REPOSITORY, "import 'dart:async';", _DART_IO)},
        expected_violations=("DEP-DOMAIN-NO-DART-IO",),
        expected_codes=("rule.violated",),
        fixture=DART_FIXTURE_DIR,
        expected_declared_rules="FAIL",
    ),
    Variant(
        id="dart-complete-requires",
        section="class_a",
        item="dart:complete_requires",
        summary="The HTTP repository imports the order page. data requires only domain, so the "
        "edge is one nobody asked for, and the marked graph drifts with it.",
        files={
            _HTTP_REPOSITORY: _with_directives(
                _HTTP_REPOSITORY,
                "import 'package:shop/domain/repository.dart' show OrderRepository;",
                _PRESENTATION_IMPORT,
            )
        },
        expected_violations=("REQUIRES-COMPLETE",),
        expected_codes=("graph.drift", "rule.violated"),
        fixture=DART_FIXTURE_DIR,
        expected_declared_rules="FAIL",
    ),
    Variant(
        id="dart-component-cycle",
        section="class_a",
        item="dart:no_component_cycles",
        summary="The repository port imports the HTTP repository that implements it, closing "
        "domain -> data -> domain. The same import is also uncovered by any requires entry.",
        files={_REPOSITORY: _with_directives(_REPOSITORY, "import 'entities.dart';", _DATA_IMPORT)},
        expected_violations=("COMPONENT-NO-CYCLES", "REQUIRES-COMPLETE"),
        expected_codes=("graph.drift", "rule.violated", "rule.violated"),
        fixture=DART_FIXTURE_DIR,
        expected_declared_rules="FAIL",
    ),
    Variant(
        id="dart-complete-assignment",
        section="class_a",
        item="dart:complete_assignment",
        summary="lib/util/strings.dart belongs to no component, and shop.util is no declared "
        "child of the package root.",
        files={"lib/util/strings.dart": _UTIL_STRINGS},
        expected_violations=("ASSIGNMENT-COMPLETE", "ROOT-LAYOUT"),
        expected_codes=("rule.violated", "rule.violated"),
        fixture=DART_FIXTURE_DIR,
        expected_declared_rules="FAIL",
    ),
    Variant(
        id="dart-external-scope",
        section="class_a",
        item="dart:external_dependency_scope",
        summary="A widget imports package:http, which EXTERNAL-HTTP-DATA allows in data only.",
        files={
            _ORDER_TILE: _with_directives(
                _ORDER_TILE, "import 'package:flutter/widgets.dart';", _HTTP_IMPORT
            )
        },
        expected_violations=("EXTERNAL-HTTP-DATA",),
        expected_codes=("rule.violated",),
        fixture=DART_FIXTURE_DIR,
        expected_declared_rules="FAIL",
    ),
    Variant(
        id="dart-interface-show",
        section="class_a",
        item="dart:interface_boundary:show",
        summary="A widget imports `entities.dart show OrderDraft`. The `show` names the symbol, "
        "so the rule decides it: OrderDraft is neither exported by the facade nor public by "
        "name.",
        files={
            _ORDER_TILE: _with_directives(
                _ORDER_TILE, "import 'package:shop/domain/domain.dart' show Order;", _DRAFT_IMPORT
            )
        },
        expected_violations=("INTERFACE-BOUNDARY",),
        expected_codes=("rule.violated",),
        fixture=DART_FIXTURE_DIR,
        expected_declared_rules="FAIL",
    ),
    Variant(
        id="dart-interface-unknown",
        section="class_a",
        item="dart:interface_boundary:unknown",
        summary="A widget imports repository.dart without `show`. Only "
        "shop.domain.repository:OrderRepository is public there, and the directive does not say "
        "which names the widget uses: undecided, so UNKNOWN with its count, never PASS and "
        "never a violation. validate still exits 0.",
        files={
            _ORDER_TILE: _with_directives(
                _ORDER_TILE,
                "import 'package:shop/domain/domain.dart' show Order;",
                _UNSHOWN_REPOSITORY_IMPORT,
            )
        },
        expected_violations=(),
        expected_codes=(),
        expected_unknowns=(("interface_symbol_limit", "shop.presentation.order_tile"),),
        fixture=DART_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
    ),
    Variant(
        id="dart-unsupported-rule",
        section="validation",
        item="dart:rule_unsupported_by_profile:rule",
        summary="The contract adds a forbidden_construct rule. The directive scanner sees no "
        "statements, so it refuses the rule with exit 2 instead of passing it unread.",
        files={
            "architecture-contract.json": contract_with_rule(
                {
                    "id": "CONSTRUCT-NO-DYNAMIC",
                    "kind": "forbidden_construct",
                    "source": "shop",
                    "constructs": ["dynamic_import"],
                    "rationale": "A rule the Dart profile cannot evaluate, for the architecture "
                    "demo's rule_unsupported_by_profile coverage.",
                    "provenance": ["docs/architecture/shop.md"],
                    "decided_by": "architect",
                },
                fixture=DART_FIXTURE_DIR,
            )
        },
        expected_violations=(),
        expected_codes=(),
        expected_kinds=("rule_unsupported_by_profile",),
        fixture=DART_FIXTURE_DIR,
    ),
    Variant(
        id="dart-unsupported-budget",
        section="validation",
        item="dart:rule_unsupported_by_profile:measurement_budget",
        summary="The contract selects the typing_positions budget, a scalar the Dart profile "
        "does not measure. A budget on a value that is never measured would always hold, so "
        "it is refused with exit 2.",
        files={
            "architecture-contract.json": contract_measurement_budgets(
                "typing_positions", fixture=DART_FIXTURE_DIR
            ),
            "architecture-baseline.json": _TYPING_BUDGET_BASELINE,
        },
        expected_violations=(),
        expected_codes=(),
        baseline="architecture-baseline.json",
        expected_kinds=("rule_unsupported_by_profile",),
        fixture=DART_FIXTURE_DIR,
    ),
    Variant(
        id="dart-unreadable-header",
        section="validation",
        item="dart:parse_error",
        summary="A new widget's first import has no semicolon. The header no longer fits the "
        "directive grammar, so the file is a coverage failure, exit 2, with no guessed edge.",
        files={
            "lib/presentation/order_badge.dart": _DART_HEADER
            + (
                "\nimport 'package:flutter/widgets.dart'\n"
                "import 'package:shop/domain/domain.dart' show Order;\n\n"
                "Widget orderBadge(Order order) => Text('${order.lines.length}');\n"
            )
        },
        expected_violations=(),
        expected_codes=(),
        expected_kinds=("parse_error",),
        fixture=DART_FIXTURE_DIR,
    ),
    Variant(
        id="dart-tour",
        section="showcase",
        item="dart:tour",
        summary="The Dart rows at once: dart:io in the domain, a domain -> data -> presentation "
        "-> domain cycle, an unowned library, http in a widget, a non-public name imported "
        "with `show`, and one import without `show` that stays UNKNOWN beside the violations.",
        files={
            _REPOSITORY: _with_directives(
                _REPOSITORY, "import 'dart:async';", _DART_IO, _DATA_IMPORT
            ),
            _HTTP_REPOSITORY: _with_directives(
                _HTTP_REPOSITORY,
                "import 'package:shop/domain/repository.dart' show OrderRepository;",
                _PRESENTATION_IMPORT,
            ),
            _ORDER_TILE: _with_directives(
                _ORDER_TILE,
                "import 'package:shop/domain/domain.dart' show Order;",
                _HTTP_IMPORT,
                _DRAFT_IMPORT,
                _UNSHOWN_REPOSITORY_IMPORT,
            ),
            "lib/util/strings.dart": _UTIL_STRINGS,
        },
        expected_violations=(
            "ASSIGNMENT-COMPLETE",
            "COMPONENT-NO-CYCLES",
            "DEP-DOMAIN-NO-DART-IO",
            "EXTERNAL-HTTP-DATA",
            "INTERFACE-BOUNDARY",
            "REQUIRES-COMPLETE",
            "REQUIRES-COMPLETE",
            "ROOT-LAYOUT",
        ),
        expected_codes=("graph.drift", *("rule.violated",) * 8),
        expected_unknowns=(("interface_symbol_limit", "shop.presentation.order_tile"),),
        fixture=DART_FIXTURE_DIR,
        expected_declared_rules="FAIL",
    ),
)
