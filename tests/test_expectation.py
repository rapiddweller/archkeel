# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
# DATAMIMIC
# Copyright (c) 2023-2026 Rapiddweller Asia Co., Ltd.
# Enterprise Edition (non-MIT); see repository license terms.

"""Behavioral proofs for the fixed architecture expectation contract."""

from __future__ import annotations

import copy

import pytest

from archkeel.check.delta import SUPPORTED_DIMENSIONS as DELTA_DIMENSIONS
from archkeel.check.expectation import (
    EXPECTATION_SCHEMA_VERSION,
    GUARDRAIL_DIMENSIONS,
    GUARDRAIL_KEYS,
    ExpectationError,
    evaluate_expectation,
    parse_expectation,
)
from archkeel.check.expectation import SUPPORTED_DIMENSIONS as EXPECTATION_DIMENSIONS
from archkeel.ir.codec import parse_delta
from archkeel.ir.digest import package_digest
from archkeel.ir.model import ArchitectureDelta

ANALYZER_DIGEST = "a" * 64
CHECKER_DIGEST = package_digest()
CONTRACT_DIGEST = "c" * 64
BASELINE_DIGEST = "b" * 64
HEAD_DIGEST = "d" * 64
FINGERPRINT = "forbidden_dependency:datamimic_ee.tasks:datamimic_ee.clients"


def _measurements() -> dict[str, object]:
    return {
        "scalars": {
            "violations": 0,
            "cycle_edges": 0,
            "private_crossings": 0,
            "typing_positions": 0,
            "calls_unresolved": 0,
            "coverage_failures": 0,
        },
        "calls_total": 0,
        "resolution": "n/a",
    }


def test_expectation_and_delta_share_the_fixed_dimension_vocabulary() -> None:
    assert EXPECTATION_DIMENSIONS == DELTA_DIMENSIONS


def _expectation_payload() -> dict[str, object]:
    return {
        "schema_version": EXPECTATION_SCHEMA_VERSION,
        "evidence_class": "HYPOTHESIS",
        "checker_digest": CHECKER_DIGEST,
        "accepted_digest": "e" * 64,
        "baseline_commit": "3" * 40,
        "analyzer_digest": ANALYZER_DIGEST,
        "contract_digest": CONTRACT_DIGEST,
        "baseline_digest": BASELINE_DIGEST,
        "selected_changes": [
            {
                "dimension": "violations",
                "change": "removed",
                "fingerprint": FINGERPRINT,
                "before_count": 1,
                "after_count": 0,
            }
        ],
        "guardrails": dict.fromkeys(GUARDRAIL_KEYS, True),
    }


def _delta_payload() -> dict[str, object]:
    dimensions = {
        dimension: {
            "status": "SUPPORTED",
            "before_count": 1,
            "after_count": 1,
            "added": [],
            "removed": [],
            "relocated": [],
            "changed": [],
        }
        for dimension in GUARDRAIL_DIMENSIONS
    }
    dimensions["violations"] = {
        "status": "SUPPORTED",
        "before_count": 1,
        "after_count": 0,
        "added": [],
        "removed": [FINGERPRINT],
        "relocated": [],
        "changed": [],
    }
    return {
        "schema_version": "1.2.0",
        "analyzer": {"name": "observer", "version": "0.3.0", "code_digest": ANALYZER_DIGEST},
        "baseline": {
            "git_head": "1" * 40,
            "source_digest": BASELINE_DIGEST,
            "coverage_status": "PASS",
            "python_version": "3.11.12",
        },
        "head": {
            "git_head": "2" * 40,
            "source_digest": HEAD_DIGEST,
            "coverage_status": "PASS",
            "python_version": "3.11.12",
        },
        "contract": {"schema_version": "1.1.0", "digest": CONTRACT_DIGEST, "path": "contract.json"},
        "provenance": {
            "checker_digest": CHECKER_DIGEST,
            "analyzer_digest": ANALYZER_DIGEST,
            "contract_digest": CONTRACT_DIGEST,
            "baseline_digest": BASELINE_DIGEST,
            "head_digest": HEAD_DIGEST,
        },
        "coverage": {
            "status": "PASS",
            "baseline_status": "PASS",
            "head_status": "PASS",
            "supported_dimensions": list(GUARDRAIL_DIMENSIONS),
            "unknown_dimensions": [],
        },
        "dimensions": dimensions,
        "ratchets": {
            "status": "SUPPORTED",
            "baseline": _measurements(),
            "head": _measurements(),
        },
        "semantic_changes": [
            {
                "dimension": "violations",
                "change": "removed",
                "fingerprint": FINGERPRINT,
                "before_count": 1,
                "after_count": 0,
                "before": {
                    "id": "VIO-before",
                    "evidence_class": "VIOLATION",
                    "area": "architecture",
                    "kind": "forbidden_dependency",
                    "title": "violation",
                    "subjects": [],
                    "data": {},
                    "evidence": [],
                },
                "after": None,
            }
        ],
        "unknowns": [],
    }


def _typed_delta(payload: dict[str, object]) -> ArchitectureDelta:
    return parse_delta(payload)


def test_expectation_requires_hypothesis_and_fixed_guardrails() -> None:
    parsed = parse_expectation(_expectation_payload())

    assert parsed.analyzer_digest == ANALYZER_DIGEST
    assert parsed.selected_changes[0].fingerprint == FINGERPRINT

    wrong_class = _expectation_payload()
    wrong_class["evidence_class"] = "FACT"
    with pytest.raises(ExpectationError, match="must be HYPOTHESIS"):
        parse_expectation(wrong_class)

    disabled_guardrail = _expectation_payload()
    guardrails = disabled_guardrail["guardrails"]
    assert isinstance(guardrails, dict)
    guardrails["no_new_cycles"] = False
    with pytest.raises(ExpectationError, match="must be true"):
        parse_expectation(disabled_guardrail)


def test_expectation_rejects_generic_fields_and_invalid_counts() -> None:
    generic = _expectation_payload()
    generic["rules"] = [{"when": "anything", "then": "pass"}]
    with pytest.raises(ExpectationError, match="fields mismatch"):
        parse_expectation(generic)

    invalid_count = _expectation_payload()
    changes = invalid_count["selected_changes"]
    assert isinstance(changes, list)
    assert isinstance(changes[0], dict)
    changes[0]["before_count"] = True
    with pytest.raises(ExpectationError, match="non-negative integer"):
        parse_expectation(invalid_count)


def test_expected_semantic_fingerprint_and_guardrails_pass() -> None:
    result = evaluate_expectation(
        _typed_delta(_delta_payload()), parse_expectation(_expectation_payload())
    )

    assert result.passed is True
    assert result.failures == ()


def test_missing_fingerprint_and_guardrail_regression_are_governance_failures() -> None:
    delta = _delta_payload()
    semantic_changes = delta["semantic_changes"]
    assert isinstance(semantic_changes, list)
    semantic_changes.clear()
    dimensions = delta["dimensions"]
    assert isinstance(dimensions, dict)
    cycles = dimensions["cycles"]
    assert isinstance(cycles, dict)
    cycles["after_count"] = 2

    result = evaluate_expectation(_typed_delta(delta), parse_expectation(_expectation_payload()))

    assert result.passed is False
    assert result.failures == (
        "guardrail regression in cycles: 1->2",
        f"missing expected violations removed fingerprint {FINGERPRINT}",
    )


def test_new_violation_cannot_be_hidden_by_an_unrelated_removal() -> None:
    delta = _delta_payload()
    dimensions = delta["dimensions"]
    assert isinstance(dimensions, dict)
    violations = dimensions["violations"]
    assert isinstance(violations, dict)
    violations["after_count"] = 1
    semantic_changes = delta["semantic_changes"]
    assert isinstance(semantic_changes, list)
    semantic_changes.append(
        {
            "dimension": "violations",
            "change": "added",
            "fingerprint": "new-hard-violation",
            "before_count": 0,
            "after_count": 1,
            "before": None,
            "after": _projection("VIO-new"),
        }
    )

    result = evaluate_expectation(_typed_delta(delta), parse_expectation(_expectation_payload()))

    assert result.failures == ("guardrail added violations fingerprint new-hard-violation",)


def _projection(identifier: str, data: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "id": identifier,
        "evidence_class": "FACT",
        "area": "architecture",
        "kind": "item",
        "title": identifier,
        "subjects": [],
        "data": data or {},
        "evidence": [],
    }


def _cycle_change(
    *,
    change: str,
    fingerprint: str,
    level: str,
    members: list[str],
) -> dict[str, object]:
    projection = _projection(f"SCC-{fingerprint}", {"level": level, "members": members})
    return {
        "dimension": "cycles",
        "change": change,
        "fingerprint": fingerprint,
        "before_count": 1 if change == "removed" else 0,
        "after_count": 1 if change == "added" else 0,
        "before": projection if change == "removed" else None,
        "after": projection if change == "added" else None,
    }


def _delta_with_replaced_cycle(
    *, old_members: list[str], new_members: list[str], new_level: str = "package"
) -> dict[str, object]:
    delta = _delta_payload()
    dimensions = delta["dimensions"]
    assert isinstance(dimensions, dict)
    cycles = dimensions["cycles"]
    assert isinstance(cycles, dict)
    cycles["before_count"] = 12
    cycles["after_count"] = 11
    semantic_changes = delta["semantic_changes"]
    assert isinstance(semantic_changes, list)
    semantic_changes.extend(
        [
            _cycle_change(
                change="removed",
                fingerprint="old-cycle",
                level="package",
                members=old_members,
            ),
            _cycle_change(
                change="added",
                fingerprint="new-cycle",
                level=new_level,
                members=new_members,
            ),
        ]
    )
    return delta


def test_cycle_guardrail_accepts_strict_same_level_scc_contraction() -> None:
    delta = _delta_with_replaced_cycle(
        old_members=[f"package_{index}" for index in range(15)],
        new_members=[f"package_{index}" for index in range(14)],
    )

    result = evaluate_expectation(_typed_delta(delta), parse_expectation(_expectation_payload()))

    assert result.passed is True


@pytest.mark.parametrize(
    ("old_members", "new_members", "new_level"),
    [
        (["a", "b", "c"], ["a", "b", "d"], "package"),
        (["a", "b", "c"], ["a", "b", "c", "d"], "package"),
        (["a", "b", "c"], ["a", "b"], "module"),
        (["a", "b", "c"], ["a", "b", "c"], "package"),
    ],
)
def test_cycle_guardrail_rejects_non_contractions(
    old_members: list[str],
    new_members: list[str],
    new_level: str,
) -> None:
    delta = _delta_with_replaced_cycle(
        old_members=old_members,
        new_members=new_members,
        new_level=new_level,
    )

    result = evaluate_expectation(_typed_delta(delta), parse_expectation(_expectation_payload()))

    assert result.failures == ("guardrail added cycles fingerprint new-cycle",)


@pytest.mark.parametrize(
    "malformed_after",
    [
        None,
        {"id": "SCC-new-cycle", "data": {"level": "package"}},
    ],
)
def test_cycle_guardrail_fails_closed_on_missing_or_malformed_projection(
    malformed_after: object,
) -> None:
    delta = _delta_with_replaced_cycle(old_members=["a", "b", "c"], new_members=["a", "b"])
    semantic_changes = delta["semantic_changes"]
    assert isinstance(semantic_changes, list)
    added = next(
        change
        for change in semantic_changes
        if isinstance(change, dict)
        and change.get("dimension") == "cycles"
        and change.get("change") == "added"
    )
    added["after"] = malformed_after

    with pytest.raises(ValueError, match="cycle projection|after fields mismatch"):
        evaluate_expectation(_typed_delta(delta), parse_expectation(_expectation_payload()))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("analyzer", "analyzer_digest does not match"),
        ("contract", "contract_digest does not match"),
        ("baseline", "baseline_digest does not match"),
        ("coverage", "coverage status must be PASS"),
        ("unknown_dimension", "cycles is not safely comparable"),
    ],
)
def test_unverifiable_delta_is_an_infrastructure_error(mutation: str, message: str) -> None:
    delta = copy.deepcopy(_delta_payload())
    if mutation in {"analyzer", "contract", "baseline"}:
        provenance = delta["provenance"]
        assert isinstance(provenance, dict)
        provenance[f"{mutation}_digest"] = "f" * 64
    elif mutation == "coverage":
        coverage = delta["coverage"]
        assert isinstance(coverage, dict)
        coverage["status"] = "FAIL"
    else:
        dimensions = delta["dimensions"]
        assert isinstance(dimensions, dict)
        cycles = dimensions["cycles"]
        assert isinstance(cycles, dict)
        cycles["status"] = "UNKNOWN"

    with pytest.raises(ExpectationError, match=message):
        evaluate_expectation(_typed_delta(delta), parse_expectation(_expectation_payload()))
