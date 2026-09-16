# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-21: structure measurements are derived from one observation and gate nothing."""

import json
from pathlib import Path

from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.structure import structure_metrics

ROOT = Path(__file__).resolve().parents[1]


def _self_observation():
    artifact = (ROOT / "fixtures/D-self/architecture.json").read_bytes()
    return parse_observation(decode_canonical_model(json.loads(artifact)))


def test_component_metrics_sum_to_the_observation_totals() -> None:
    observation = _self_observation()
    metrics = structure_metrics(observation)
    components = [metric for metric in metrics if metric.level == "component"]
    packages = [metric for metric in metrics if metric.level == "package"]

    modules = len(observation.records("modules") or ())
    assert sum(metric.modules for metric in packages) == modules
    assert sum(metric.modules for metric in components) <= modules
    assert sum(metric.calls for metric in packages) == len(observation.records("calls") or ())
    unresolved = sum(
        1
        for record in observation.records("calls") or ()
        if record.data.get("status") == "unresolved"
    )
    assert sum(metric.unresolved for metric in packages) == unresolved


def test_inner_and_crossing_edges_split_every_module_edge() -> None:
    """An edge between two modules of one scope is inside it; every other edge crosses once."""
    observation = _self_observation()
    packages = [metric for metric in structure_metrics(observation) if metric.level == "package"]
    module_edges = [
        record
        for record in observation.records("dependency_edges") or ()
        if record.data.get("level") == "module"
    ]

    inside = sum(metric.inner_edges for metric in packages)
    crossing = sum(metric.fan_out for metric in packages)
    assert inside + crossing == len(module_edges)
    assert crossing == sum(metric.fan_in for metric in packages)


def test_the_self_observation_names_its_densest_component() -> None:
    """The derivation is what a reader acts on, so it must separate dense from sparse scopes."""
    metrics = {
        metric.scope: metric
        for metric in structure_metrics(_self_observation())
        if metric.level == "component"
    }

    assert metrics["analyzer"].modules > metrics["render"].modules
    assert metrics["analyzer"].inner_edges > metrics["render"].inner_edges
    # ir is the target of every core dependency, so it takes imports and sends none.
    assert metrics["ir"].fan_out == 0
    assert metrics["ir"].fan_in > 0
