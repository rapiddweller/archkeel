# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-97: nothing the Dart profile cannot decide may read PASS.

A directive without `show` says which library is imported, never which names are used, so a
rule that is decided per name has undecided positions on Dart: they must reach `unknowns` and
move the verdict to UNKNOWN (AD-92), never pass silently and never become a violation. A rule
kind, declaration or measurement the profile does not observe at all is worse than undecided:
declaring it would buy a PASS for something nobody looked at, so it is an unverifiable input
(exit 2) naming what to remove. A scalar nobody measured is `null`, not a reassuring 0, and a
class D claim whose signal the profile lacks is UNKNOWN, not "0 candidates".

The Python profile must not move while this is added: its result JSON keeps its shape apart
from the documented additive fields.
"""

import json
import subprocess
from pathlib import Path

import pytest
from test_dart_directives import (
    LIBRARIES,
    component,
    dart_package,
    observe_dart,
    report_dart,
    rule,
)

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.report import render_result, run_report
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.model import Observation, Record

_UNMEASURED = (
    "typing_positions",
    "calls_unresolved",
    "private_crossings",
    "untyped_private_accesses",
)


def _unknowns(observation: Observation | None, kind: str) -> list[Record]:
    assert observation is not None
    return [item for item in observation.records("unknowns") or () if item.kind == kind]


def _violations(observation: Observation | None) -> list[Record]:
    assert observation is not None
    return list(observation.records("violations") or ())


def _scalars(payload: dict[str, object]) -> dict[str, object]:
    measurements = payload["measurements"]
    assert isinstance(measurements, dict)
    scalars = measurements["scalars"]
    assert isinstance(scalars, dict)
    return scalars


def _ib_package(tmp_path: Path, public: list[str], files: dict[str, str]) -> Path:
    return dart_package(
        tmp_path / "pkg",
        files,
        components=[
            component("core", public=public),
            component("ui", requires=[{"component": "core", "rationale": "Probe."}]),
            component("data"),
        ],
        rules=[rule("RULE", "interface_boundary")],
    )


# ---------------------------------------------------------------------------------------------
# 5a: interface_boundary without `show`


def test_no_show_import_hiding_a_real_crossing_is_unknown_not_pass(tmp_path: Path) -> None:
    # `Api` is the only public name; the ui library may well use `Internal` from the same
    # library, and without `show` the scanner cannot tell.
    root = _ib_package(
        tmp_path,
        ["app.core.api:Api"],
        {
            "lib/core/api.dart": "class Api {}\n\nclass Internal {}\n",
            "lib/ui/b.dart": "import 'package:app/core/api.dart';\n\nclass B {}\n",
        },
    )
    result, observation, payload = report_dart(root)
    assert result.exit_code == 0, result.diagnostics
    assert result.declared_rules == "UNKNOWN"
    assert _violations(observation) == []
    (record,) = _unknowns(observation, "interface_symbol_limit")
    assert record.rule_ids == ("RULE",)
    assert record.subjects == ("app.ui.b",)
    assert record.data.get("undecided") == 1
    unknown_positions = _scalars(payload)["unknown_positions"]
    assert isinstance(unknown_positions, int)
    assert unknown_positions > 0


def test_undecided_imports_are_counted_once_per_rule(tmp_path: Path) -> None:
    root = _ib_package(
        tmp_path,
        ["app.core.api:Api"],
        {
            "lib/ui/b.dart": "import 'package:app/core/api.dart';\n\nclass B {}\n",
            "lib/ui/c.dart": "import 'package:app/core/api.dart' as core;\n\nclass C {}\n",
            "lib/ui/a.dart": "import 'package:app/core/api.dart' hide Api;\n\nclass A {}\n",
        },
    )
    result, observation, payload = report_dart(root)
    assert result.declared_rules == "UNKNOWN"
    (record,) = _unknowns(observation, "interface_symbol_limit")
    assert record.subjects == ("app.ui.a", "app.ui.b", "app.ui.c")
    assert record.data.get("undecided") == 3
    assert _scalars(payload)["unknown_positions"] == 3


def test_no_show_import_of_a_library_that_exports_is_unknown(tmp_path: Path) -> None:
    # facade.dart is not public but re-exports the public api: what it offers may be public.
    root = _ib_package(
        tmp_path,
        ["app.core.api"],
        {
            "lib/core/facade.dart": "export 'api.dart';\n\nclass Facade {}\n",
            "lib/ui/b.dart": "import 'package:app/core/facade.dart';\n\nclass B {}\n",
        },
    )
    result, observation, _ = report_dart(root)
    assert result.declared_rules == "UNKNOWN"
    assert _violations(observation) == []
    (record,) = _unknowns(observation, "interface_symbol_limit")
    assert record.rule_ids == ("RULE",)


@pytest.mark.parametrize(
    ("public", "imported", "verdict"),
    [
        (["app.core.api"], "api", "PASS"),
        (["app.core.api", "app.core.hidden:Hidden"], "api", "PASS"),
        (["app.core.api"], "impl", "FAIL"),
    ],
)
def test_no_show_import_is_decided_where_the_module_answers(
    tmp_path: Path, public: list[str], imported: str, verdict: str
) -> None:
    root = _ib_package(
        tmp_path,
        public,
        {"lib/ui/b.dart": f"import 'package:app/core/{imported}.dart';\n\nclass B {{}}\n"},
    )
    result, observation, _ = report_dart(root)
    assert result.exit_code == 0, result.diagnostics
    assert result.declared_rules == verdict
    assert _unknowns(observation, "interface_symbol_limit") == []
    assert len(_violations(observation)) == (verdict == "FAIL")


# ---------------------------------------------------------------------------------------------
# 5b: forbidden_dependency with target_symbol


@pytest.mark.parametrize(
    ("directive", "verdict"),
    [
        ("import 'package:app/core/api.dart';", "UNKNOWN"),
        ("import 'package:app/core/api.dart' as core hide Api;", "UNKNOWN"),
        ("import 'package:app/core/api.dart' show Secret;", "FAIL"),
        ("import 'package:app/core/api.dart' show Api;", "PASS"),
    ],
)
def test_forbidden_symbol_without_show_is_unknown(
    tmp_path: Path, directive: str, verdict: str
) -> None:
    root = dart_package(
        tmp_path / "pkg",
        {
            "lib/core/api.dart": "class Api {}\n\nclass Secret {}\n",
            "lib/ui/b.dart": f"{directive}\n\nclass B {{}}\n",
        },
        rules=[
            rule(
                "RULE",
                "forbidden_dependency",
                source="app.ui",
                target="app.core.api",
                target_symbol="Secret",
                include_type_checking=True,
            )
        ],
    )
    result, observation, _ = report_dart(root)
    assert result.exit_code == 0, result.diagnostics
    assert result.declared_rules == verdict
    limits = _unknowns(observation, "dependency_symbol_limit")
    if verdict == "UNKNOWN":
        assert _violations(observation) == []
        (record,) = limits
        assert record.rule_ids == ("RULE",)
        assert record.subjects == ("app.ui.b",)
        assert record.data.get("undecided") == 1
    else:
        assert limits == []


# ---------------------------------------------------------------------------------------------
# Unsupported by the profile: exit 2, never PASS


@pytest.mark.parametrize(
    "unsupported",
    [
        rule(
            "UNSUPPORTED",
            "symbol_placement",
            source="app.core",
            class_kinds=["class"],
            exact_sources=["app.core.api"],
        ),
        rule("UNSUPPORTED", "boundary_types", source="app.core"),
        rule("UNSUPPORTED", "forbidden_construct", source="app", constructs=["dynamic_import"]),
    ],
    ids=lambda item: str(item["kind"]),
)
def test_unsupported_rule_kind_is_unverifiable(
    tmp_path: Path, unsupported: dict[str, object]
) -> None:
    root = dart_package(
        tmp_path / "pkg",
        {"lib/ui/b.dart": "import 'package:app/core/api.dart';\n\nclass B {}\n"},
        components=[
            component("core", public=["app.core.api"]),
            component("ui", requires=[{"component": "core", "rationale": "Probe."}]),
            component("data"),
        ],
        rules=[rule("DECIDED", "complete_requires"), unsupported],
    )
    result, _, payload = report_dart(root)
    assert result.exit_code == 2
    assert result.declared_rules != "PASS"
    matching = [
        item
        for item in result.diagnostics
        if item.kind == "rule_unsupported_by_profile" and item.subject == "UNSUPPORTED"
    ]
    assert matching, result.diagnostics
    assert matching[0].remedy.strip()
    assert "DECIDED" not in {item.subject for item in result.diagnostics}
    diagnostics = payload["diagnostics"]
    assert isinstance(diagnostics, list)
    assert "rule_unsupported_by_profile" in {item["kind"] for item in diagnostics}


def test_context_roots_are_unverifiable(tmp_path: Path) -> None:
    root = dart_package(
        tmp_path / "pkg",
        {"lib/ui/b.dart": "class B {}\n"},
        declarations={"context_roots": ["app"], "context_roots_provenance": ["docs/app.md"]},
    )
    result, _, _ = report_dart(root)
    assert result.exit_code == 2
    assert any(
        item.kind == "rule_unsupported_by_profile" and item.subject == "declarations.context_roots"
        for item in result.diagnostics
    ), result.diagnostics


@pytest.mark.parametrize("name", _UNMEASURED)
def test_budget_on_an_unmeasured_scalar_is_unverifiable(tmp_path: Path, name: str) -> None:
    root = dart_package(
        tmp_path / "pkg",
        {"lib/ui/b.dart": "class B {}\n"},
        declarations={"measurement_budgets": [{"name": name, "provenance": ["docs/app.md"]}]},
    )
    result, _, _ = report_dart(root)
    assert result.exit_code == 2
    assert any(
        item.kind == "rule_unsupported_by_profile"
        and item.subject == f"declarations.measurement_budgets.{name}"
        for item in result.diagnostics
    ), result.diagnostics


def test_budget_on_a_measured_scalar_is_accepted(tmp_path: Path) -> None:
    root = dart_package(
        tmp_path / "pkg",
        {"lib/ui/b.dart": "class B {}\n"},
        declarations={
            "measurement_budgets": [{"name": "cycle_edges", "provenance": ["docs/app.md"]}]
        },
    )
    result, _, _ = report_dart(root)
    assert result.exit_code == 0, result.diagnostics


# ---------------------------------------------------------------------------------------------
# Unmeasured scalars and class D claims


def test_unmeasured_scalars_are_null_and_measured_ones_are_counts(tmp_path: Path) -> None:
    root = dart_package(
        tmp_path / "pkg",
        {"lib/ui/b.dart": "import 'package:app/core/api.dart';\n\nclass B {}\n"},
    )
    result, _, payload = report_dart(root)
    assert result.exit_code == 0, result.diagnostics
    scalars = _scalars(payload)
    for name in _UNMEASURED:
        assert name in scalars
        assert scalars[name] is None, name
    for name in ("cycle_edges", "violations", "coverage_failures", "unknown_positions"):
        assert type(scalars[name]) is int, name
    coverage = payload["coverage"]
    assert isinstance(coverage, dict)
    assert coverage["calls_analyzed"] == 0
    assert coverage["calls_unresolved"] == 0


def test_claims_without_their_signal_are_unknown_not_zero(tmp_path: Path) -> None:
    root = dart_package(
        tmp_path / "pkg",
        {"lib/ui/b.dart": "import 'package:app/core/api.dart';\n\nclass B {}\n"},
    )
    result, observation, payload = report_dart(root)
    assert result.exit_code == 0, result.diagnostics
    assert observation is not None
    assert observation.records("references") is None
    assert observation.records("bindings") is None
    claims = payload["claims"]
    assert isinstance(claims, dict)
    assert claims["unreferenced_symbols"] is None
    assert claims["unread_bindings"] is None
    assert result.claims is not None
    assert result.claims.unreferenced_symbols is None
    assert result.claims.unread_bindings is None


def test_dart_observation_sections_it_does_not_observe_are_empty(tmp_path: Path) -> None:
    root = dart_package(tmp_path / "pkg", {"lib/ui/b.dart": "class B {}\n"})
    result = observe_dart(root)
    assert result.diagnostics == ()
    observation = result.observation
    assert observation is not None
    for section in (
        "calls",
        "typing_signals",
        "constructs",
        "contexts",
        "context_evidence",
    ):
        assert observation.records(section) == (), section
    # Absent, not empty: a claim reading symbols must say UNKNOWN, never "0 candidates".
    assert observation.records("symbols") is None
    assert observation.coverage.files_discovered == len(LIBRARIES) + 1
    assert list(observation.source.scope) == ["lib/**/*.dart"]


# ---------------------------------------------------------------------------------------------
# Python stays as it was


def test_python_result_json_changes_only_by_the_additive_fields(tmp_path: Path) -> None:
    root = tmp_path / "py"
    (root / "sample/core").mkdir(parents=True)
    (root / "sample/cli").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (root / "contract.json").write_text(
        json.dumps({"schema_version": "2.1.0", "components": [], "rules": []})
    )
    for relative, text in {
        "sample/__init__.py": "",
        "sample/core/__init__.py": "",
        "sample/cli/__init__.py": "",
        "sample/core/api.py": "def run() -> int:\n    return 1\n",
        "sample/cli/main.py": "from sample.core import api\nimport sample.core.api\n",
    }.items():
        (root / relative).write_text(text)
    for args in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "py@example.invalid"],
        ["git", "config", "user.name", "Py"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "package"],
    ):
        subprocess.run(args, cwd=root, check=True, capture_output=True)
    config = ScanConfig(("sample",), "sample", "contract.json", "0" * 64)
    assert config.language == "python"
    result, architecture = run_report(root, config=config, analyzer=observe)
    assert result.exit_code == 0, result.diagnostics
    payload = json.loads(render_result(result))
    # Every key the result carried before, plus only the documented additive scalar.
    assert _scalars(payload) == {
        "calls_unresolved": 0,
        "coverage_failures": 0,
        "cycle_edges": 0,
        "private_crossings": 0,
        "typing_positions": 0,
        "unknown_positions": 0,
        "untyped_private_accesses": 0,
        "violations": 0,
    }
    assert set(payload) == {
        "agent_decisions",
        "artifact",
        "baseline_new",
        "baseline_resolved",
        "claims",
        "command",
        "coverage",
        "declared_rules",
        "delta",
        "diagnostics",
        "draft_sizes",
        "exit_code",
        "expectation_fulfilled",
        "failures",
        "filtered_violations",
        "git_predicate",
        "host_order",
        "host_source",
        "measurements",
        "observation",
        "observation_complete",
        "open_decisions",
        "provenance",
        "python_version",
        "report_filter",
        "violations_by_component_pair",
        "violations_by_rule",
    }
    claims = payload["claims"]
    assert isinstance(claims, dict)
    assert claims["unreferenced_symbols"] is not None
    assert claims["unread_bindings"] is not None
    assert architecture is not None
    model = json.loads(architecture)
    assert model["analyzer"]["name"] != "archkeel-dart-directives"
    observation = parse_observation(decode_canonical_model(model))
    records = observation.records("imports") or ()
    assert len(records) == 2
    assert all(item.data.get("symbols_known") is True for item in records)
