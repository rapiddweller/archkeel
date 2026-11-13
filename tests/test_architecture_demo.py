# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11: every catalogued demo variant produces its declared findings, or cites evidence."""

import json
import shutil
import subprocess
from dataclasses import fields as dataclass_fields
from pathlib import Path
from typing import get_args, get_type_hints

import pytest
from archkeel.check.expectation import GUARDRAIL_DIMENSIONS
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.check.validation import run_validate
from archkeel.cli.config import load_config
from archkeel.cli.observe import observe, observer_for
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.measurements import SCALARS
from archkeel.ir.model import (
    ArchitectureRule,
    ContractDeclarations,
    DiagnosticCode,
    DiagnosticKind,
    ForbiddenConstructKind,
    RuleVerdict,
)
from archkeel.ir.trace import trace_valid_violations
from archkeel.render.html import render_architecture_html
from archkeel.render.summary import badge, report_summary
from fixtures.architecture_demo import CATALOG, markdown
from fixtures.demo_catalog_support import FIXTURE_DIR, Variant, apply_overlay

from archkeel.cli import main
from tools.dual_run_corpus import Case, case_language

SUPPORTED_CATALOG = tuple(
    variant
    for variant in CATALOG
    if not variant.explore
    and case_language(
        Case(variant.id, str(variant.fixture), variant.config, files=dict(variant.files))
    )
    in {"rust", "typescript"}
)

ROOT = Path(__file__).parents[1]
CONFIG = ScanConfig(("shop",), "shop", "architecture-contract.json", "0" * 64)
_SAMPLE_VARIANTS = [
    variant
    for variant in SUPPORTED_CATALOG
    if variant.evidence is None
    and variant.check is None
    and variant.against is None
    and variant.view is None
    and variant.report is None
    and variant.typescript_trace is None
    and not variant.explore
]
_CHECK_VARIANTS = [variant for variant in CATALOG if variant.check is not None]
_AGAINST_VARIANTS = [variant for variant in CATALOG if variant.against is not None]
# A scalar row and its guardrail row share one CheckExpectation, so each protocol runs once.
_UNIQUE_CHECK_RUNS = list({id(variant.check): variant for variant in _CHECK_VARIANTS}.values())
# Raising these makes typed code raise instead of returning FAIL; see demo_catalog_evidence.py.
_CLASS_B_TESTED_ONLY = {
    "SCALARS:coverage_failures",
    "GUARDRAIL_DIMENSIONS:unknowns",
    "GUARDRAIL_DIMENSIONS:dependency_edges",
    "coverage_must_pass",
}


def test_variant_ids_are_unique() -> None:
    ids = [variant.id for variant in CATALOG]
    assert len(ids) == len(set(ids))


def test_class_a_covers_every_rule_kind() -> None:
    items = {variant.item.split(":", 1)[0] for variant in CATALOG if variant.section == "class_a"}
    kinds = {get_args(get_type_hints(rule)["kind"])[0] for rule in get_args(ArchitectureRule)}
    assert kinds <= items
    assert {"bounded_numeric_operand", "protocol_declarations"} <= items


# allowed_dependency records a permission, never a violation: the analyzer never evaluates it
# against a run (docs/rules.md), so no run, `tour` included, can ever make it fire (AD-11).
_KIND_CANNOT_VIOLATE = {"allowed_dependency"}


def _clean_sample_rule_kind_by_id() -> dict[str, str]:
    """Every rule id the clean sample declares, mapped to its kind.

    An inside rule (AD-36) is keyed the way a finding names it, `<component>:<id>`, so it lines
    up directly with `Variant.expected_violations`.
    """
    top = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    mapping = {rule["id"]: rule["kind"] for rule in top["rules"]}
    inside = json.loads((FIXTURE_DIR / "shop/store/architecture-contract.json").read_text())
    mapping.update({f"store:{rule['id']}": rule["kind"] for rule in inside["rules"]})
    return mapping


def test_clean_sample_declares_every_class_a_rule_kind() -> None:
    """AD-11: the clean sample itself declares every Class A rule kind, not only the catalogue.

    test_clean_variant_is_fully_clean proves the declared rules are all satisfied; this proves
    the declaration is complete.
    """
    kinds = {get_args(get_type_hints(rule)["kind"])[0] for rule in get_args(ArchitectureRule)}
    assert kinds <= set(_clean_sample_rule_kind_by_id().values())
    assert {"bounded_numeric_operand", "protocol_declarations"} <= set(
        _clean_sample_rule_kind_by_id().values()
    )


def test_class_a_covers_every_forbidden_construct_kind() -> None:
    covered = {
        variant.item.split(":", 1)[1]
        for variant in CATALOG
        if variant.item.startswith("forbidden_construct:")
    }
    assert {kind.value for kind in ForbiddenConstructKind} <= covered


def test_every_diagnostic_code_has_a_variant_or_evidence() -> None:
    produced = {code for variant in CATALOG for code in variant.expected_codes}
    evidenced_codes = {
        variant.item
        for variant in CATALOG
        if variant.evidence is not None and variant.item in set(get_args(DiagnosticCode))
    }
    assert set(get_args(DiagnosticCode)) <= produced | evidenced_codes


def test_every_diagnostic_kind_has_a_variant_or_evidence() -> None:
    # expected_kinds lists uncoded diagnostics only; every coded row is a contract_invalid one.
    produced = {kind for variant in CATALOG for kind in variant.expected_kinds}
    if any(variant.expected_codes for variant in CATALOG):
        produced = produced | {"contract_invalid"}
    evidenced_kinds = {
        variant.item
        for variant in CATALOG
        if variant.evidence is not None and variant.item in set(get_args(DiagnosticKind))
    }
    assert set(get_args(DiagnosticKind)) <= produced | evidenced_kinds


def test_class_a_shows_exact_sources_beside_its_prefix_twin() -> None:
    """AD-49: one nested handler, allowed under a prefix and reported under the exact name."""
    rows = {variant.item: variant for variant in CATALOG}
    prefix = rows["forbidden_construct:allowed_sources"]
    exact = rows["forbidden_construct:exact_sources"]
    assert prefix.files["shop/cli/main.py"] == exact.files["shop/cli/main.py"]
    assert prefix.expected_violations == ()
    assert exact.expected_violations == ("CONSTRUCT-NO-BROAD-EXCEPT",)


def test_class_b_covers_every_measurement_dimension() -> None:
    items = {variant.item for variant in CATALOG if variant.section == "class_b"}
    expected = {
        *(f"SCALARS:{name}" for name in SCALARS),
        "unresolved_ratio",
        *(f"GUARDRAIL_DIMENSIONS:{name}" for name in GUARDRAIL_DIMENSIONS),
        "coverage_must_pass",
    }
    assert expected <= items

    # A new scalar or dimension fails here until it has a check run.
    checked = {
        variant.item
        for variant in CATALOG
        if variant.section == "class_b" and variant.check is not None
    }
    assert expected - _CLASS_B_TESTED_ONLY <= checked
    tested_only = {
        variant.item
        for variant in CATALOG
        if variant.section == "class_b" and variant.evidence is not None
    }
    assert tested_only == _CLASS_B_TESTED_ONLY


def test_class_c_covers_every_contract_declarations_field() -> None:
    items = {variant.item for variant in CATALOG if variant.section == "class_c"}
    expected = {
        f"ContractDeclarations.{field.name}" for field in dataclass_fields(ContractDeclarations)
    }
    assert expected <= items


def test_check_expectation_names_are_valid_measurements() -> None:
    valid_scalars = {*SCALARS, "unresolved_ratio"}
    for variant in CATALOG:
        if variant.check is None:
            continue
        assert set(variant.check.regressed_scalars) <= valid_scalars
        assert set(variant.check.regressed_dimensions) <= set(GUARDRAIL_DIMENSIONS)


def test_evidence_paths_exist() -> None:
    missing = [
        variant.id
        for variant in CATALOG
        if variant.evidence is not None and not (ROOT / variant.evidence).is_file()
    ]
    assert missing == []


def _prepare_repo(
    tmp_path: Path, files: dict[str, str | None], fixture: Path = FIXTURE_DIR
) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(fixture, root)
    resolver_inputs = root / "resolver-inputs"
    has_resolver_inputs = resolver_inputs.is_dir()
    if has_resolver_inputs:
        shutil.copytree(resolver_inputs, root / "node_modules")
    apply_overlay(root, files)
    commands = [
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "demo@example.invalid"],
        ["git", "config", "user.name", "Demo"],
    ]
    if has_resolver_inputs:
        commands.append(["git", "config", "core.autocrlf", "false"])
    commands.append(["git", "add", "-A"])
    if has_resolver_inputs:
        commands.append(["git", "add", "--force", "node_modules"])
    commands.append(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "variant"],
    )
    for args in commands:
        subprocess.run(args, cwd=root, check=True, capture_output=True)
    return root


def _report_findings(
    root: Path, config: ScanConfig
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...], RuleVerdict]:
    """Violations, `unknowns` (kind, subject) pairs and the declared-rules verdict of one report.

    `run_validate` never populates `RunResult.observation` on a passing run (only its
    diagnostics reach the caller), so `expected_unknowns` has nowhere to read from there;
    `run_report`'s own decoded model already stands in for violations below, and carries the
    `unknowns` section too, so checking it costs no second scan of the sample.
    """
    report, architecture = run_report(
        root,
        config=config,
        analyzer=observer_for(
            config.language, collector_argv=config.collector_argv, tsconfig=config.tsconfig
        ),
    )
    if architecture is None:
        return (), (), report.declared_rules
    summary = report_summary(report)
    expected = badge(
        "NOT CHECKED"
        if report.exit_code == 2 and report.rule_assessments is None
        else report.declared_rules
    )
    assert summary.decision == expected
    assert (
        next(row.value for row in summary.verdicts if row.key == "declared_rules")
        == report.declared_rules
    )
    page = render_architecture_html(
        report, architecture, repository="sample", architecture_href="architecture.json"
    ).decode()
    assert f'data-decision="{expected.state}"' in page
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    violations = trace_valid_violations(observation)
    actual_violations = tuple(
        sorted(item.rule_ids[0] if item.rule_ids else item.id for item in violations)
    )
    actual_unknowns = tuple(
        sorted(
            (record.kind, subject)
            for record in observation.records("unknowns") or ()
            for subject in record.subjects
        )
    )
    return actual_violations, actual_unknowns, report.declared_rules


# Keyed by variant id, so a variant several tests need (`tour`) is run once per session, not
# once per test: `_sample_run` is the only place that materializes and analyzes a sample variant.
_SampleRun = tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[tuple[str, str], ...],
    int,
    tuple[str, ...],
    RuleVerdict,
]
_SAMPLE_RUN_CACHE: dict[str, _SampleRun] = {}


def _sample_run(tmp_path_factory: pytest.TempPathFactory, variant: Variant) -> _SampleRun:
    """Actual (codes, kinds, violations, unknowns, ...) from a real run, cached by id.

    The configuration is the variant's own sample's `archkeel.toml`, read the way the CLI reads
    it, so a sample in another language runs exactly as a user's repository would.
    """
    if variant.id not in _SAMPLE_RUN_CACHE:
        root = _prepare_repo(
            tmp_path_factory.mktemp(variant.id), dict(variant.files), variant.fixture
        )
        baseline = root / variant.baseline if variant.baseline is not None else None
        config = load_config(root, variant.config)
        validate_result, _ = run_validate(
            root,
            config,
            observer_for(
                config.language, collector_argv=config.collector_argv, tsconfig=config.tsconfig
            ),
            baseline=baseline,
            write_baseline=variant.write_baseline,
        )
        actual_codes = tuple(sorted(item.code for item in validate_result.diagnostics if item.code))
        actual_kinds = tuple(
            sorted(item.kind for item in validate_result.diagnostics if item.code is None)
        )
        actual_violations, actual_unknowns, declared_rules = _report_findings(root, config)
        if validate_result.observation_complete == "PASS":
            assert validate_result.declared_rules == declared_rules
        _SAMPLE_RUN_CACHE[variant.id] = (
            actual_codes,
            actual_kinds,
            actual_violations,
            actual_unknowns,
            validate_result.exit_code,
            validate_result.failures,
            declared_rules,
        )
    return _SAMPLE_RUN_CACHE[variant.id]


@pytest.mark.parametrize("variant", _SAMPLE_VARIANTS, ids=lambda v: v.id)
def test_variant_produces_the_catalogued_findings(
    tmp_path_factory: pytest.TempPathFactory, variant: Variant
) -> None:
    actual_codes, actual_kinds, actual_violations, actual_unknowns, _, _, declared_rules = (
        _sample_run(tmp_path_factory, variant)
    )
    assert actual_codes == variant.expected_codes
    assert actual_kinds == variant.expected_kinds
    assert actual_violations == variant.expected_violations
    # Subset, not equality: dynamic_call_limit/context_alias_limit/boundary_type_limit fire on
    # every sample scan regardless of this variant's own overlay (see Variant.expected_unknowns).
    assert set(variant.expected_unknowns) <= set(actual_unknowns)
    assert not set(variant.absent_unknowns) & set(actual_unknowns)
    if variant.expected_declared_rules is not None:
        assert declared_rules == variant.expected_declared_rules


_ROLLUP_ONLY = "Package cycle with 2 members, roll-up only: no module cycle crosses them"
_CYCLE_ROWS = {
    "class-a-no-component-cycles-module-hidden": [
        ("module_scc", ("shop.model.alpha", "shop.model.beta"), "Module cycle with 2 members")
    ],
    "class-a-package-cycle-rollup-only": [
        ("package_scc", ("shop.model", "shop.render"), _ROLLUP_ONLY)
    ],
    "class-a-package-cycle-backed": [
        ("module_scc", ("shop.model.entities", "shop.render.text"), "Module cycle with 2 members"),
        ("package_scc", ("shop.model", "shop.render"), "Package cycle with 2 members"),
    ],
}


@pytest.mark.parametrize(
    "variant", [item for item in CATALOG if item.typescript_trace is not None], ids=lambda v: v.id
)
def test_typescript_trace_variant_keeps_ids_and_displays_source_labels(
    tmp_path: Path, variant: Variant, capsys: pytest.CaptureFixture
) -> None:
    trace = variant.typescript_trace
    assert trace is not None
    root = _prepare_repo(tmp_path, dict(variant.files), variant.fixture)
    config = load_config(root, variant.config)
    report, architecture = run_report(
        root,
        config=config,
        analyzer=observer_for(
            config.language,
            collector_argv=config.collector_argv,
            tsconfig=config.tsconfig,
            bundler=config.bundler,
        ),
    )
    if trace.observation_complete is not None:
        assert report.observation_complete.value == trace.observation_complete
    assert architecture is not None
    snapshot = tmp_path / "architecture.json"
    snapshot.write_bytes(architecture)
    assert (
        main(
            [
                "story",
                "trace",
                "--from",
                trace.source,
                "--to",
                trace.target,
                "--snapshot",
                str(snapshot),
                "--json",
            ]
        )
        == 0
    )
    (path,) = json.loads(capsys.readouterr().out)["paths"]
    nodes = (path["start"], *(hop["node"] for hop in path["hops"]))
    assert tuple(node["name"] for node in nodes) == trace.names
    assert tuple(node["label"] for node in nodes) == trace.labels
    assert tuple(hop["status"] for hop in path["hops"]) == trace.hops


def _violation_files(root: Path, config: ScanConfig) -> set[tuple[str, str]]:
    """(rule id, source file) for every traced violation of one report run."""
    _, architecture = run_report(root, config=config, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    files = {item.id: item.file for item in observation.evidence}
    return {
        (item.rule_ids[0], files[evidence_id])
        for item in trace_valid_violations(observation)
        for evidence_id in item.evidence_ids
    }


def test_architecture_demo_markdown_matches_generated_output() -> None:
    doc = ROOT / "docs/architecture-demo.md"
    assert doc.read_text() == markdown()
