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

from archkeel.analyzer import observe
from archkeel.check.expectation import GUARDRAIL_DIMENSIONS
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.check.validation import run_validate
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.measurements import SCALARS, compare_measurements
from archkeel.ir.model import (
    ArchitectureRule,
    ContractDeclarations,
    DiagnosticCode,
    DiagnosticKind,
    ForbiddenConstructKind,
)
from archkeel.ir.trace import trace_valid_violations
from fixtures.architecture_demo import CATALOG, markdown
from fixtures.demo_catalog_check import build_and_run_check
from fixtures.demo_catalog_support import FIXTURE_DIR, Variant, apply_overlay
from fixtures.demo_catalog_widening import build_and_run_against

ROOT = Path(__file__).parents[1]
CONFIG = ScanConfig(("shop",), "shop", "architecture-contract.json", "0" * 64)
_SAMPLE_VARIANTS = [
    variant
    for variant in CATALOG
    if variant.evidence is None and variant.check is None and variant.against is None
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


def test_tour_fires_every_class_a_rule_kind_that_can_violate(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """AD-11: `tour` is the showcase promise, not only the wider catalogue.

    A rule kind present somewhere in the catalogue but missing from `tour`'s own real run is
    exactly the gap that let symbol_placement and boundary_types (AD-58) land without joining
    the showcase (issue #47), and that let `touch_store` drop out of `tour` silently when
    `boundary_types` narrowed to a component's declared facade (issue #55): this asserts against
    the violations a run of `tour` actually produces, sharing that run with
    `test_variant_produces_the_catalogued_findings[tour]` via `_sample_run` rather than scanning
    the sample a second time.
    """
    kinds = {get_args(get_type_hints(rule)["kind"])[0] for rule in get_args(ArchitectureRule)}
    tour = next(variant for variant in CATALOG if variant.id == "tour")
    rule_kind = _clean_sample_rule_kind_by_id()
    _, _, actual_violations, _, _, _ = _sample_run(tmp_path_factory, tour)
    fired_kinds = {rule_kind[rule_id] for rule_id in actual_violations}
    assert kinds - _KIND_CANNOT_VIOLATE <= fired_kinds


def test_clean_sample_declares_every_class_a_rule_kind() -> None:
    """AD-11: the clean sample itself declares every Class A rule kind, not only the catalogue.

    test_clean_variant_is_fully_clean proves the declared rules are all satisfied; this proves
    the declaration is complete.
    """
    kinds = {get_args(get_type_hints(rule)["kind"])[0] for rule in get_args(ArchitectureRule)}
    assert kinds <= set(_clean_sample_rule_kind_by_id().values())


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


def _prepare_repo(tmp_path: Path, files: dict[str, str | None]) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(FIXTURE_DIR, root)
    apply_overlay(root, files)
    for args in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "demo@example.invalid"],
        ["git", "config", "user.name", "Demo"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "variant"],
    ):
        subprocess.run(args, cwd=root, check=True, capture_output=True)
    return root


def _report_findings(root: Path) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Violations and `unknowns` (kind, subject) pairs, both off one decoded report model.

    `run_validate` never populates `RunResult.observation` on a passing run (only its
    diagnostics reach the caller), so `expected_unknowns` has nowhere to read from there;
    `run_report`'s own decoded model already stands in for violations below, and carries the
    `unknowns` section too, so checking it costs no second scan of the sample.
    """
    _, architecture = run_report(root, config=CONFIG, analyzer=observe)
    if architecture is None:
        return (), ()
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
    return actual_violations, actual_unknowns


# Keyed by variant id, so a variant several tests need (`tour`) is run once per session, not
# once per test: `_sample_run` is the only place that materializes and analyzes a sample variant.
_SampleRun = tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[tuple[str, str], ...],
    int,
    tuple[str, ...],
]
_SAMPLE_RUN_CACHE: dict[str, _SampleRun] = {}


def _sample_run(tmp_path_factory: pytest.TempPathFactory, variant: Variant) -> _SampleRun:
    """Actual (codes, kinds, violations, unknowns) from a real run, cached by id."""
    if variant.id not in _SAMPLE_RUN_CACHE:
        root = _prepare_repo(tmp_path_factory.mktemp(variant.id), dict(variant.files))
        baseline = root / variant.baseline if variant.baseline is not None else None
        validate_result, _ = run_validate(root, CONFIG, observe, baseline=baseline)
        actual_codes = tuple(sorted(item.code for item in validate_result.diagnostics if item.code))
        actual_kinds = tuple(
            sorted(item.kind for item in validate_result.diagnostics if item.code is None)
        )
        actual_violations, actual_unknowns = _report_findings(root)
        _SAMPLE_RUN_CACHE[variant.id] = (
            actual_codes,
            actual_kinds,
            actual_violations,
            actual_unknowns,
            validate_result.exit_code,
            validate_result.failures,
        )
    return _SAMPLE_RUN_CACHE[variant.id]


@pytest.mark.parametrize("variant", _SAMPLE_VARIANTS, ids=lambda v: v.id)
def test_variant_produces_the_catalogued_findings(
    tmp_path_factory: pytest.TempPathFactory, variant: Variant
) -> None:
    actual_codes, actual_kinds, actual_violations, actual_unknowns, _, _ = _sample_run(
        tmp_path_factory, variant
    )
    assert actual_codes == variant.expected_codes
    assert actual_kinds == variant.expected_kinds
    assert actual_violations == variant.expected_violations
    # Subset, not equality: dynamic_call_limit/context_alias_limit/boundary_type_limit fire on
    # every sample scan regardless of this variant's own overlay (see Variant.expected_unknowns).
    assert set(variant.expected_unknowns) <= set(actual_unknowns)


def test_baseline_interface_narrowing_runs_a_real_validate_gate(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    variant = next(item for item in CATALOG if item.id == "validation-baseline-interface-narrowing")
    _, _, _, _, exit_code, failures = _sample_run(tmp_path_factory, variant)

    assert exit_code == 1
    assert failures == (
        "resolved violation: RESOLVED-IMPORT | shop.app.orders.summarize shop.cli.main "
        "(0 observed, 1 in the baseline); rewrite the baseline with --write-baseline",
        "resolved public entry: shop.app.orders:summarize is no longer reached; remove it from "
        "app.public",
    )


def test_measurement_budget_demo_passes_clean_and_fails_on_a_rise(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    variants = {item.id: item for item in CATALOG}
    clean = _sample_run(tmp_path_factory, variants["validation-measurement-budget-clean"])
    risen = _sample_run(tmp_path_factory, variants["validation-measurement-budget-rise"])

    assert (clean[4], clean[5]) == (0, ())
    assert (risen[4], risen[5]) == (
        1,
        ("measurement budget exceeded in cycle_edges: 0->2",),
    )


@pytest.mark.parametrize("variant", _UNIQUE_CHECK_RUNS, ids=lambda v: v.id)
def test_check_variant_produces_the_catalogued_verdicts(tmp_path: Path, variant: Variant) -> None:
    check = variant.check
    assert check is not None
    result = build_and_run_check(tmp_path, variant.files, check.scenario)

    assert result.exit_code == check.exit_code
    assert result.expectation_fulfilled == check.expectation_fulfilled
    assert result.git_predicate == check.git_predicate
    assert result.host_order == check.host_order

    if not check.regressed_scalars and not check.regressed_dimensions:
        # AD-84 inspects one direct field level. The clean shop facade contains
        # collection-valued model fields, whose deeper model positions stay UNKNOWN.
        assert result.declared_rules == "UNKNOWN"
        return
    delta = result.delta
    assert delta is not None
    ratchets = delta.ratchets
    assert ratchets.status == "SUPPORTED"
    assert ratchets.baseline is not None
    assert ratchets.head is not None
    actual_scalars = {
        name
        for name, _, _, verdict in compare_measurements(ratchets.baseline, ratchets.head)
        if verdict == "FAIL"
    }
    assert actual_scalars == set(check.regressed_scalars)
    # Only the guardrail-comparable dimensions matter here; a new module also adds an
    # incidental api_crossings/dependency_edges entry for its own __future__ import, which is
    # not a guardrail dimension and not part of what any row demonstrates.
    dimensions = {dimension.name: dimension for dimension in delta.dimensions}
    actual_dimensions = {
        name
        for name in GUARDRAIL_DIMENSIONS
        if dimensions[name].after_count > dimensions[name].before_count
    }
    assert actual_dimensions == set(check.regressed_dimensions)


@pytest.mark.parametrize("variant", _AGAINST_VARIANTS, ids=lambda v: v.id)
def test_against_variant_produces_the_catalogued_verdict(tmp_path: Path, variant: Variant) -> None:
    against = variant.against
    assert against is not None
    result = build_and_run_against(tmp_path, variant.files, against)

    assert result.exit_code == against.exit_code
    assert result.diagnostics == ()
    assert result.failures == against.failures


def test_graph_drift_names_the_command_or_the_line_it_refuses(tmp_path: Path) -> None:
    """AD-46: a stale page names --write-graph, which then passes; a subgraph is left to a human.

    The rename touches both markers (AD-57), since the shop sample's target graph agrees with
    its observed one today; --write-graph regenerates both in the one page.
    """
    rows = {variant.item: variant for variant in CATALOG}
    stale = _prepare_repo(tmp_path / "stale", dict(rows["graph.drift:write-graph"].files))
    drifted = run_validate(stale, CONFIG, observe)[0].diagnostics
    assert {item.code for item in drifted} == {"graph.drift"}
    assert {"archkeel validate --write-graph" in item.remedy for item in drifted} == {True}
    fixed, files = run_validate(stale, CONFIG, observe, write_graph=True)
    assert (fixed.exit_code, set(files)) == (0, {"docs/architecture/shop.md"})

    refused = _prepare_repo(tmp_path / "refused", dict(rows["graph.drift:subgraph"].files))
    result, files = run_validate(refused, CONFIG, observe, write_graph=True)
    assert files == {}
    assert {item.code for item in result.diagnostics} == {"graph.drift"}
    for item in result.diagnostics:
        assert "`subgraph composition`" in item.remedy
        assert "by hand" in item.remedy


def test_target_graph_drift_leaves_the_observed_graph_untouched(tmp_path: Path) -> None:
    """AD-57: a target-only edit drifts only the target marker; the observed one keeps passing."""
    rows = {variant.item: variant for variant in CATALOG}
    stale = _prepare_repo(
        tmp_path / "target-stale", dict(rows["graph.drift:target-write-graph"].files)
    )
    (drift,) = run_validate(stale, CONFIG, observe)[0].diagnostics
    assert drift.subject == "docs/architecture/shop.md (target graph)"
    assert "archkeel validate --write-graph" in drift.remedy
    fixed, files = run_validate(stale, CONFIG, observe, write_graph=True)
    assert (fixed.exit_code, set(files)) == (0, {"docs/architecture/shop.md"})

    refused = _prepare_repo(
        tmp_path / "target-refused", dict(rows["graph.drift:target-subgraph"].files)
    )
    result, files = run_validate(refused, CONFIG, observe, write_graph=True)
    (drift,) = result.diagnostics
    assert files == {}
    assert drift.subject == "docs/architecture/shop.md (target graph)"
    assert "`subgraph composition`" in drift.remedy
    assert "by hand" in drift.remedy


def test_clean_variant_is_fully_clean(tmp_path: Path) -> None:
    clean = next(variant for variant in CATALOG if variant.id == "clean")
    root = _prepare_repo(tmp_path, dict(clean.files))

    validate_result, _ = run_validate(root, CONFIG, observe)
    assert validate_result.exit_code == 0
    assert validate_result.diagnostics == ()
    # AD-46: the clean page is what --write-graph writes, so the command leaves it alone.
    assert run_validate(root, CONFIG, observe, write_graph=True)[1] == {}

    report_result, _ = run_report(root, config=CONFIG, analyzer=observe)
    # AD-84 keeps collection-contained model fields bounded at one level.
    assert report_result.declared_rules == "UNKNOWN"


def test_architecture_demo_markdown_matches_generated_output() -> None:
    doc = ROOT / "docs/architecture-demo.md"
    assert doc.read_text() == markdown()
