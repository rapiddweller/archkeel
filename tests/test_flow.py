# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Unit tests for the AD-10 component flow derivation."""

import json
from pathlib import Path

from test_architecture_demo import CONFIG, _prepare_repo

from archkeel.analyzer import observe
from archkeel.check.report import run_report
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.render.flow import FlowEdge, build_flow
from fixtures.architecture_demo import CATALOG
from fixtures.demo_catalog_support import contract_without_rule

_TOUR = next(variant for variant in CATALOG if variant.id == "tour")
_CLEAN = next(variant for variant in CATALOG if variant.id == "clean")

# Every ordered component pair with at least one observed import in the tour sample, and the
# rule ids that pair's edge must carry (empty when the pair conforms). Derived by running the
# tour fixture and reading its violations and dependency_edges directly (see AD-10 task notes):
# EXTERNAL-JSON-STORE, ASSIGNMENT-COMPLETE and the CONSTRUCT-* rules name a single module or an
# external dependency, never a component pair, so they never attach to an edge.
_TOUR_EDGES = {
    ("app", "model"): (3, ()),
    ("app", "store"): (6, ("DEP-APP-NO-STORE-BACKEND", "DEP-APP-NO-STORE-SQLITE")),
    ("cli", "app"): (1, ()),
    ("cli", "render"): (2, ("INTERFACE-BOUNDARY",)),
    ("model", "render"): (1, ("COMPONENT-NO-CYCLES", "DEP-MODEL-NO-RENDER")),
    ("render", "model"): (1, ("COMPONENT-NO-CYCLES",)),
    ("render", "store"): (1, ("COMPONENT-NO-CYCLES", "DEP-RENDER-NO-STORE")),
    ("store", "model"): (3, ("COMPONENT-NO-CYCLES", "DEP-STORE-NO-MONEY")),
}


def _observation(tmp_path: Path, files: dict[str, str | None]):
    root = _prepare_repo(tmp_path, files)
    _, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    return parse_observation(decode_canonical_model(json.loads(architecture)))


def test_flow_derives_components_and_weighted_edges(tmp_path: Path) -> None:
    flow = build_flow(_observation(tmp_path, dict(_TOUR.files)))

    assert [component.label for component in flow.components] == [
        "app",
        "cli",
        "model",
        "render",
        "store",
    ]
    store = next(component for component in flow.components if component.label == "store")
    assert "shop.store.repository" in store.modules
    assert store.public is None or isinstance(store.public, tuple)

    actual_edges = {
        (edge.source, edge.target): (edge.import_sites, edge.rule_ids) for edge in flow.edges
    }
    assert actual_edges == _TOUR_EDGES
    assert {edge.state for edge in flow.edges if edge.rule_ids} == {"violation"}
    assert {edge.state for edge in flow.edges if not edge.rule_ids} == {"conforms"}


def test_flow_violated_edges_carry_only_pair_scoped_rule_ids(tmp_path: Path) -> None:
    flow = build_flow(_observation(tmp_path, dict(_TOUR.files)))

    violated_rule_ids = {rule_id for edge in flow.edges for rule_id in edge.rule_ids}
    assert violated_rule_ids == {
        "COMPONENT-NO-CYCLES",
        "DEP-APP-NO-STORE-BACKEND",
        "DEP-APP-NO-STORE-SQLITE",
        "DEP-MODEL-NO-RENDER",
        "DEP-RENDER-NO-STORE",
        "DEP-STORE-NO-MONEY",
        "INTERFACE-BOUNDARY",
    }
    # Single-subject and unowned-target rules never name a component pair.
    assert "ASSIGNMENT-COMPLETE" not in violated_rule_ids
    assert "EXTERNAL-JSON-STORE" not in violated_rule_ids
    assert "CONSTRUCT-NO-ASSERT" not in violated_rule_ids


def test_flow_clean_sample_has_no_violated_edges(tmp_path: Path) -> None:
    flow = build_flow(_observation(tmp_path, dict(_CLEAN.files)))

    assert flow.edges
    assert all(edge.rule_ids == () for edge in flow.edges)


def test_flow_marks_an_observed_edge_undecided_when_its_allowed_rule_is_removed(
    tmp_path: Path,
) -> None:
    """AD-15: an observed pair with neither an allowed nor a forbidden rule is undecided,
    from the same `open_decisions` derivation as validation's `decision.open` diagnostic."""
    files = {
        **dict(_TOUR.files),
        "architecture-contract.json": contract_without_rule("DEP-APP-ALLOWS-MODEL"),
    }
    flow = build_flow(_observation(tmp_path, files))

    edge = next(edge for edge in flow.edges if (edge.source, edge.target) == ("app", "model"))
    assert edge.state == "undecided"
    assert edge.rule_ids == ()


def test_flow_keeps_violation_state_for_an_edge_that_is_also_undecided(tmp_path: Path) -> None:
    """A rule violation always outranks an undecided pair on the same edge."""
    files = {
        **dict(_TOUR.files),
        "architecture-contract.json": contract_without_rule("DEP-APP-ALLOWS-STORE"),
    }
    flow = build_flow(_observation(tmp_path, files))

    edge = next(edge for edge in flow.edges if (edge.source, edge.target) == ("app", "store"))
    assert edge.state == "violation"
    assert edge.rule_ids == ("DEP-APP-NO-STORE-BACKEND", "DEP-APP-NO-STORE-SQLITE")


def test_flow_edge_is_a_frozen_dataclass_value() -> None:
    edge = FlowEdge("a", "b", 1, (), "conforms")
    assert edge == FlowEdge("a", "b", 1, (), "conforms")


def test_flow_carries_the_imports_inside_one_component(tmp_path: Path) -> None:
    """AD-24: the inside of a component is observed and travels with the view, undecided."""
    flow = build_flow(_observation(tmp_path, dict(_TOUR.files)))
    store = next(component for component in flow.components if component.label == "store")

    inner = {(edge.source, edge.target) for edge in store.inner_edges}
    assert ("shop.store", "shop.store.repository") in inner
    # Every inner edge stays inside the component; a crossing edge belongs to flow.edges.
    assert all(source in store.modules and target in store.modules for source, target in inner)
    assert all(edge.import_sites > 0 for edge in store.inner_edges)
    crossing = {(edge.source, edge.target) for edge in flow.edges}
    assert not inner & crossing
