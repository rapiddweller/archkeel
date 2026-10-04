# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Typed comparison evidence must survive strict wire round trips."""

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from archkeel.ir.architecture_graph import EntityCorrespondence, GraphAssessment, GraphComparison
from archkeel.ir.graph_codec import comparison_bytes, parse_comparison
from tools.architecture_graph_schema import comparison_schema


def _comparison():
    return GraphComparison(
        "FAIL",
        (
            GraphAssessment(
                "result",
                "target-run",
                "signature",
                "FAIL",
                "changed",
                "Parameter count differs.",
                ("definition",),
                ("proof",),
                ("fact",),
            ),
        ),
        correspondences=(EntityCorrespondence("target-run", ("definition",)),),
    )


def test_comparison_round_trip_preserves_identity_evidence_and_status():
    comparison = _comparison()
    encoded = comparison_bytes(comparison)
    assert parse_comparison(json.loads(encoded)) == comparison
    schema = comparison_schema()
    Draft202012Validator(schema).validate(json.loads(encoded))
    saved = Path(__file__).parents[1] / "schema/architecture-comparison.schema.json"
    assert json.loads(saved.read_bytes()) == schema


@pytest.mark.parametrize("change", ["field", "version", "status", "duplicate", "evidence"])
def test_comparison_wire_rejects_inconsistent_or_untyped_results(change):
    raw = json.loads(json.dumps(asdict(_comparison())))
    if change == "field":
        raw["surprise"] = True
    elif change == "version":
        raw["schema_version"] = "99.0.0"
    elif change == "status":
        raw["status"] = "PASS"
    elif change == "duplicate":
        raw["assessments"].append(raw["assessments"][0])
    else:
        raw["assessments"][0]["evidence_ids"] = [False]
    with pytest.raises(ValueError):
        parse_comparison(raw)


def test_empty_comparison_cannot_claim_pass():
    with pytest.raises(ValueError):
        comparison_bytes(GraphComparison("PASS"))


def test_old_comparison_without_correspondences_remains_readable():
    raw = json.loads(comparison_bytes(_comparison()))
    raw.pop("correspondences")
    decoded = parse_comparison(raw)
    assert not decoded.correspondences and decoded.status == "FAIL"


@pytest.mark.parametrize(
    "change", ["duplicate_target", "duplicate_observed", "empty", "type", "field"]
)
def test_correspondence_rejects_ambiguous_wire_structure(change):
    raw = json.loads(comparison_bytes(_comparison()))
    entry = raw["correspondences"][0]
    if change == "duplicate_target":
        raw["correspondences"].append(entry)
    elif change == "duplicate_observed":
        entry["observed_ids"].append("definition")
    elif change == "empty":
        entry["observed_ids"] = []
    elif change == "type":
        entry["observed_ids"] = [False]
    else:
        entry["guessed_name"] = "run"
    with pytest.raises(ValueError):
        parse_comparison(raw)
