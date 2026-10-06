# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #314: filtered JSON opens recorded evidence and drops passing rule rows."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_report_filter import CONFIG
from test_result_schema import validator as validator
from test_target_graph import _nested_repository

from archkeel.check.report import run_report
from archkeel.cli import main
from archkeel.cli.observe import observe
from archkeel.ir.codec import (
    _architecture_component_payload,
    decode_canonical_model,
    parse_observation,
    result_bytes,
    result_payload,
)
from archkeel.ir.report_projection import architecture_command_envelope
from archkeel.render.html import render_architecture_html
from fixtures.architecture_demo import CATALOG


def _root(tmp_path: Path, variant_id: str) -> Path:
    if variant_id == "mixed":
        unknown = next(
            item for item in CATALOG if item.id == "class-a-boundary-types-shadowed-dict-unknown"
        )
        failing = next(item for item in CATALOG if item.id == "class-a-forbidden-dependency-pair")
        return _prepare_repo(tmp_path, {**unknown.files, **failing.files})
    variant = next(item for item in CATALOG if item.id == variant_id)
    return _prepare_repo(tmp_path, dict(variant.files), variant.fixture)


def test_architecture_json_is_compact_by_default_and_full_query_restores_details(
    tmp_path, validator
):
    root = _root(tmp_path, "tour")
    compact, _ = run_report(root, config=CONFIG, analyzer=observe, only_architecture=True)
    complete, _ = run_report(
        root,
        config=CONFIG,
        analyzer=observe,
        only_architecture=True,
        full_architecture=True,
    )
    compact_payload = result_payload(compact)
    full_payload = result_payload(complete)
    compact_projection = compact_payload["architecture_projection"]
    full_projection = full_payload["architecture_projection"]
    assert "permission_rules" not in compact_projection
    assert "policy_context" not in compact_projection
    assert "filtered_violations" not in compact_payload
    assert compact_payload["filtered_violation_count"] == len(compact.filtered_violations or ())
    assert compact_payload["violation_details_included"] is False
    contradictory_compact = copy.deepcopy(compact_payload)
    contradictory_compact["violation_details_included"] = True
    assert list(validator.iter_errors(contradictory_compact))
    assert all("finding_count" in component for component in compact_projection["components"])
    assert full_projection["permission_rules"]
    assert "policy_context" in full_projection
    full_view = architecture_command_envelope(complete).architecture_projection
    assert full_projection["components"] == [
        _architecture_component_payload(component) for component in full_view.components
    ]
    assert {item["id"] for item in full_payload["filtered_violations"]} == {
        item.record.id for item in complete.filtered_violations or ()
    }
    assert full_payload["filtered_violation_count"] == len(complete.filtered_violations or ())
    assert full_payload["violation_details_included"] is True
    contradictory_full = copy.deepcopy(full_payload)
    contradictory_full["violation_details_included"] = False
    assert list(validator.iter_errors(contradictory_full))
    assert compact_payload["declared_rules"] == full_payload["declared_rules"]
    assert compact.exit_code == complete.exit_code
    assert not list(validator.iter_errors(compact_payload))
    assert not list(validator.iter_errors(full_payload))


def test_architecture_json_reports_selected_scope_violation_count(tmp_path, validator):
    root = _root(tmp_path, "tour")
    scoped_full, _ = run_report(
        root,
        config=CONFIG,
        analyzer=observe,
        only_architecture=True,
        full_architecture=True,
        component="store",
    )
    scoped, _ = run_report(
        root, config=CONFIG, analyzer=observe, only_architecture=True, component="store"
    )
    full_payload = result_payload(scoped_full)
    payload = result_payload(scoped)
    global_count = scoped.measurements.scalars.violations
    assert scoped.filtered_violations is not None
    assert len(scoped.filtered_violations) < global_count
    assert "filtered_violations" not in payload
    assert payload["filtered_violation_count"] == len(scoped.filtered_violations)
    assert payload["filtered_violation_count"] != global_count
    assert payload["violation_details_included"] is False
    assert payload["declared_rules"] == "FAIL"
    assert not list(validator.iter_errors(payload))
    assert len(full_payload["filtered_violations"]) == len(scoped_full.filtered_violations or ())
    assert full_payload["filtered_violation_count"] == len(scoped_full.filtered_violations or ())
    assert full_payload["violation_details_included"] is True
    assert not list(validator.iter_errors(full_payload))


def test_architecture_json_full_empty_and_unavailable_details_are_distinct(tmp_path, validator):
    root = _root(tmp_path, "clean")
    measured, _ = run_report(
        root,
        config=CONFIG,
        analyzer=observe,
        only_architecture=True,
        full_architecture=True,
    )
    measured_payload = result_payload(measured)
    assert measured.filtered_violations == ()
    assert measured_payload["filtered_violations"] == []
    assert measured_payload["filtered_violation_count"] == 0
    assert measured_payload["violation_details_included"] is True
    assert not list(validator.iter_errors(measured_payload))
    contradictory_empty = copy.deepcopy(measured_payload)
    contradictory_empty["violation_details_included"] = False
    assert list(validator.iter_errors(contradictory_empty))
    compact_measured, _ = run_report(root, config=CONFIG, analyzer=observe, only_architecture=True)
    compact_measured_payload = result_payload(compact_measured)
    assert "filtered_violations" not in compact_measured_payload
    assert compact_measured_payload["filtered_violation_count"] == 0
    assert compact_measured_payload["violation_details_included"] is False
    leaked_details = copy.deepcopy(compact_measured_payload)
    leaked_details["filtered_violations"] = []
    assert list(validator.iter_errors(leaked_details))
    assert not list(validator.iter_errors(compact_measured_payload))

    broken_root = _root(tmp_path / "broken", "class-a-forbidden-dependency-pair")
    (broken_root / "shop/app/broken.py").write_text("def broken(:\n")
    unavailable, _ = run_report(
        broken_root,
        config=CONFIG,
        analyzer=observe,
        only_architecture=True,
        full_architecture=True,
    )
    unavailable_payload = result_payload(unavailable)
    assert unavailable.filtered_violations is None
    assert unavailable_payload["filtered_violations"] is None
    assert unavailable_payload["filtered_violation_count"] is None
    assert unavailable_payload["violation_details_included"] is False
    assert not list(validator.iter_errors(unavailable_payload))
    contradictory_unavailable = copy.deepcopy(unavailable_payload)
    contradictory_unavailable["violation_details_included"] = True
    assert list(validator.iter_errors(contradictory_unavailable))
    compact_unavailable, _ = run_report(
        broken_root, config=CONFIG, analyzer=observe, only_architecture=True
    )
    compact_unavailable_payload = result_payload(compact_unavailable)
    assert "filtered_violations" not in compact_unavailable_payload
    assert compact_unavailable_payload["filtered_violation_count"] is None
    assert compact_unavailable_payload["violation_details_included"] is False
    assert not list(validator.iter_errors(compact_unavailable_payload))


def test_nested_architecture_json_compact_and_full_schema_variants(tmp_path, validator):
    root, config = _nested_repository(tmp_path)
    compact, _ = run_report(root, config=config, analyzer=observe, only_architecture=True)
    full, _ = run_report(
        root,
        config=config,
        analyzer=observe,
        only_architecture=True,
        full_architecture=True,
    )
    compact_payload = result_payload(compact)
    full_payload = result_payload(full)
    compact_components = compact_payload["architecture_projection"]["components"]
    nested = [item for item in compact_components if item.get("parent_id") is not None]
    assert nested
    assert all("finding_count" in item for item in compact_components)
    assert all("path" not in item and "provenance" not in item for item in nested)
    assert "permission_rules" not in compact_payload["architecture_projection"]
    assert not list(validator.iter_errors(compact_payload))
    assert not list(validator.iter_errors(full_payload))
    assert all(
        {"path", "provenance", "packages", "not_responsible_for"} <= item.keys()
        for item in full_payload["architecture_projection"]["components"]
    )
    incomplete_full = copy.deepcopy(full_payload)
    nested_full = next(
        item
        for item in incomplete_full["architecture_projection"]["components"]
        if item.get("parent_id") is not None
    )
    del nested_full["path"]
    assert list(validator.iter_errors(incomplete_full))


def test_complete_assignment_json_names_owner_candidates_and_remedy(tmp_path, capsys, validator):
    root = _root(tmp_path, "clean")
    contract_path = root / "architecture-contract.json"
    contract = json.loads(contract_path.read_bytes())
    contract["rules"].append(
        {
            "id": "ASSIGN-SHOP",
            "kind": "complete_assignment",
            "source": "shop",
            "rationale": "Every module has one owner.",
            "provenance": ["docs/architecture.md"],
            "decided_by": "architect",
        }
    )
    (root / "shop/unowned.py").write_text("VALUE = 1\n")
    contract_path.write_text(json.dumps(contract))
    result, _ = run_report(
        root, config=CONFIG, analyzer=observe, only_architecture=True, full_architecture=True
    )
    payload = result_payload(result)
    unowned_violation = next(
        item for item in payload["filtered_violations"] if item["kind"] == "complete_assignment"
    )
    expected_owners = {"none"}
    assert set(unowned_violation["owners"]) == expected_owners
    assert unowned_violation["remedy"]
    assert len(json.dumps(unowned_violation, separators=(",", ":")).encode()) <= 5 * 1024
    assert not list(validator.iter_errors(payload))

    assert (
        main(
            [
                "report",
                "--root",
                str(root),
                "--only",
                "violations",
                "--rule",
                "ASSIGN-SHOP",
                "--json",
            ]
        )
        == 0
    )
    focused = json.loads(capsys.readouterr().out)
    (focused_violation,) = focused["filtered_violations"]
    assert focused_violation["kind"] == "complete_assignment"
    assert set(focused_violation["owners"]) == expected_owners
    assert focused_violation["remedy"] == unowned_violation["remedy"]
    assert len(json.dumps(focused, separators=(",", ":")).encode()) <= 5000
    assert not list(validator.iter_errors(focused))


def test_filtered_assignment_names_each_claiming_owner(tmp_path, capsys, validator):
    from test_module_explore import _sample

    from archkeel.ir.codec import canonical_report_bytes

    model = _sample(
        tmp_path,
        ambiguous=True,
        extra_rules=(
            {
                "id": "assignment",
                "kind": "complete_assignment",
                "source": "sample.core",
                "rationale": "Each module has one owner.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            },
        ),
    )
    snapshot = tmp_path / "architecture.json"
    snapshot.write_bytes(canonical_report_bytes(model))
    assert (
        main(
            [
                "report",
                "--input",
                str(snapshot),
                "--only",
                "violations",
                "--rule",
                "assignment",
                "--component",
                "core",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    (violation,) = payload["filtered_violations"]
    assert set(violation["owners"]) == {"core", "overlap"}
    assert violation["remedy"]
    assert not list(validator.iter_errors(payload))
    assert len(json.dumps(payload, separators=(",", ":")).encode()) <= 5000


def test_cli_filtered_violation_opens_the_recorded_source_line(tmp_path, capsys, validator):
    root = _root(tmp_path, "class-a-forbidden-dependency-pair")
    assert main(["report", "--root", str(root), "--only", "violations", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    (violation,) = payload["filtered_violations"]
    assert violation["rule_ids"] == ["DEP-RENDER-NO-STORE"]
    assert violation["locations"] == [{"path": "shop/render/text.py", "line": 9}]
    assert not list(validator.iter_errors(payload))


@pytest.mark.parametrize("variant_id", ["class-a-forbidden-dependency-pair", "tour"])
@pytest.mark.parametrize(
    "facet", [{"only_violations": True}, {"rule": "DEP-RENDER-NO-STORE"}, {"component": "render"}]
)
def test_locations_match_html_recorded_evidence_without_changing_observation(
    tmp_path, facet, variant_id
):
    root = _root(tmp_path, variant_id)
    unfiltered, complete = run_report(root, config=CONFIG, analyzer=observe)
    filtered, architecture = run_report(root, config=CONFIG, analyzer=observe, **facet)
    assert architecture == complete and architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    payload = result_payload(filtered)
    page = render_architecture_html(
        filtered, architecture, repository="shop", architecture_href="architecture.json"
    ).decode()
    records = {item.id: item for item in observation.records("violations") or ()}
    for violation in payload["filtered_violations"]:
        evidence = [
            item
            for item in observation.evidence
            if item.id in records[violation["id"]].evidence_ids
        ]
        assert violation["locations"] == [
            {"path": item.file, "line": item.line} for item in evidence
        ]
        assert all(f"{item.file}:{item.line}" in page for item in evidence)
    assert filtered.measurements == unfiltered.measurements
    assert filtered.declared_rules == unfiltered.declared_rules == "FAIL"
    assert filtered.violations_by_rule == unfiltered.violations_by_rule
    assert filtered.violations_by_component_pair == unfiltered.violations_by_component_pair
    assert filtered.exit_code == unfiltered.exit_code == 0
    if facet.get("rule") or facet.get("component"):
        assert filtered.rule_assessments is not None
        selected_rule_ids = {
            rule_id
            for violation in filtered.filtered_violations or ()
            for rule_id in violation.record.rule_ids
        }
        assessment_ids = {item.id for item in filtered.rule_assessments}
        if facet.get("component"):
            assert "DEP-RENDER-NO-STORE" in assessment_ids
            assert "DEP-APP-NO-STORE-BACKEND" not in assessment_ids
        else:
            assert assessment_ids <= selected_rule_ids


@pytest.mark.parametrize(
    "variant_id",
    [
        "clean",
        "class-a-forbidden-dependency-pair",
        "class-a-boundary-types-shadowed-dict-unknown",
        "tour",
        "mixed",
    ],
)
def test_only_violations_keeps_fail_and_unknown_assessments(tmp_path, validator, variant_id):
    root = _root(tmp_path, variant_id)
    full, _ = run_report(root, config=CONFIG, analyzer=observe)
    filtered, _ = run_report(root, config=CONFIG, analyzer=observe, only_violations=True)
    assert full.rule_assessments is not None
    assert filtered.rule_assessments == tuple(
        item for item in full.rule_assessments if item.status in {"FAIL", "UNKNOWN"}
    )
    if variant_id == "mixed":
        assert {item.status for item in filtered.rule_assessments} == {"FAIL", "UNKNOWN"}
    assert full.measurements == filtered.measurements
    assert full.declared_rules == filtered.declared_rules
    assert not list(validator.iter_errors(result_payload(full)))
    assert not list(validator.iter_errors(result_payload(filtered)))


def test_passing_assessment_rows_account_for_filtered_output_reduction(tmp_path):
    root = _root(tmp_path, "class-a-forbidden-dependency-pair")
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_bytes())
    template = next(rule for rule in contract["rules"] if rule["id"] == "DEP-APP-NO-CLI")
    contract["rules"].extend({**template, "id": f"PASS-{index}"} for index in range(40))
    path.write_text(json.dumps(contract))
    full, _ = run_report(root, config=CONFIG, analyzer=observe)
    filtered, _ = run_report(root, config=CONFIG, analyzer=observe, only_violations=True)
    assert full.rule_assessments is not None and filtered.rule_assessments is not None
    removed = [item for item in full.rule_assessments if item.status in {"PASS", "DECLARATION"}]
    assert len(removed) >= 40
    removed_bytes = len(json.dumps(result_payload(full)["rule_assessments"])) - len(
        json.dumps(result_payload(filtered)["rule_assessments"])
    )
    assert len(result_bytes(full)) - len(result_bytes(filtered)) > removed_bytes * 0.9


@pytest.mark.parametrize("file_only", [False, True])
def test_locations_never_guess_a_source_line_without_recorded_evidence(
    tmp_path, file_only, validator
):
    root = _root(tmp_path, "class-a-forbidden-dependency-pair")
    _, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    model = parse_observation(decode_canonical_model(json.loads(architecture)))
    (violation,) = model.records("violations")
    evidence_ids = set(violation.evidence_ids)
    evidence = (
        tuple(
            replace(item, line=0, end_line=0, column=0, excerpt="")
            if item.id in evidence_ids
            else item
            for item in model.evidence
        )
        if file_only
        else model.evidence
    )
    sections = (
        tuple(
            replace(
                section,
                records=tuple(
                    replace(item, evidence_ids=()) if item.id == violation.id else item
                    for item in section.records
                ),
            )
            for section in model.sections
        )
        if not file_only
        else model.sections
    )
    recorded = replace(model, evidence=evidence, sections=sections)

    def analyzer(*args, **kwargs):
        result = observe(*args, **kwargs)
        return replace(result, observation=recorded, coverage=recorded.coverage)

    filtered, _ = run_report(root, config=CONFIG, analyzer=analyzer, only_violations=True)
    payload = result_payload(filtered)
    assert payload["filtered_violations"][0]["locations"] == (
        [{"path": "shop/render/text.py", "line": 0}] if file_only else []
    )
    assert not list(validator.iter_errors(payload))


@pytest.mark.parametrize(
    "location",
    [
        {"path": "x.py", "line": -1},
        {"path": "x.py", "line": True},
        {"path": "x.py", "line": "9"},
        {"path": "", "line": 9},
        {"path": "x.py"},
        {"line": 9},
        {"path": "x.py", "line": 9, "guess": True},
    ],
)
def test_result_schema_rejects_malformed_locations(tmp_path, validator, location):
    root = _root(tmp_path, "class-a-forbidden-dependency-pair")
    result, _ = run_report(root, config=CONFIG, analyzer=observe, only_violations=True)
    payload = copy.deepcopy(result_payload(result))
    payload["filtered_violations"][0]["locations"] = [location]
    assert not validator.is_valid(payload)


def test_result_schema_requires_locations_and_filtered_assessment_statuses(tmp_path, validator):
    root = _root(tmp_path, "class-a-forbidden-dependency-pair")
    full, _ = run_report(root, config=CONFIG, analyzer=observe)
    result, _ = run_report(root, config=CONFIG, analyzer=observe, only_violations=True)
    payload = result_payload(result)
    del payload["filtered_violations"][0]["locations"]
    assert not validator.is_valid(payload)
    payload = result_payload(result)
    payload["rule_assessments"] = result_payload(full)["rule_assessments"]
    assert not validator.is_valid(payload)


def test_incomplete_observation_keeps_unknown_assessments_when_filtered(tmp_path, validator):
    root = _root(tmp_path, "class-a-forbidden-dependency-pair")
    (root / "shop/app/broken.py").write_text("def broken(:\n")
    full, _ = run_report(root, config=CONFIG, analyzer=observe)
    filtered, _ = run_report(root, config=CONFIG, analyzer=observe, only_violations=True)
    assert full.rule_assessments is not None
    assert filtered.rule_assessments == tuple(
        item for item in full.rule_assessments if item.status in {"FAIL", "UNKNOWN"}
    )
    assert any(item.status == "UNKNOWN" for item in filtered.rule_assessments)
    assert full.exit_code == filtered.exit_code == 2
    assert full.measurements == filtered.measurements is None
    assert not list(validator.iter_errors(result_payload(full)))
    assert not list(validator.iter_errors(result_payload(filtered)))


def test_filter_preserves_resolved_baseline_comparisons_after_dropping_pass_rows(tmp_path):
    from archkeel.ir.baseline import KnownViolation, ViolationFingerprint
    from archkeel.ir.codec import baseline_bytes

    root = _root(tmp_path, "class-a-forbidden-dependency-pair")
    baseline = root / "baseline.json"
    baseline.write_bytes(
        baseline_bytes(
            (KnownViolation(ViolationFingerprint(("DEP-APP-NO-CLI",), ("shop.app.orders",)), 1),)
        )
    )
    full, _ = run_report(root, config=CONFIG, analyzer=observe, baseline=baseline)
    filtered, _ = run_report(
        root, config=CONFIG, analyzer=observe, baseline=baseline, only_violations=True
    )
    assert full.baseline_comparisons == filtered.baseline_comparisons
    assert filtered.baseline_comparisons[0].status == "resolved"


def test_dangling_source_evidence_still_fails_closed(tmp_path, validator):
    root = _root(tmp_path, "class-a-forbidden-dependency-pair")

    def analyzer(*args, **kwargs):
        observed = observe(*args, **kwargs)
        model = observed.observation
        assert model is not None
        return replace(observed, observation=replace(model, evidence=()))

    filtered, _ = run_report(root, config=CONFIG, analyzer=analyzer, only_violations=True)
    assert filtered.exit_code == 2
    assert filtered.filtered_violations is None
    assert filtered.declared_rules == "UNKNOWN"
    assert not list(validator.iter_errors(result_payload(filtered)))


@pytest.mark.parametrize("facet", [{"only_violations": True}, {"only_calls": True}])
@pytest.mark.parametrize("failure", ["parse", "dangling_evidence"])
def test_failed_filtered_report_keeps_unmeasured_rows_null(tmp_path, validator, facet, failure):
    root = _root(tmp_path, "class-a-forbidden-dependency-pair")
    if failure == "parse":
        (root / "shop/app/broken.py").write_text("def broken(:\n")

    def analyzer(*args, **kwargs):
        observed = observe(*args, **kwargs)
        if failure == "parse":
            return observed
        model = observed.observation
        assert model is not None
        return replace(observed, observation=replace(model, evidence=()))

    result, _ = run_report(root, config=CONFIG, analyzer=analyzer, **facet)
    payload = result_payload(result)
    assert result.exit_code == 2 and result.observation_complete == "UNKNOWN"
    assert payload["filtered_calls"] is None and payload["filtered_violations"] is None
    assert not list(validator.iter_errors(payload))
