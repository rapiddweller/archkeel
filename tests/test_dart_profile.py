# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-97: the Dart profile reads directives, and what it cannot see is UNKNOWN, never PASS."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from archkeel.analyzer import observe
from archkeel.analyzer.embedded.dart_directives import read_header
from archkeel.analyzer.embedded.dart_lexer import DirectiveError
from archkeel.check.ports import ScanConfig
from archkeel.check.ratchets import measure_python_ratchets
from archkeel.check.run import inspect_observation
from archkeel.check.validation import run_validate
from archkeel.cli.config import ConfigError, parse_config
from archkeel.ir.codec import (
    baseline_bytes,
    canonical_report_bytes,
    decode_canonical_model,
    decode_json,
    parse_measurements,
    parse_observation,
    result_payload,
)
from archkeel.ir.decisions import review_claims
from archkeel.ir.measurements import MeasurementBudget, compare_measurements
from archkeel.ir.model import ObservationResult, RunResult

_BASE = {"schema_version": "2.1.0", "components": [], "rules": []}


def _component(label: str, package: str, **fields: Any) -> dict[str, Any]:
    return {
        "id": f"COMP-{label.upper()}",
        "label": label,
        "role": "component",
        "packages": [package],
        "responsibilities": [f"{label}."],
        "forbidden_responsibilities": [],
        "provenance": ["pubspec.yaml"],
        "decided_by": "architect",
        **fields,
    }


def _rule(rule_id: str, kind: str, **fields: Any) -> dict[str, Any]:
    return {
        "id": rule_id,
        "kind": kind,
        "rationale": "The sample needs this decision for its own reasons.",
        "provenance": ["pubspec.yaml"],
        "decided_by": "architect",
        **fields,
    }


def _observe(root: Path, files: dict[str, str], contract: dict[str, Any] | None = None):
    (root / "pubspec.yaml").write_text("name: app\n")
    (root / "contract.json").write_text(json.dumps({**_BASE, **(contract or {})}))
    for relative, text in files.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(text)
    return observe(
        root,
        roots=("lib",),
        namespace="app",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
        language="dart",
    )


def _imports(result: ObservationResult) -> set[tuple[str, str, str | None]]:
    assert result.observation is not None
    return {
        (str(item.data.get("source_module")), str(item.data.get("target_module")), symbol)
        for item in result.observation.records("imports") or ()
        if isinstance(symbol := item.data.get("symbol"), str | None)
    }


def test_header_grammar_reads_every_directive_form() -> None:
    header = read_header(
        "#!/usr/bin/env dart\n/// Doc.\n/* a /* nested */ b */\n@Tags(['x', (1)])\n"
        "@pkg.Meta()\nlibrary app.main;\n"
        "import r'a.dart' deferred as a show X, Y hide Z;\n"
        "import 'b' '.dart' if (dart.library.io) '''c.dart''' if (x.y == 'z') \"d.dart\";\n"
        "export 'e.dart' hide Q;\npart 'f.dart';\n"
        "void main() { const s = \"import 'g.dart';\"; }\nimport 'never.dart';\n"
    )
    assert [(item.kind, item.uris, item.shown) for item in header.directives] == [
        ("import", ("a.dart",), ("X", "Y")),
        ("import", ("b.dart", "c.dart", "d.dart"), ()),
        ("export", ("e.dart",), ()),
    ]
    assert [part.uri for part in header.parts] == ["f.dart"]
    assert read_header("part of 'main.dart';\nclass A {}\n").part_of == "main.dart"


@pytest.mark.parametrize(
    "source",
    ["import 'a$b.dart';\n", "import 'a${b}.dart';\n", "import 'a.dart'\nclass A {}\n", "/* x"],
)
def test_header_outside_the_grammar_is_an_error(source: str) -> None:
    with pytest.raises(DirectiveError):
        read_header(source)


def test_uris_map_to_dotted_modules_and_parts_are_not_modules(tmp_path: Path) -> None:
    result = _observe(
        tmp_path,
        {
            "lib/app.dart": "import 'package:app/src/app.config.dart';\n"
            "import 'src/model.dart' show Order;\nimport 'dart:io';\n"
            "import 'package:http/http.dart';\nimport 'package:bloc/bloc-base.dart';\n",
            "lib/src/app.config.dart": "",
            "lib/src/model.dart": "part 'model_part.dart';\nclass Order {}\n",
            "lib/src/model_part.dart": "part of 'model.dart';\n",
        },
    )
    assert result.exit_code == 0, result.diagnostics
    assert _imports(result) == {
        ("app.app", "app.src.app_config", None),
        ("app.app", "app.src.model", "Order"),
        ("app.app", "dart.io", None),
        ("app.app", "http.http", None),
        ("app.app", "bloc.bloc_base", None),
    }
    observation = result.observation
    assert observation is not None
    modules = {item.data.get("qualified_name") for item in observation.records("modules") or ()}
    assert modules == {"app.app", "app.src.app_config", "app.src.model"}
    assert observation.coverage.files_parsed == 4


@pytest.mark.parametrize(
    "files",
    [
        {"lib/a.dart": "import '../outside.dart';\n"},
        {"lib/a.dart": "import 'package:app/missing.dart';\n"},
        {"lib/a.dart": "", "lib/orphan.dart": "part of 'a.dart';\n"},
        {"lib/a-b.dart": "", "lib/a_b.dart": ""},
        {"lib/a.dart": "import 'x.dart'\n"},
    ],
)
def test_undecidable_input_is_exit_2(tmp_path: Path, files: dict[str, str]) -> None:
    result = _observe(tmp_path, files)
    assert result.exit_code == 2
    assert {item.kind for item in result.diagnostics} == {"parse_error"}


def test_pubspec_name_must_be_the_namespace(tmp_path: Path) -> None:
    result = _observe(tmp_path, {"lib/a.dart": ""})
    assert result.exit_code == 0
    (tmp_path / "pubspec.yaml").write_text("name: other # comment\n")
    mismatch = observe(
        tmp_path,
        roots=("lib",),
        namespace="app",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
        language="dart",
    )
    assert mismatch.exit_code == 2
    assert "'other'" in mismatch.diagnostics[0].unknown_claim


_LAYERS = {
    "components": [
        _component("model", "app.model", public=["app.model.api:Order"]),
        _component("ui", "app.ui"),
    ],
}


def test_interface_boundary_without_show_is_unknown_not_pass(tmp_path: Path) -> None:
    files = {
        "lib/model/api.dart": "class Order {}\nclass Secret {}\n",
        "lib/ui/view.dart": "import 'package:app/model/api.dart';\n",
    }
    contract = {**_LAYERS, "rules": [_rule("IFACE", "interface_boundary")]}
    result = _observe(tmp_path, files, contract)
    assert result.observation is not None
    measurements, verdict = inspect_observation(result.observation)
    assert verdict == "UNKNOWN"
    assert measurements.scalars.unknown_positions == 1

    shown = {**files, "lib/ui/view.dart": "import 'package:app/model/api.dart' show Secret;\n"}
    decided = _observe(tmp_path, shown, contract)
    assert decided.observation is not None
    assert inspect_observation(decided.observation)[1] == "FAIL"


def test_forbidden_symbol_without_show_is_unknown_and_sdk_target_decides(tmp_path: Path) -> None:
    files = {
        "lib/model/api.dart": "class Order {}\n",
        "lib/ui/view.dart": "import 'package:app/model/api.dart';\nimport 'dart:io';\n",
    }
    rules = [
        _rule(
            "NO-ORDER",
            "forbidden_dependency",
            source="app.ui",
            target="app.model.api",
            target_symbol="Order",
            include_type_checking=False,
        ),
    ]
    result = _observe(tmp_path, files, {**_LAYERS, "rules": rules})
    assert result.observation is not None
    assert inspect_observation(result.observation)[1] == "UNKNOWN"

    sdk = [
        _rule(
            "NO-IO",
            "forbidden_dependency",
            source="app.ui",
            target="dart.io",
            include_type_checking=False,
        )
    ]
    decided = _observe(tmp_path, files, {**_LAYERS, "rules": sdk})
    assert decided.observation is not None
    assert inspect_observation(decided.observation)[1] == "FAIL"
    misspelt = [{**sdk[0], "target": "dart.iox"}]
    assert _observe(tmp_path, files, {**_LAYERS, "rules": misspelt}).diagnostics[0].kind == (
        "rule_without_subjects"
    )


@pytest.mark.parametrize(
    "contract",
    [
        {"rules": [_rule("NO-ANY", "forbidden_construct", source="app", constructs=["cast"])]},
        {
            "declarations": {
                "context_roots": ["app.a"],
                "context_roots_provenance": ["pubspec.yaml"],
            }
        },
        {
            "declarations": {
                "measurement_budgets": [
                    {"name": "typing_positions", "provenance": ["pubspec.yaml"]}
                ]
            }
        },
    ],
)
def test_what_the_profile_cannot_decide_is_refused(tmp_path: Path, contract: dict) -> None:
    result = _observe(tmp_path, {"lib/a.dart": ""}, contract)
    assert result.exit_code == 2
    assert [item.kind for item in result.diagnostics] == ["rule_unsupported_by_profile"]


def test_unmeasured_scalars_and_absent_signals_are_null(tmp_path: Path) -> None:
    result = _observe(tmp_path, {"lib/a.dart": "import 'b.dart';\n", "lib/b.dart": ""})
    observation = result.observation
    assert observation is not None
    measurements = measure_python_ratchets(observation)
    scalars = dict(measurements.scalars.items())
    assert [name for name, value in scalars.items() if value is None] == [
        "private_crossings",
        "typing_positions",
        "calls_unresolved",
        "untyped_private_accesses",
    ]
    assert {status for *_, status in compare_measurements(measurements, measurements)} == {
        "PASS",
        "n/a",
    }
    payload = result_payload(RunResult("report", 0, measurements=measurements))
    assert parse_measurements(payload["measurements"], "result") == measurements
    claims = review_claims(observation)
    assert claims.unreferenced_symbols is None and claims.unread_bindings is None
    assert claims.type_fanin is None and claims.repeated_logic is None
    raw = decode_canonical_model(decode_json(canonical_report_bytes(observation)))
    assert raw["symbols"] is None and raw["references"] is None and raw["bindings"] is None
    assert parse_observation(raw) == observation


def test_config_language_is_optional_and_closed() -> None:
    base = b'[scan]\nroots = ["lib"]\nnamespace = "app"\ncontract = "c.json"\n'
    assert parse_config(base).language == "python"
    assert parse_config(base + b'language = "dart"\n').language == "dart"
    with pytest.raises(ConfigError):
        parse_config(base + b'language = "go"\n')


def _committed(root: Path, files: dict[str, str], contract: dict[str, Any]) -> ScanConfig:
    _observe(root, files, contract)
    identity = ["-c", "user.email=a@example.invalid", "-c", "user.name=A"]
    for command in (["init", "-q"], [*identity, "add", "."], [*identity, "commit", "-qm", "d"]):
        subprocess.run(["git", *command], cwd=root, check=True)
    return ScanConfig(("lib",), "app", "contract.json", "", "dart")


def test_validate_reads_sdk_targets_and_refuses_unmeasured_budgets(tmp_path: Path) -> None:
    """A6: `dart.io` is a valid forbidden target before any scan; A7: the profile gate wins."""
    rules = [
        _rule(
            "NO-IO",
            "forbidden_dependency",
            source="app.ui",
            target="dart.io",
            include_type_checking=False,
        )
    ]
    files = {"lib/ui/view.dart": "import 'dart:io';\n", "lib/model/api.dart": ""}
    config = _committed(tmp_path, files, {**_LAYERS, "rules": rules})
    result, _ = run_validate(tmp_path, config, observe)
    assert "reference.namespace" not in {item.code for item in result.diagnostics}
    assert result.violations_by_rule == (("NO-IO", 1),)

    budgets = [{"name": "typing_positions", "provenance": ["pubspec.yaml"]}]
    contract = {**_LAYERS, "rules": rules, "declarations": {"measurement_budgets": budgets}}
    (tmp_path / "contract.json").write_text(json.dumps({**_BASE, **contract}))
    baseline = tmp_path / "baseline.json"
    baseline.write_bytes(baseline_bytes((), (MeasurementBudget("typing_positions", 0),)))
    refused, _ = run_validate(tmp_path, config, observe, baseline=baseline)
    assert refused.exit_code == 2
    assert [item.kind for item in refused.diagnostics] == ["rule_unsupported_by_profile"]
