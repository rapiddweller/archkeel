# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""One report boundary retains independent graphs and verified Core receipts."""

import json

import pytest
from test_target_graph import _contract

from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    ArchitectureReport,
    GraphComparison,
)
from archkeel.ir.codec import parse_contract
from archkeel.ir.graph_codec import parse_report, report_bytes
from archkeel.ir.target_graph import declared_graph


@pytest.mark.parametrize("observed,target", [(True, False), (False, True), (False, False)])
def test_report_serialization_retains_unavailable_graphs(observed, target):
    report = ArchitectureReport(
        ArchitectureGraph("observed") if observed else None,
        ArchitectureGraph("declared") if target else None,
        unavailable=None if observed else "Source facts are absent.",
    )
    wire = json.loads(report_bytes(report))
    assert (wire["observed"] is not None) is observed
    assert (wire["target"] is not None) is target
    assert wire["comparison"] is None
    assert wire["unavailable"] == report.unavailable
    assert parse_report(wire) == report


@pytest.mark.parametrize("layer", [None, "Cœur"])
def test_report_serialization_preserves_layer_presence(layer):
    raw = _contract()
    raw["schema_version"] = "2.3.0"
    if layer is not None:
        raw["components"][0]["layer"] = layer
    report = ArchitectureReport(
        ArchitectureGraph("observed"),
        declared_graph(parse_contract(raw)),
        schema_version="1.2.0" if layer is not None else "1.0.0",
    )
    wire = json.loads(report_bytes(report))
    intent = wire["target"]["component_intents"][0]
    assert ("layer" in intent) is (layer is not None)
    if layer is not None:
        assert intent["layer"] == layer
        assert layer.encode() in report_bytes(report)
    assert parse_report(wire) == report


@pytest.mark.parametrize(
    "report,reason",
    [
        (ArchitectureReport(ArchitectureGraph("declared"), None), "observed origin"),
        (
            ArchitectureReport(ArchitectureGraph("observed"), ArchitectureGraph("observed")),
            "declared origin",
        ),
        (ArchitectureReport(None, None), "reason"),
        (
            ArchitectureReport(
                None, None, GraphComparison("UNKNOWN"), unavailable="Source facts are absent."
            ),
            "both source and Target",
        ),
    ],
)
def test_report_serialization_keeps_full_validation(report, reason):
    with pytest.raises(ValueError, match=reason):
        report_bytes(report)


def test_report_rejects_swapped_origins_and_comparison_without_source():
    with pytest.raises(ValueError, match="observed origin"):
        ArchitectureReport(ArchitectureGraph("declared"), None).validate()
    with pytest.raises(ValueError, match="declared origin"):
        ArchitectureReport(ArchitectureGraph("observed"), ArchitectureGraph("observed")).validate()
    with pytest.raises(ValueError, match="reason"):
        ArchitectureReport(None, None).validate()
    with pytest.raises(ValueError, match="both source and Target"):
        ArchitectureReport(
            None, None, GraphComparison("UNKNOWN"), unavailable="Source facts are absent."
        ).validate()
