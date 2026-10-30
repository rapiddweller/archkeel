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

import pytest
from test_baseline import GETATTR_RULE, PROBE, _repo
from test_html_report import _start_tags
from test_report_filter import CONFIG, _tour_root

from archkeel.check.report import run_report
from archkeel.check.validation import run_validate
from archkeel.cli.observe import observe
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
from archkeel.ir.model import RULE_KINDS, EvidenceClass, ReportFilter
from archkeel.render.html import render_architecture_details, render_architecture_html


def _flow_data(page: str):
    start = page.index(">", page.index('id="flow-data"')) + 1
    return json.loads(page[start : page.index("</script>", start)])


def _linked_audit(page: str, directory: Path):
    atlas = _flow_data(page)["atlas"]
    href = atlas["architecture_href"]
    assert Path(href).name == href
    assert href in {link.get("href") for link in _start_tags(page, "a")}
    model = parse_observation(decode_canonical_model(json.loads((directory / href).read_bytes())))
    assert model.source.source_digest == atlas["source"]["source_digest"]
    assert model.source.git_head == atlas["source"]["git_head"]
    return model


def _report(
    tmp_path: Path,
    *,
    only_violations: bool = False,
    mixed_evidence: bool = False,
    opaque_provider: bool = False,
):
    root = _tour_root(tmp_path)
    if opaque_provider:
        provider = root / "shop/model/entities.py"
        provider.write_text(
            provider.read_text() + "\ndef opaque_probe():\n    return eval('Order')\n"
        )
    if mixed_evidence:
        (root / "shop/app/mixed.py").write_text(
            "def mixed(payload: dict, stamp: 'Missing') -> str:\n    return ''\n"
        )
        contract_path = root / CONFIG.contract
        contract = json.loads(contract_path.read_bytes())
        app = next(item for item in contract["components"] if item["id"] == "COMP-APP")
        app["public"].append("shop.app.mixed:mixed")
        contract_path.write_text(json.dumps(contract))
    result, architecture = run_report(
        root, config=CONFIG, analyzer=observe, only_violations=only_violations
    )
    assert architecture is not None
    (tmp_path / "architecture.json").write_bytes(architecture)
    for name, content in render_architecture_details(
        result, architecture, repository="shop", architecture_href="architecture.json"
    ).items():
        (tmp_path / name).write_bytes(content)
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    page = render_architecture_html(
        result, architecture, repository="shop", architecture_href="architecture.json"
    ).decode()
    return result, observation, page


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
    audit = _linked_audit(page, tmp_path)
    rules = [
        item
        for item in observation.records("declarations") or ()
        if item.evidence_class.value == "DECLARED_RULE" and item.kind in RULE_KINDS
    ]

    assert 'aria-label="Decision: FAIL"' in page
    for rule in rules:
        assert next(item for item in audit.records("declarations") if item.id == rule.id) == rule

    permission = next(rule for rule in rules if rule.id == "DEP-APP-ALLOWS-MODEL")
    assert permission.kind == "allowed_dependency"
    assert permission.evidence_class is EvidenceClass.DECLARED_RULE
    assert not any(
        permission.id in record.rule_ids
        for section in ("unknowns", "violations")
        for record in observation.records(section) or ()
    )


@pytest.mark.parametrize("opaque_provider", [False, True])
def test_fail_and_unknown_evidence_coexist_without_downgrading_the_verdict(
    tmp_path: Path, opaque_provider: bool
) -> None:
    result, observation, page = _report(
        tmp_path, mixed_evidence=True, opaque_provider=opaque_provider
    )
    violations = [
        item
        for item in observation.records("violations") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
    ]
    assert len(violations) == 2
    assert {
        tuple(item.data.get(key) for key in ("qualified_name", "position", "annotation"))
        for item in violations
    } == {
        ("shop.app.orders.place_order", "store_dir", "object"),
        ("shop.app.mixed.mixed", "payload", "dict"),
    }
    violation = next(
        item for item in violations if item.data.get("qualified_name") == "shop.app.mixed.mixed"
    )
    (unknown,) = [
        item for item in observation.records("unknowns") or () if item.kind == "boundary_type_limit"
    ]
    assert violation.rule_ids == unknown.rule_ids == ("APP-TYPES-NOT-DICT",)
    assert violation.id != unknown.id
    assert unknown.data.get("ambiguous_facade") == 0
    assert unknown.data.get("ambiguous_binding") == int(opaque_provider)
    assert unknown.data.get("forward_reference") == 1
    assert tuple(unknown.data.get(key) for key in ("positions", "decided", "undecided")) == (
        9,
        8 - int(opaque_provider),
        1 + int(opaque_provider),
    )
    positions = [
        item
        for item in observation.records("unknowns") or ()
        if item.kind == "boundary_type_position" and item.rule_ids == unknown.rule_ids
    ]
    expected_positions = {
        ("shop.app.mixed", "shop.app.mixed.mixed", "stamp", 0, "'Missing'", "forward_reference")
    }
    if opaque_provider:
        expected_positions.add(
            (
                "shop.app.orders",
                "shop.app.orders.place_order",
                "return",
                0,
                "Order",
                "ambiguous_binding",
            )
        )
    assert len(positions) == len(expected_positions)
    keys = ("module", "qualified_name", "position", "occurrence", "annotation", "reason")
    assert {tuple(item.data.get(key) for key in keys) for item in positions} == expected_positions
    assessment = next(row for row in result.rule_assessments if row.id == "APP-TYPES-NOT-DICT")
    assert (
        assessment.status,
        assessment.evaluation_proven,
        assessment.count,
        assessment.undecided,
    ) == ("FAIL", True, 2, 1 + int(opaque_provider))
    assert result.declared_rules == "FAIL"
    assert result.measurements is not None
    assert result.measurements.scalars.violations == len(observation.records("violations") or ())
    audit = _linked_audit(page, tmp_path)
    assert all(item in audit.records("violations") for item in violations)
    assert unknown in audit.records("unknowns")
    assert 'aria-label="Decision: FAIL"' in page


def test_report_is_deterministic_and_keeps_unknown_context_when_focusing_violations(
    tmp_path: Path,
) -> None:
    result, observation, page = _report(tmp_path, only_violations=True, mixed_evidence=True)
    repeated = render_architecture_html(
        result,
        canonical_report_bytes(observation),
        repository="shop",
        architecture_href="architecture.json",
    ).decode()

    assert page == repeated
    assert "Complete scan inventory" in page
    assert "Known unknowns" not in page
    assert any(
        record.kind == "boundary_type_limit" and record.rule_ids == ("APP-TYPES-NOT-DICT",)
        for record in observation.records("unknowns") or ()
    )
    assert result.declared_rules == "FAIL"
