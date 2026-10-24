# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The full Compass proof replays source-only variants through the native report path."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from archkeel.ir.graph_codec import parse_report
from fixtures.architecture_demo import REPORT_CASES, replay
from fixtures.demo_catalog_compass import COMPASS_FIXTURE_DIR, VARIANTS

SOURCE_DIGEST = "c6c1b8fe62fbc950af3b3dc4a033cac300bdeec2564e563909504a69df753e72"
TARGET_DIGEST = "4f6fb239818ff66ae963ce5a4ffe43d319b6d21cbeaf76d262d9cbf670a33a67"
EXPECTED_ASSESSMENTS = {
    "compass-project": Counter(PASS=1749, UNKNOWN=23),
    "compass-forbidden-edge": Counter(PASS=1749, UNKNOWN=23),
    "compass-signature-fail": Counter(PASS=1748, UNKNOWN=23, FAIL=1),
    "compass-dynamic-unknown": Counter(PASS=1747, UNKNOWN=24, FAIL=1),
}


def _payload(html: Path) -> dict:
    match = re.search(
        r'<script[^>]*id="flow-data"[^>]*>(.*?)</script>',
        html.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    assert match
    return json.loads(match.group(1))


def _report(output: Path):
    main = output.with_suffix(".report.html")
    atlas = _payload(main)["atlas"]
    detail = main.with_name(atlas["detail_page"])
    data = _payload(detail)
    assert data["navigation"]["main_href"] == main.name
    return parse_report(
        {
            key: value
            for key, value in data.items()
            if key not in {"initial_scope", "initial_view", "navigation", "boundary_permissions"}
        }
    )


def _assert_named_factory_identities(report) -> None:
    factories = [
        entity
        for entity in report.target.entities
        if entity.kind == "method" and entity.qualified_name.endswith(".fromJson")
    ]
    assert len(factories) == 11
    for factory in factories:
        matches = [
            entity
            for entity in report.observed.entities
            if entity.kind == "method" and entity.qualified_name == factory.qualified_name
        ]
        assert len(matches) == 1
        for aspect in ("existence", "signature"):
            assessment = next(
                item
                for item in report.comparison.assessments
                if item.subject_id == factory.id and item.aspect == aspect
            )
            assert assessment.status == "PASS"


def test_compass_variants_are_source_only_and_keep_the_full_snapshot() -> None:
    assert {variant.id for variant in VARIANTS} == {
        "compass-project",
        "compass-forbidden-edge",
        "compass-signature-fail",
        "compass-dynamic-unknown",
    }
    selected = {
        path.relative_to(COMPASS_FIXTURE_DIR).as_posix()
        for path in COMPASS_FIXTURE_DIR.rglob("*.dart")
    }
    assert len(selected) == 111
    target_paths = (
        "architecture-contract.json",
        "contracts/application.json",
        "contracts/presentation.json",
        "contracts/domain.json",
        "contracts/data.json",
        "contracts/utilities.json",
    )
    target_digest = hashlib.sha256(
        b"".join((COMPASS_FIXTURE_DIR / path).read_bytes() for path in target_paths)
    ).hexdigest()
    assert target_digest == TARGET_DIGEST
    for variant in VARIANTS:
        assert variant.fixture == COMPASS_FIXTURE_DIR
        assert all(path in selected for path in variant.files)
        assert all(path.startswith("lib/") and path.endswith(".dart") for path in variant.files)


def test_compass_forbidden_edge_is_inside_the_data_component_contract() -> None:
    variant = next(row for row in VARIANTS if row.id == "compass-forbidden-edge")
    service_path = "lib/data/services/local/local_data_service.dart"
    assert set(variant.files) == {service_path}
    changed = variant.files[service_path]
    assert "import '../api/api_client.dart';" in changed
    assert "ApiClient().getDestinations();" in changed


def test_compass_reports_keep_target_comparison_and_partial_coverage_distinct(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    expected_comparison = {
        "compass-project": "UNKNOWN",
        "compass-forbidden-edge": "UNKNOWN",
        "compass-signature-fail": "FAIL",
        "compass-dynamic-unknown": "FAIL",
    }
    expected_exit = {variant_id: 2 for variant_id in expected_comparison}
    reports = {}
    module_sets = set()
    contract_digests = set()
    for variant_id, comparison_status in expected_comparison.items():
        output = tmp_path / f"{variant_id}.json"
        registered_case = REPORT_CASES[f"uml-{variant_id}"]
        assert registered_case == (variant_id, expected_exit[variant_id])
        assert replay(variant_id, output) == registered_case[1]
        summaries = [
            json.loads(line)
            for line in capsys.readouterr().out.splitlines()
            if line.startswith("{") and line.endswith("}")
        ]
        report_summary = next(item for item in summaries if item.get("command") == "report")
        assert report_summary["exit_code"] == 2
        assert report_summary["observation_complete"] == "UNKNOWN"
        assert report_summary["declared_rules"] == (
            "UNKNOWN" if variant_id == "compass-project" else "FAIL"
        )
        requires = {
            row["id"]: row["status"]
            for row in report_summary["rule_assessments"]
            if row["kind"] == "complete_requires"
        }
        assert requires == {
            "Compose environment, localization, routes and app shell:REQUIRES-COMPLETE": "PASS",
            "data:REQUIRES-COMPLETE": "FAIL" if variant_id == "compass-forbidden-edge" else "PASS",
            "domain:REQUIRES-COMPLETE": "PASS",
            "presentation:REQUIRES-COMPLETE": "PASS",
            "utilities:REQUIRES-COMPLETE": "PASS",
            "REQUIRES-COMPLETE": "PASS",
        }
        assert report_summary["coverage"]["status"] == "FAIL"
        raw = json.loads(output.read_text(encoding="utf-8"))
        if variant_id == "compass-project":
            assert raw["source"]["source_digest"] == SOURCE_DIGEST
        else:
            assert raw["source"]["source_digest"] != SOURCE_DIGEST
        assert raw["coverage"]["files_discovered"] == 111
        assert raw["coverage"]["files_read"] == 111
        assert raw["coverage"]["files_parsed"] == 111
        assert len(raw["modules"]) == 89
        gaps = [
            item for item in raw["coverage"]["failures"] if item["kind"] == "source_resolution_gap"
        ]
        assert len(gaps) == 30
        assert raw["coverage"]["status"] == "FAIL"
        contract_digests.add(raw["contract"]["digest"])
        assert output.with_suffix(".report.html").is_file()
        assert output.with_suffix(".detail.html").is_file()
        report = _report(output)
        _assert_named_factory_identities(report)
        assert report.comparison and report.comparison.status == comparison_status
        assert (
            Counter(a.status for a in report.comparison.assessments)
            == EXPECTED_ASSESSMENTS[variant_id]
        )
        assert not any(
            a.status == "UNKNOWN" and a.aspect == "completeness"
            for a in report.comparison.assessments
        )
        assert len(report.target.entities) == 468
        assert len(report.target.relationships) == 275
        assert any(item.status == "UNKNOWN" for item in report.comparison.assessments)
        module_sets.add(
            frozenset(
                item.qualified_name for item in report.observed.entities if item.kind == "module"
            )
        )
        reports[variant_id] = report
    assert len(contract_digests) == 1
    assert len(module_sets) == 1

    forbidden = json.loads((tmp_path / "compass-forbidden-edge.json").read_text(encoding="utf-8"))[
        "violations"
    ]
    assert len(forbidden) == 1
    assert forbidden[0][7] == ["data:REQUIRES-COMPLETE"]
    assert forbidden[0][6] == ["EVD-928d55de43475d94"]

    call = "presentation:calls-booking-viewmodel-creates-booking"
    call_assessments = {
        variant_id: next(
            item
            for item in report.comparison.assessments
            if item.subject_id == call and item.aspect == "relationship"
        )
        for variant_id, report in reports.items()
    }
    assert call_assessments["compass-project"].status == "PASS"
    assert call_assessments["compass-forbidden-edge"].status == "PASS"
    assert call_assessments["compass-signature-fail"].status == "PASS"
    assert call_assessments["compass-dynamic-unknown"].status == "UNKNOWN"
    assert (
        call_assessments["compass-project"].evidence_ids
        == call_assessments["compass-signature-fail"].evidence_ids
    )
    assert call_assessments["compass-project"].evidence_ids[0] == "EVD-629d35e6ef2c2631"
    assert "EVD-629d35e6ef2c2631" in call_assessments["compass-dynamic-unknown"].evidence_ids

    signature_subject = (
        "domain:method-compass-domain-use-cases-booking-booking-create-use-case-"
        "bookingcreateusecase-createfrom"
    )
    baseline_signature = next(
        item
        for item in reports["compass-project"].comparison.assessments
        if item.subject_id == signature_subject and item.aspect == "signature"
    )
    signature = next(
        item
        for item in reports["compass-signature-fail"].comparison.assessments
        if item.subject_id == signature_subject and item.aspect == "signature"
    )
    assert baseline_signature.status == "PASS"
    assert signature.status == "FAIL"
    assert baseline_signature.subject_id == signature.subject_id
    assert baseline_signature.evidence_ids == signature.evidence_ids
    assert signature.evidence_ids == ("EVD-cc18c41f101b2432",)
    dynamic_annotation = next(
        item
        for item in reports["compass-dynamic-unknown"].comparison.assessments
        if item.subject_id
        == "presentation:attribute-compass-ui-booking-view-models-booking-viewmodel-"
        "bookingviewmodel-createusecase"
        and item.aspect == "annotation"
    )
    assert dynamic_annotation.status == "FAIL"
    assert dynamic_annotation.evidence_ids == ("EVD-6ed26bccb52971b6",)
