# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-21: structure measurements are derived from one observation and gate nothing."""

from dataclasses import replace

from archkeel.ir.model import Observation
from archkeel.ir.structure import oversized_insides, structure_metrics


def test_component_metrics_sum_to_the_observation_totals(self_observation: Observation) -> None:
    observation = self_observation
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


def test_inner_and_crossing_edges_split_every_module_edge(self_observation: Observation) -> None:
    """An edge between two modules of one scope is inside it; every other edge crosses once."""
    observation = self_observation
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


def test_the_self_observation_names_its_densest_component(self_observation: Observation) -> None:
    """The derivation is what a reader acts on, so it must separate dense from sparse scopes."""
    metrics = {
        metric.scope: metric
        for metric in structure_metrics(self_observation)
        if metric.level == "component"
    }

    assert metrics["analyzer"].modules > metrics["render"].modules
    assert metrics["analyzer"].inner_edges > metrics["render"].inner_edges
    # ir is the target of every core dependency, so it takes imports and sends none.
    assert metrics["ir"].fan_out == 0
    assert metrics["ir"].fan_in > 0


def test_the_claim_names_exactly_the_components_larger_than_their_level(
    self_observation: Observation,
) -> None:
    """AD-33: the threshold is the top level itself, so both directions must hold."""
    observation = self_observation
    claim = oversized_insides(observation)
    named = {item.scope for item in claim.candidates}

    assert claim.status == "SUPPORTED"
    for metric in structure_metrics(observation):
        if metric.level != "component":
            continue
        exceeds = metric.modules > claim.components or metric.inner_edges > claim.component_edges
        assert (metric.scope in named) == exceeds
    # The decision log publishes `check` as an inside worth a level of its own (AD-20).
    assert "check" in named


def test_the_claim_is_unknown_without_the_edge_signal(self_observation: Observation) -> None:
    """Comparing against zero component edges would name every component that has one."""
    observation = self_observation
    without_edges = replace(
        observation,
        sections=tuple(item for item in observation.sections if item.name != "dependency_edges"),
    )

    claim = oversized_insides(without_edges)

    assert claim.status == "UNKNOWN"
    assert claim.candidates == ()
