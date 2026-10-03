# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent acceptance: every rule and measurement has visible TypeScript evidence."""

import json
from dataclasses import fields
from pathlib import Path
from typing import get_args

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from archkeel.ir.codec import observation_payload
from archkeel.ir.measurements import (
    SCALARS,
    Measurements,
    NameBudgetKind,
    RatchetScalars,
    compare_measurements,
)
from archkeel.ir.model import RULE_KINDS
from archkeel.ir.structure import StructureMetric, module_edges, structure_metrics
from archkeel.ir.trace import trace_valid_violations
from fixtures.demo_catalog_typescript import (
    MEASUREMENT_EXAMPLES,
    NAME_BUDGET_EXAMPLES,
    RULE_EXAMPLES,
    STRUCTURE_EXAMPLES,
    UNMEASURED,
    VARIANTS,
)
from fixtures.reproduce_typescript import ADAPTER, Outcome, run_variant


def test_catalog_exhausts_rule_and_measurement_vocabulary() -> None:
    assert set(RULE_EXAMPLES) == RULE_KINDS
    assert set(NAME_BUDGET_EXAMPLES) == set(get_args(NameBudgetKind))
    assert set(MEASUREMENT_EXAMPLES) == set(SCALARS)
    assert set(MEASUREMENT_EXAMPLES) == {field.name for field in fields(RatchetScalars)}
    assert {field.name for field in fields(Measurements)} == {
        "scalars",
        "calls_total",
        "resolution",
    }
    assert set(STRUCTURE_EXAMPLES) == {field.name for field in fields(StructureMetric)}
    ids = {variant.id for variant in VARIANTS}
    assert len(ids) == len(VARIANTS)
    for examples in (
        *RULE_EXAMPLES.values(),
        *MEASUREMENT_EXAMPLES.values(),
        *STRUCTURE_EXAMPLES.values(),
        *NAME_BUDGET_EXAMPLES.values(),
    ):
        assert examples
        assert {f"typescript-{name}" for name in examples} <= ids


@pytest.fixture(scope="module")
def outcomes(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Outcome]:
    assert ADAPTER.is_file(), (
        "run make -C packages/typescript-adapter install build before TypeScript acceptance"
    )
    workspace = tmp_path_factory.mktemp("typescript-demo")
    return {variant.id: run_variant(workspace, variant) for variant in VARIANTS}


@pytest.mark.parametrize("variant", VARIANTS, ids=lambda variant: variant.id)
def test_each_demo_matches_independent_expectation(variant, outcomes: dict[str, Outcome]) -> None:
    outcome = outcomes[variant.id]
    if variant.expected_kinds:
        for result in (outcome.validation, outcome.report):
            assert result.exit_code == 2
            assert {item.kind for item in result.diagnostics} >= set(variant.expected_kinds)
            assert result.measurements is None
        return
    assert outcome.observation is not None
    assert outcome.report.declared_rules == variant.expected_declared_rules
    violations = trace_valid_violations(outcome.observation)
    assert sorted(rule for record in violations for rule in record.rule_ids) == sorted(
        variant.expected_violations
    )
    assert outcome.report.measurements is not None
    assert outcome.report.measurements.scalars.violations == len(violations)
    assert sorted(item.code for item in outcome.validation.diagnostics if item.code) == sorted(
        variant.expected_codes
    )
    for name in UNMEASURED:
        assert dict(outcome.report.measurements.scalars.items())[name] is None
    assert outcome.report.measurements.calls_total is None
    assert outcome.report.measurements.resolution == "n/a"
    assert outcome.observation.records("calls") is None
    assert outcome.observation.records("symbols") is None


def test_clean_graph_has_independently_counted_modules_and_edges(
    outcomes: dict[str, Outcome],
) -> None:
    outcome = outcomes["typescript-clean"]
    observation = outcome.observation
    assert observation is not None
    assert len(observation.records("modules") or ()) == 7
    assert len(module_edges(observation)) == 8
    metrics = {
        metric.scope: (metric.modules, metric.inner_edges, metric.fan_in, metric.fan_out)
        for metric in structure_metrics(observation)
        if metric.level == "component"
    }
    assert metrics == {
        "app": (1, 0, 0, 2),
        "data": (2, 0, 1, 2),
        "presentation": (1, 0, 1, 1),
        "domain": (3, 3, 3, 0),
    }
    assert outcome.report.measurements is not None
    scalars = dict(outcome.report.measurements.scalars.items())
    assert {
        name: scalars[name]
        for name in ("violations", "cycle_edges", "coverage_failures", "unknown_positions")
    } == {"violations": 0, "cycle_edges": 0, "coverage_failures": 0, "unknown_positions": 0}


def test_real_typescript_demo_matches_decoded_profile_schema(outcomes: dict[str, Outcome]) -> None:
    root = Path(__file__).parents[1]
    schemas = [json.loads(path.read_bytes()) for path in (root / "schema").glob("*.json")]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    schema = json.loads((root / "schema/architecture-ir-decoded.schema.json").read_bytes())
    observation = outcomes["typescript-clean"].observation
    assert observation is not None
    errors = list(
        Draft202012Validator(schema, registry=registry).iter_errors(
            observation_payload(observation)
        )
    )
    assert not errors


def test_module_cycle_is_not_a_component_cycle(outcomes: dict[str, Outcome]) -> None:
    outcome = outcomes["typescript-module-cycle"]
    assert outcome.observation is not None
    cycles = outcome.observation.records("cycles") or ()
    assert any(record.kind == "module_scc" for record in cycles)
    assert not any(record.kind == "component_scc" for record in cycles)
    assert outcome.report.measurements is not None
    assert outcome.report.measurements.scalars.cycle_edges == 2


@pytest.mark.parametrize("case", ["computed-import", "indirect-require"])
def test_unobserved_loader_preserves_unknown(outcomes: dict[str, Outcome], case: str) -> None:
    outcome = outcomes[f"typescript-{case}"]
    assert outcome.report.declared_rules == "UNKNOWN"
    assert outcome.report.exit_code == 2
    assert outcome.report.measurements is None
    assert outcome.observation is not None
    assert outcome.observation.records("unknowns")
    assert outcome.observation.coverage.failures


@pytest.mark.parametrize(
    ("case", "rule"),
    (("unsupported-symbol-interface", "PROBE"), ("unsupported-symbol-requires", "REQUIRES")),
)
def test_unsupported_symbol_declaration_does_not_prove_a_violation(
    outcomes: dict[str, Outcome],
    case: str,
    rule: str,
) -> None:
    outcome = outcomes[f"typescript-{case}"]
    assert outcome.report.exit_code == 2
    if outcome.observation is not None:
        assert not any(
            rule in record.rule_ids for record in trace_valid_violations(outcome.observation)
        )


def test_demo_retains_normal_artifacts(tmp_path: Path) -> None:
    outcome = run_variant(tmp_path, VARIANTS[0])
    root = tmp_path / outcome.variant.id
    for name in ("validation-result.json", "report-result.json", "architecture.json"):
        assert (root / name).is_file()
    measurements = json.loads((root / "report-result.json").read_bytes())["measurements"]
    assert measurements["calls_total"] is None
    assert measurements["scalars"]["calls_unresolved"] is None
    assert measurements["resolution"] == "n/a"


@pytest.mark.parametrize(
    "statement",
    (
        'import { local } from "../data/local";',
        'export { local } from "../data/local";',
        'export * from "../data/local";',
        'export type { local } from "../data/local";',
        'export type Local = typeof import("../data/local").local;',
        'export const load = () => import("../data/local");',
        'const local = require("../data/local");',
    ),
)
def test_supported_import_forms_enforce_direction(tmp_path: Path, statement: str) -> None:
    from dataclasses import replace

    from fixtures.demo_catalog_typescript import appended

    variant = replace(
        VARIANTS[0],
        id="typescript-import-form",
        files={"src/domain/order.ts": appended("src/domain/order.ts", statement + "\n")},
    )
    outcome = run_variant(tmp_path, variant)
    assert outcome.observation is not None
    assert "DOMAIN-NO-DATA" in {
        rule for record in trace_valid_violations(outcome.observation) for rule in record.rule_ids
    }


def test_supported_absence_requires_observed_runtime_closure(tmp_path: Path) -> None:
    from dataclasses import replace

    from fixtures.demo_catalog_typescript import appended

    variant = replace(
        VARIANTS[0],
        id="typescript-runtime-closure",
        files={
            "src/main.ts": appended("src/main.ts", 'import { value } from "../runtime.cjs";\n'),
            "runtime.d.cts": "export declare const value: string;\n",
            "runtime.cjs": 'module.exports = require("./missing-runtime.cjs");\n',
        },
    )
    outcome = run_variant(tmp_path, variant)
    assert outcome.report.exit_code == 2 or outcome.report.declared_rules == "UNKNOWN"
    assert outcome.report.declared_rules != "PASS"


def test_structure_does_not_turn_unmeasured_calls_into_zero(outcomes: dict[str, Outcome]) -> None:
    observation = outcomes["typescript-clean"].observation
    assert observation is not None
    for metric in structure_metrics(observation):
        assert metric.calls is None
        assert metric.unresolved is None


def test_path_identity_preserves_extension_index_and_literal_escape(tmp_path: Path) -> None:
    from dataclasses import replace

    variant = replace(
        VARIANTS[0],
        id="typescript-path-identities",
        files={
            "src/domain/foo.ts": "export const value = 1;\n",
            "src/domain/foo/index.ts": "export const value = 2;\n",
            "src/domain/foo_x2e_ts.ts": "export const value = 3;\n",
            "src/domain/order-id.ts": "export const value = 4;\n",
            "src/domain/foo.test.ts": "export const test = 5;\n",
        },
    )
    outcome = run_variant(tmp_path, variant)
    assert outcome.observation is not None
    modules = {
        record.data.get("qualified_name") for record in outcome.observation.records("modules") or ()
    }
    assert modules >= {
        "shop.src.domain.foo_x2e_ts",
        "shop.src.domain.foo.index_x2e_ts",
        "shop.src.domain.foo_x5f_x2e_x5f_ts_x2e_ts",
        "shop.src.domain.order_x2d_id_x2e_ts",
    }
    assert "shop.src.domain.foo_x2e_test_x2e_ts" not in modules
    assert len(modules) == 11


def test_project_scripts_and_tsconfig_plugins_are_not_executed(tmp_path: Path) -> None:
    import json
    from dataclasses import replace

    from fixtures.demo_catalog_typescript import TYPESCRIPT_FIXTURE_DIR

    config = json.loads((TYPESCRIPT_FIXTURE_DIR / "tsconfig.json").read_text())
    config["compilerOptions"]["plugins"] = [{"name": "./plugin.cjs"}]
    variant = replace(
        VARIANTS[0],
        id="typescript-no-project-execution",
        files={
            "tsconfig.json": json.dumps(config),
            "package.json": json.dumps(
                {
                    "name": "shop",
                    "scripts": {"prepare": "node plugin.cjs", "postinstall": "node plugin.cjs"},
                }
            ),
            "plugin.cjs": 'require("node:fs").writeFileSync("EXECUTED", "bad");\n',
        },
    )
    outcome = run_variant(tmp_path, variant)
    assert outcome.report.exit_code == 0
    assert not (tmp_path / variant.id / "EXECUTED").exists()


def test_measurement_regressions_preserve_unmeasured_state(outcomes: dict[str, Outcome]) -> None:
    accepted = outcomes["typescript-clean"].report.measurements
    candidate = outcomes["typescript-module-cycle"].report.measurements
    assert accepted is not None and candidate is not None
    comparisons = {
        name: verdict for name, _, _, verdict in compare_measurements(accepted, candidate)
    }
    assert comparisons == {
        "violations": "FAIL",
        "cycle_edges": "FAIL",
        "coverage_failures": "PASS",
        "unknown_positions": "PASS",
        "private_crossings": "n/a",
        "typing_positions": "n/a",
        "calls_unresolved": "n/a",
        "untyped_private_accesses": "n/a",
        "unresolved_ratio": "n/a",
    }
    assert outcomes["typescript-computed-import"].report.measurements is None


def test_missing_configured_process_has_no_language_fallback(tmp_path: Path) -> None:
    from archkeel.check.report import run_report
    from archkeel.cli.config import load_config
    from archkeel.cli.observe import observer_for
    from fixtures.reproduce_typescript import repository

    root = repository(tmp_path, VARIANTS[0])
    config = load_config(root)
    configured = observer_for(
        config.language,
        collector_argv=(str(tmp_path / "missing-collector"),),
        tsconfig=config.tsconfig or "tsconfig.json",
    )
    result, artifact = run_report(root, config=config, analyzer=configured)
    assert result.exit_code == 2
    assert {item.kind for item in result.diagnostics} == {"missing_tool"}
    assert result.measurements is None
    assert artifact is None


def test_replacement_executable_is_actually_called(tmp_path: Path) -> None:
    import json
    import shutil
    import sys

    from archkeel.check.report import run_report
    from archkeel.cli.config import load_config
    from archkeel.cli.observe import observer_for
    from fixtures.reproduce_typescript import repository

    node = shutil.which("node")
    assert node is not None
    marker = tmp_path / "collector-called"
    replacement = tmp_path / "collector.py"
    replacement.write_text(
        "import os\nfrom pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('called')\n"
        f"os.execv({node!r}, [{node!r}, {str(ADAPTER)!r}])\n"
    )
    root = repository(tmp_path, VARIANTS[0])
    config_path = root / "archkeel.toml"
    config_path.write_text(
        "\n".join(
            line
            for line in config_path.read_text().splitlines()
            if not line.startswith("collector_argv")
        )
        + "\ncollector_argv = "
        + json.dumps([sys.executable, str(replacement)])
        + "\n"
    )
    config = load_config(root)
    configured = observer_for(
        config.language,
        collector_argv=config.collector_argv,
        tsconfig=config.tsconfig or "tsconfig.json",
    )
    result, artifact = run_report(root, config=config, analyzer=configured)
    assert marker.read_text() == "called"
    assert result.declared_rules == "PASS"
    assert artifact is not None


def test_same_snapshot_produces_identical_observation(tmp_path: Path) -> None:
    from archkeel.check.report import run_report
    from archkeel.cli.config import load_config
    from archkeel.cli.observe import observer_for
    from fixtures.reproduce_typescript import repository

    root = repository(tmp_path, VARIANTS[0])
    config = load_config(root)
    configured = observer_for(
        config.language,
        collector_argv=config.collector_argv,
        tsconfig=config.tsconfig or "tsconfig.json",
    )
    first, first_artifact = run_report(root, config=config, analyzer=configured)
    second, second_artifact = run_report(root, config=config, analyzer=configured)
    assert first_artifact is not None
    assert first_artifact == second_artifact
    assert first.measurements == second.measurements


def test_package_cycles_follow_typescript_directories(outcomes: dict[str, Outcome]) -> None:
    observation = outcomes["typescript-component-cycle"].observation
    assert observation is not None
    packages = [
        record for record in observation.records("cycles") or () if record.kind == "package_scc"
    ]
    assert len(packages) == 1
    assert set(packages[0].subjects) == {"shop.src.data", "shop.src.domain"}
    assert packages[0].data.get("backed_by")
    measurements = outcomes["typescript-component-cycle"].report.measurements
    assert measurements is not None
    assert measurements.scalars.cycle_edges == 4


def test_incomplete_scan_keeps_known_violations_and_unknown_evidence(
    outcomes: dict[str, Outcome],
) -> None:
    outcome = outcomes["typescript-mixed-known-and-unknown"]
    assert outcome.observation is not None
    assert outcome.observation.records("unknowns")
    assert {
        rule for record in trace_valid_violations(outcome.observation) for rule in record.rule_ids
    } == {"COMPONENT-CYCLES", "DOMAIN-NO-DATA", "MODULE-CYCLES", "REQUIRES"}
    assert outcome.report.exit_code == 2
    assert outcome.report.measurements is None
