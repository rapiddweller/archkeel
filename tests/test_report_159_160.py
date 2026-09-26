# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #159/#160 report acceptance.

Rule status needs evaluation evidence: a violation beats undecided evidence, while a clean
fully evaluated rule can pass. `allowed_dependency` is a permission declaration, not a check
and not an UNKNOWN measurement. Browser acceptance must verify computed fail color and a
non-color status cue, plus the evidence attached to the correct rule row; HTML/CSS source
matching is not visual or accessibility proof.
"""

import json
from pathlib import Path

from test_baseline import GETATTR_RULE, PROBE, _repo
from test_report_filter import CONFIG, _tour_root

from archkeel.analyzer import observe
from archkeel.check.report import run_report
from archkeel.check.validation import run_validate
from archkeel.ir.baseline import (
    KnownViolation,
    ViolationFingerprint,
    compare_violations,
    select_violations,
)
from archkeel.ir.codec import (
    baseline_bytes,
    canonical_report_bytes,
    decode_canonical_model,
    parse_observation,
)
from archkeel.ir.model import EvidenceClass, ReportFilter
from archkeel.render.html import render_architecture_html


def _report(tmp_path: Path, *, only_violations: bool = False):
    root = _tour_root(tmp_path)
    result, architecture = run_report(
        root, config=CONFIG, analyzer=observe, only_violations=only_violations
    )
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    page = render_architecture_html(
        result, architecture, repository="shop", architecture_href="architecture.json"
    ).decode()
    return result, observation, page


def _renderer_only_mixed_report(tmp_path: Path, *, only_violations: bool = False):
    """Render injected UNKNOWN evidence beside a real scan; this is not an E2E proof.

    The UNKNOWN summary is synthetic and added after measurement. This only probes renderer
    output; it does not prove that a rule row associates status with the correct evidence.
    A browser/structured-state acceptance must establish that association.
    """
    root = _tour_root(tmp_path)
    result, architecture = run_report(
        root, config=CONFIG, analyzer=observe, only_violations=only_violations
    )
    assert architecture is not None
    raw = decode_canonical_model(json.loads(architecture))
    observed_violations = len(raw["violations"])
    raw["unknowns"].append(
        {
            "id": "UNKNOWN-APP-TYPES-PARTIAL",
            "evidence_class": "UNKNOWN",
            "area": "type_architecture",
            "kind": "boundary_type_limit",
            "title": "One facade type position is undecided",
            "subjects": ["shop.app.orders.place_order"],
            "evidence_ids": [],
            "rule_ids": ["APP-TYPES-NOT-DICT"],
            "fact_ids": [],
            "provenance": ["docs/architecture/shop.md"],
            "data": {
                "positions": 2,
                "decided": 1,
                "undecided": 1,
                "missing_annotation": 0,
                "forward_reference": 0,
                "dotted_name": 0,
                "generic": 0,
                "union": 0,
                "unresolved_name": 0,
                "external_type": 0,
                "other": 1,
            },
        }
    )
    observation = parse_observation(raw)
    page = render_architecture_html(
        result,
        canonical_report_bytes(observation),
        repository="shop",
        architecture_href="architecture.json",
    ).decode()
    return result, observation, page, observed_violations


def test_same_fingerprint_growth_is_one_counted_finding_not_an_exact_line_claim() -> None:
    fingerprint = ViolationFingerprint((GETATTR_RULE,), ("shop.model.probe.read",))
    known = (KnownViolation(fingerprint, 1),)
    observed = (KnownViolation(fingerprint, 2),)

    assert compare_violations(known, observed, cycle_rules=frozenset()) == (
        f"new violation: {GETATTR_RULE} | shop.model.probe.read (2 observed, 1 in the baseline)",
    )


def test_one_fingerprint_shrink_reports_one_resolved_finding() -> None:
    fingerprint = ViolationFingerprint((GETATTR_RULE,), ("shop.model.probe.read",))

    assert compare_violations(
        (KnownViolation(fingerprint, 2),),
        (KnownViolation(fingerprint, 1),),
        cycle_rules=frozenset(),
    ) == (
        f"resolved violation: {GETATTR_RULE} | shop.model.probe.read "
        "(1 observed, 2 in the baseline); rewrite the baseline with --write-baseline",
    )


def test_incomplete_observation_does_not_claim_baseline_findings_resolved(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path, "incomplete", {"shop/model/probe.py": PROBE})
    baseline = root / "known-violations.json"
    fingerprint = ViolationFingerprint((GETATTR_RULE,), ("shop.model.gone.read",))
    baseline.write_bytes(baseline_bytes((KnownViolation(fingerprint, 1),)))
    (root / "shop/model/broken.py").write_text("def broken(:\n")

    result, _ = run_validate(root, CONFIG, observe, baseline=baseline)

    assert result.exit_code == 2
    assert result.observation_complete == "UNKNOWN"
    assert result.baseline_resolved is None
    assert not any("resolved violation" in failure for failure in result.failures)


def test_no_baseline_does_not_label_observed_findings_new(tmp_path: Path) -> None:
    root = _repo(tmp_path, "without-baseline", {"shop/model/probe.py": PROBE})

    result, _ = run_validate(root, CONFIG, observe)

    assert result.baseline_new is None
    assert result.baseline_resolved is None
    assert not any("new violation" in failure for failure in result.failures)


def test_rule_filter_keeps_construct_and_cycle_violations_without_import_pairs(
    tmp_path: Path,
) -> None:
    _, observation, _ = _report(tmp_path)

    for rule_id, kind in (
        ("CONSTRUCT-NO-DYNAMIC", "forbidden_construct"),
        ("COMPONENT-NO-CYCLES", "no_component_cycles"),
    ):
        selected = select_violations(observation, ReportFilter(False, rule_id, None))
        assert selected
        assert all(item.kind == kind and item.rule_ids == (rule_id,) for item in selected)


def test_report_lists_every_declared_rule_and_its_provenance(tmp_path: Path) -> None:
    _, observation, page = _report(tmp_path)
    rules = [
        item
        for item in observation.records("declarations") or ()
        if item.evidence_class.value == "DECLARED_RULE"
    ]

    assert "Declared rules" in page
    for rule in rules:
        assert rule.id in page
        assert rule.kind in page
        data = dict(rule.data.entries)
        for field in ("decided_by", "rationale"):
            assert str(data[field]) in page
        assert all(item in page for item in rule.provenance)

    permission = next(rule for rule in rules if rule.id == "DEP-APP-ALLOWS-MODEL")
    assert permission.kind == "allowed_dependency"
    assert permission.evidence_class is EvidenceClass.DECLARED_RULE
    assert not any(
        permission.id in record.rule_ids
        for section in ("unknowns", "violations")
        for record in observation.records(section) or ()
    )


def test_fail_and_unknown_evidence_coexist_without_downgrading_the_verdict(
    tmp_path: Path,
) -> None:
    result, observation, page, observed_violations = _renderer_only_mixed_report(tmp_path)
    violation = next(
        item
        for item in observation.records("violations") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
    )
    (unknown,) = [
        item for item in observation.records("unknowns") or () if item.kind == "boundary_type_limit"
    ]
    assert violation.rule_ids == unknown.rule_ids == ("APP-TYPES-NOT-DICT",)
    assert violation.id != unknown.id
    assert result.declared_rules == "FAIL"
    assert result.measurements is not None
    assert result.measurements.scalars.violations == observed_violations
    assert "APP-TYPES-NOT-DICT" in page
    assert "FAIL" in page and "UNKNOWN" in page
    assert unknown.title in page


def test_report_is_deterministic_and_keeps_unknown_context_when_focusing_violations(
    tmp_path: Path,
) -> None:
    result, observation, page, _ = _renderer_only_mixed_report(tmp_path, only_violations=True)
    repeated = render_architecture_html(
        result,
        canonical_report_bytes(observation),
        repository="shop",
        architecture_href="architecture.json",
    ).decode()

    assert page == repeated
    assert "Complete ArchitectureIR inventory" in page
    assert "Known unknowns" not in page
    assert any(
        record.kind == "boundary_type_limit" and record.rule_ids == ("APP-TYPES-NOT-DICT",)
        for record in observation.records("unknowns") or ()
    )
    assert result.declared_rules == "FAIL"
