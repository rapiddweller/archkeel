# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from __future__ import annotations

import hashlib
from typing import Any

import pytest

from archkeel.check.delta import build_architecture_delta
from archkeel.ir.codec import (
    canonical_json_bytes,
    canonical_report_bytes,
    delta_payload,
    parse_observation,
)
from archkeel.ir.digest import package_digest
from archkeel.ir.model import CLASSIFIED_SECTIONS


def _evidence(identifier: str, line: int) -> dict[str, Any]:
    return {
        "id": identifier,
        "file": "datamimic_ee/tasks/sample.py",
        "line": line,
        "end_line": line,
        "column": 0,
        "excerpt": "from datamimic_ee.clients import Client",
    }


def _record(
    identifier: str,
    *,
    kind: str,
    evidence_id: str | None = None,
    data: dict[str, Any] | None = None,
    evidence_class: str = "FACT",
) -> dict[str, Any]:
    return {
        "id": identifier,
        "evidence_class": evidence_class,
        "area": "architecture",
        "kind": kind,
        "title": kind,
        "subjects": ["datamimic_ee.tasks", "datamimic_ee.clients"],
        "evidence_ids": [evidence_id] if evidence_id else [],
        "rule_ids": ["DEP-TASKS-NO-CLIENTS"] if evidence_class == "VIOLATION" else [],
        "fact_ids": [],
        "provenance": [],
        "data": data or {},
    }


def _model(
    *,
    git_head: str,
    violations: list[dict[str, Any]] | None = None,
    dependency_edges: list[dict[str, Any]] | None = None,
    imports: list[dict[str, Any]] | None = None,
    typing_signals: list[dict[str, Any]] | None = None,
    unknowns: list[dict[str, Any]] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    coverage_status: str = "PASS",
) -> dict[str, Any]:
    raw = {
        "schema_version": "1.3.0",
        "python_version": "3.11.12",
        "analyzer": {"name": "observer", "version": "0.3.0", "code_digest": "a" * 64},
        "source": {
            "git_head": git_head,
            "dirty": False,
            "source_digest": hashlib.sha256(git_head.encode()).hexdigest(),
            "scope": ["datamimic_ee/**/*.py"],
        },
        "contract": {
            "schema_version": "1.1.0",
            "digest": "b" * 64,
            "path": "docs/architecture/architecture-contract.json",
        },
        "coverage": {
            "status": coverage_status,
            "rules": "PASS",
            "failures": []
            if coverage_status == "PASS"
            else [_record("coverage-failure", kind="failure")],
            "files_discovered": 1,
            "files_read": 1,
            "files_parsed": 1,
            "ast_coverage_percent": 100.0,
            "calls_analyzed": 0,
            "calls_resolved": 0,
            "calls_partially_resolved": 0,
            "calls_unresolved": 0,
            "call_resolution_percent": 0.0,
        },
        "violations": violations or [],
        "dependency_edges": dependency_edges or [],
        "cycles": [],
        "imports": imports or [],
        "typing_signals": typing_signals or [],
        "unknowns": unknowns or [],
        "evidence": evidence or [],
    }
    for section in CLASSIFIED_SECTIONS:
        raw.setdefault(section, [])
    return raw


def _delta(baseline: dict[str, Any], head: dict[str, Any]) -> dict[str, Any]:
    return delta_payload(
        build_architecture_delta(
            parse_observation(baseline),
            parse_observation(head),
            baseline_digest=hashlib.sha256(canonical_report_bytes(baseline)).hexdigest(),
            head_digest=hashlib.sha256(canonical_report_bytes(head)).hexdigest(),
            checker_digest=package_digest(),
        )
    )


def _semantic_change(delta: dict[str, Any], dimension: str, kind: str) -> dict[str, Any]:
    return next(
        item
        for item in delta["semantic_changes"]
        if item["dimension"] == dimension and item["change"] == kind
    )


def _violation(identifier: str, evidence_id: str) -> dict[str, Any]:
    return _record(
        identifier,
        kind="forbidden_dependency",
        evidence_id=evidence_id,
        evidence_class="VIOLATION",
        data={
            "source_module": "datamimic_ee.tasks.sample",
            "target_module": "datamimic_ee.clients.api",
            "symbol": "Client",
            "under_type_checking": False,
        },
    )


def test_line_only_move_is_relocated_not_added_or_removed() -> None:
    baseline = _model(
        git_head="1" * 40,
        violations=[_violation("VIO-old", "EVD-old")],
        evidence=[_evidence("EVD-old", 10)],
    )
    head = _model(
        git_head="2" * 40,
        violations=[_violation("VIO-new", "EVD-new")],
        evidence=[_evidence("EVD-new", 30)],
    )

    delta = _delta(baseline, head)
    dimension = delta["dimensions"]["violations"]

    assert dimension["status"] == "SUPPORTED"
    assert len(dimension["relocated"]) == 1
    assert not dimension["added"] and not dimension["removed"] and not dimension["changed"]
    relocated = _semantic_change(delta, "violations", "relocated")
    assert dimension["relocated"] == [relocated["fingerprint"]]
    assert relocated["before"]["evidence"][0]["line"] == 10
    assert relocated["after"]["evidence"][0]["line"] == 30


def test_multiset_comparison_preserves_duplicate_cardinality() -> None:
    baseline = _model(
        git_head="1" * 40,
        violations=[_violation("VIO-1", "EVD-1"), _violation("VIO-2", "EVD-2")],
        evidence=[_evidence("EVD-1", 10), _evidence("EVD-2", 20)],
    )
    head = _model(
        git_head="2" * 40,
        violations=[_violation("VIO-1", "EVD-1")],
        evidence=[_evidence("EVD-1", 10)],
    )

    delta = _delta(baseline, head)
    dimension = delta["dimensions"]["violations"]

    assert dimension["before_count"] == 2
    assert dimension["after_count"] == 1
    assert len(dimension["removed"]) == 1
    assert _semantic_change(delta, "violations", "removed")["before_count"] == 1


def test_semantic_change_on_same_edge_is_changed() -> None:
    baseline_edge = _record(
        "EDGE-old",
        kind="package_dependency",
        data={"level": "package", "source": "a", "target": "b", "count": 1, "runtime_count": 1},
    )
    head_edge = _record(
        "EDGE-new",
        kind="package_dependency",
        data={"level": "package", "source": "a", "target": "b", "count": 2, "runtime_count": 2},
    )

    delta = _delta(
        _model(git_head="1" * 40, dependency_edges=[baseline_edge]),
        _model(git_head="2" * 40, dependency_edges=[head_edge]),
    )
    dimension = delta["dimensions"]["dependency_edges"]

    assert len(dimension["changed"]) == 1
    change = _semantic_change(delta, "dependency_edges", "changed")
    assert dimension["changed"] == [change["fingerprint"]]
    assert change["before_count"] == change["after_count"] == 1


def test_aggregate_delta_evidence_is_bounded_and_reports_truncation() -> None:
    imports = []
    evidence = []
    for index in range(20):
        evidence_id = f"EVD-{index}"
        import_record = _record(
            f"IMP-{index}",
            kind="import",
            evidence_id=evidence_id,
            data={"source_package": "a", "target_package": "b", "symbol": None},
        )
        imports.append(import_record)
        evidence.append(_evidence(evidence_id, index + 1))
    edge = _record(
        "EDGE-a-b",
        kind="package_dependency",
        data={"level": "package", "source": "a", "target": "b", "count": 20},
    )
    edge["fact_ids"] = [item["id"] for item in imports]

    delta = _delta(
        _model(git_head="1" * 40, dependency_edges=[edge], imports=imports, evidence=evidence),
        _model(git_head="2" * 40),
    )
    projection = _semantic_change(delta, "dependency_edges", "removed")["before"]

    assert len(projection["evidence"]) == 16
    assert projection["data"]["delta_evidence"] == {
        "available": 20,
        "embedded": 16,
        "truncated": True,
    }


def test_missing_dimension_and_incomplete_coverage_fail_closed() -> None:
    baseline = _model(git_head="1" * 40)
    head = _model(git_head="2" * 40, coverage_status="FAIL")
    del head["imports"]

    with pytest.raises(ValueError, match="observation fields mismatch"):
        _delta(baseline, head)
    head["imports"] = []
    delta = _delta(baseline, head)

    assert delta["coverage"]["status"] == "FAIL"
    assert delta["dimensions"]["api_crossings"]["status"] == "UNKNOWN"
    assert delta["dimensions"]["violations"]["status"] == "UNKNOWN"
    assert delta["dimensions"]["coverage"]["status"] == "SUPPORTED"
    assert all(item["evidence_class"] == "UNKNOWN" for item in delta["unknowns"])


def test_delta_serialization_is_deterministic_for_reordered_inputs() -> None:
    first_import = _record(
        "IMP-1",
        kind="import",
        data={
            "source_module": "datamimic_ee.tasks.a",
            "source_package": "datamimic_ee.tasks",
            "target_module": "datamimic_ee.clients.a",
            "target_package": "datamimic_ee.clients",
            "symbol": "ClientA",
        },
    )
    second_import = _record(
        "IMP-2",
        kind="import",
        data={
            "source_module": "datamimic_ee.tasks.b",
            "source_package": "datamimic_ee.tasks",
            "target_module": "datamimic_ee.clients.b",
            "target_package": "datamimic_ee.clients",
            "symbol": "ClientB",
        },
    )
    baseline = _model(git_head="1" * 40)
    first = _model(git_head="2" * 40, imports=[first_import, second_import])
    second = _model(git_head="2" * 40, imports=[second_import, first_import])

    first_delta = build_architecture_delta(
        parse_observation(baseline),
        parse_observation(first),
        baseline_digest="c" * 64,
        head_digest="d" * 64,
        checker_digest=package_digest(),
    )
    second_delta = build_architecture_delta(
        parse_observation(baseline),
        parse_observation(second),
        baseline_digest="c" * 64,
        head_digest="d" * 64,
        checker_digest=package_digest(),
    )

    assert canonical_json_bytes(delta_payload(first_delta)) == canonical_json_bytes(
        delta_payload(second_delta)
    )
