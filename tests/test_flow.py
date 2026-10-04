# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The shared report retains every original import and Core judgement."""

import json
from pathlib import Path

import pytest
from test_architecture_demo import CONFIG, _prepare_repo

from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.report_graph import architecture_report
from fixtures.architecture_demo import CATALOG
from fixtures.demo_catalog_support import contract_without_rule


@pytest.mark.parametrize("variant", ["tour", "clean", "class-a-sibling-isolation"])
def test_report_preserves_all_import_sites_and_original_findings(tmp_path: Path, variant):
    case = next(item for item in CATALOG if item.id == variant)
    root = _prepare_repo(tmp_path, dict(case.files))
    _, encoded = run_report(root, config=CONFIG, analyzer=observe)
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    assert report.observed is not None
    imports = model.records("imports") or ()
    sites = tuple(item for item in report.observed.relationships if item.kind == "imports")
    assert {record_id for item in sites for record_id in item.record_ids} == {
        item.id for item in imports
    }
    assert len(sites) == len(imports)
    for section, status in (("violations", "FAIL"), ("unknowns", "UNKNOWN")):
        originals = {item.id: item for item in model.records(section) or ()}
        findings = {item.id: item for item in report.findings if item.status == status}
        assert findings.keys() == originals.keys()
        for identity, finding in findings.items():
            assert finding.rule_ids == originals[identity].rule_ids
            assert finding.evidence_ids == originals[identity].evidence_ids
    if variant == "clean":
        assert not any(item.status == "FAIL" for item in report.findings)
    else:
        assert any(item.status == "FAIL" for item in report.findings)


@pytest.mark.parametrize(
    "rule,target", [("DEP-APP-ALLOWS-MODEL", "model"), ("DEP-APP-ALLOWS-STORE", "store")]
)
def test_open_dependency_decision_never_replaces_recorded_failure(tmp_path: Path, rule, target):
    tour = next(item for item in CATALOG if item.id == "tour")
    root = _prepare_repo(
        tmp_path, {**dict(tour.files), "architecture-contract.json": contract_without_rule(rule)}
    )
    _, encoded = run_report(root, config=CONFIG, analyzer=observe)
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    labels = {item.label: item.component_id for item in report.target.component_intents}
    gap = next(
        item
        for item in report.decision_gaps
        if (item.source_id, item.target_id) == (labels["app"], labels[target])
    )
    assert gap.relationship_ids
    assert not any(
        item.status == "UNKNOWN" and item.kind == "decision.open" for item in report.findings
    )
    if target == "store":
        ids = set(gap.relationship_ids)
        assert any(
            item.status == "FAIL" and ids.intersection(item.graph_subject_ids)
            for item in report.findings
        )
