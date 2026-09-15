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
from archkeel.ir.measurements import SCALARS
from archkeel.ir.model import (
    ArchitectureRule,
    ContractDeclarations,
    DiagnosticCode,
    DiagnosticKind,
    ForbiddenConstructKind,
)
from archkeel.ir.trace import trace_valid_violations
from fixtures.architecture_demo import CATALOG, markdown
from fixtures.demo_catalog_support import FIXTURE_DIR, Variant, apply_overlay

ROOT = Path(__file__).parents[1]
CONFIG = ScanConfig(("shop",), "shop", "architecture-contract.json", "0" * 64)
_SAMPLE_VARIANTS = [variant for variant in CATALOG if variant.evidence is None]


def test_variant_ids_are_unique() -> None:
    ids = [variant.id for variant in CATALOG]
    assert len(ids) == len(set(ids))


def test_class_a_covers_every_rule_kind() -> None:
    items = {variant.item.split(":", 1)[0] for variant in CATALOG if variant.section == "class_a"}
    kinds = {get_args(get_type_hints(rule)["kind"])[0] for rule in get_args(ArchitectureRule)}
    assert kinds <= items


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


def test_class_b_covers_every_measurement_dimension() -> None:
    items = {variant.item for variant in CATALOG if variant.section == "class_b"}
    expected = {
        *(f"SCALARS:{name}" for name in SCALARS),
        "unresolved_ratio",
        *(f"GUARDRAIL_DIMENSIONS:{name}" for name in GUARDRAIL_DIMENSIONS),
        "coverage_must_pass",
    }
    assert expected <= items


def test_class_c_covers_every_contract_declarations_field() -> None:
    items = {variant.item for variant in CATALOG if variant.section == "class_c"}
    expected = {
        f"ContractDeclarations.{field.name}" for field in dataclass_fields(ContractDeclarations)
    }
    assert expected <= items


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


def _report_violations(root: Path) -> tuple[str, ...]:
    _, architecture = run_report(root, config=CONFIG, analyzer=observe)
    if architecture is None:
        return ()
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    violations = trace_valid_violations(observation)
    return tuple(sorted(item.rule_ids[0] if item.rule_ids else item.id for item in violations))


@pytest.mark.parametrize("variant", _SAMPLE_VARIANTS, ids=lambda v: v.id)
def test_variant_produces_the_catalogued_findings(tmp_path: Path, variant: Variant) -> None:
    root = _prepare_repo(tmp_path, dict(variant.files))

    validate_result = run_validate(root, CONFIG, observe)
    actual_codes = tuple(sorted(item.code for item in validate_result.diagnostics if item.code))
    assert actual_codes == variant.expected_codes
    actual_kinds = tuple(
        sorted(item.kind for item in validate_result.diagnostics if item.code is None)
    )
    assert actual_kinds == variant.expected_kinds

    assert _report_violations(root) == variant.expected_violations


def test_clean_variant_is_fully_clean(tmp_path: Path) -> None:
    clean = next(variant for variant in CATALOG if variant.id == "clean")
    root = _prepare_repo(tmp_path, dict(clean.files))

    validate_result = run_validate(root, CONFIG, observe)
    assert validate_result.exit_code == 0
    assert validate_result.diagnostics == ()

    report_result, _ = run_report(root, config=CONFIG, analyzer=observe)
    assert report_result.declared_rules == "PASS"


def test_architecture_demo_markdown_matches_generated_output() -> None:
    doc = ROOT / "docs/architecture-demo.md"
    assert doc.read_text() == markdown()
