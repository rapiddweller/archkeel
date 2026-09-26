# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issues #159/#160: report status, colors, declared rules, and violation filters."""

import json
import re
from html import escape
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
from archkeel.ir.codec import canonical_report_bytes, decode_canonical_model, parse_observation
from archkeel.ir.model import ReportFilter
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


def test_same_fingerprint_growth_is_one_counted_finding_not_an_exact_line_claim() -> None:
    fingerprint = ViolationFingerprint((GETATTR_RULE,), ("shop.model.probe.read",))
    known = (KnownViolation(fingerprint, 2),)
    observed = (KnownViolation(fingerprint, 3),)

    assert compare_violations(known, observed, cycle_rules=frozenset()) == (
        f"new violation: {GETATTR_RULE} | shop.model.probe.read (3 observed, 2 in the baseline)",
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


def test_report_lists_every_declared_rule_with_truthful_status_and_provenance(
    tmp_path: Path,
) -> None:
    result, observation, page = _report(tmp_path)
    violations_by_rule = dict(result.violations_by_rule)
    rules = [
        item
        for item in observation.records("declarations") or ()
        if item.evidence_class.value == "DECLARED_RULE"
    ]

    assert "Declared rules" in page
    for rule in rules:
        row = re.search(rf'<[^>]+\bdata-rule-id="{re.escape(escape(rule.id))}"[^>]*>', page)
        assert row is not None, rule.id
        assert escape(rule.kind) in page
        data = dict(rule.data.entries)
        for field in ("decided_by", "rationale"):
            assert escape(str(data[field])) in page
        assert all(escape(item) in page for item in rule.provenance)
        if violations_by_rule.get(rule.id, 0):
            assert 'data-rule-status="fail"' in row[0], rule.id
        else:
            assert any(
                f'data-rule-status="{status}"' in row[0] for status in ("pass", "unknown")
            ), rule.id

    # A grant says an edge is allowed; it is not evidence that the analyzer exercised the rule.
    permission = re.search(r'<[^>]+\bdata-rule-id="DEP-APP-ALLOWS-MODEL"[^>]*>', page)
    assert permission is not None
    assert 'data-rule-status="unknown"' in permission[0]


def test_violation_color_has_fail_text_and_icon_and_not_conformance_teal(tmp_path: Path) -> None:
    _, observation, page = _report(tmp_path)
    violation = next(
        item
        for item in observation.records("violations") or ()
        if item.kind == "forbidden_construct"
    )

    row = re.search(rf'<[^>]+\bdata-violation-id="{re.escape(escape(violation.id))}"[^>]*>', page)
    assert row is not None
    assert 'data-status="fail"' in row[0]
    assert "FAIL" in page
    assert 'aria-label="Violation"' in page
    assert '.violation-row[data-status="fail"]' in page
    assert re.search(
        r'\.violation-row\[data-status="fail"\]\s*\{[^}]*color:\s*var\(--ck-fail\)', page
    )


def test_report_is_deterministic_and_keeps_unknown_context_when_focusing_violations(
    tmp_path: Path,
) -> None:
    result, observation, page = _report(tmp_path, only_violations=True)
    repeated = render_architecture_html(
        result,
        canonical_report_bytes(observation),
        repository="shop",
        architecture_href="architecture.json",
    ).decode()

    assert page == repeated
    assert "Known unknowns" in page
    assert "declared_rules" in page
    assert "failures" in page
    assert "Complete ArchitectureIR inventory" in page
