# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The own graph boundary has independent, testable UML intent."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from browser_report_support import _browser_page
from test_uml_visual_acceptance import _route_problems

from archkeel.check.uml_compare import compare_graphs
from archkeel.ir.codec import parse_contract
from archkeel.ir.model import Observation, RunResult
from archkeel.ir.source_graph import observed_graph
from archkeel.ir.target_graph import declared_graph
from archkeel.render.html import render_html

ROOT = Path(__file__).parents[1]
TYPE_DEPENDENCIES = {
    ("Signature", "Parameter"),
    ("Entity", "Visibility"),
    ("Entity", "Signature"),
    ("TargetDefinition", "Entity"),
    ("TargetDefinition", "Relationship"),
    ("TargetDefinition", "TargetScope"),
    ("GraphComparison", "GraphAssessment"),
    ("GraphComparison", "EntityCorrespondence"),
    ("ArchitectureGraph", "Entity"),
    ("ArchitectureGraph", "Relationship"),
    ("ArchitectureGraph", "Coverage"),
    ("ArchitectureGraph", "TargetScope"),
    ("ArchitectureReport", "ArchitectureGraph"),
    ("ArchitectureReport", "GraphComparison"),
    ("ArchitectureReport", "ReportFinding"),
    ("ArchitectureReport", "ComponentMembership"),
    ("ArchitectureReport", "DependencyDecisionGap"),
    ("ArchitectureGraph", "ExternalDependencyScopeRule"),
}


def _target():
    path = ROOT / "docs/architecture/contracts/ir.json"
    return declared_graph(parse_contract(json.loads(path.read_bytes())), contract_path=str(path))


def test_own_graph_boundary_declares_fields_methods_and_imports():
    target = _target()
    by_name = {item.qualified_name: item for item in target.entities}
    graph = by_name["archkeel.ir.architecture_graph.ArchitectureGraph"]
    validate = by_name["archkeel.ir.architecture_graph.ArchitectureGraph.validate"]
    origin = by_name["archkeel.ir.architecture_graph.ArchitectureGraph.origin"]
    private = by_name["archkeel.ir.architecture_graph.ArchitectureGraph._validate_entities"]

    assert graph.kind == "class" and "frozen" in graph.modifiers
    assert validate.kind == "method" and validate.parent_id == graph.id
    assert validate.visibility.kind == "public"
    assert validate.signature is not None and validate.signature.returns == "None"
    assert origin.kind == "attribute" and origin.annotation == "OriginKind"
    assert private.visibility.kind == "private"
    assert any(item.kind == "imports" for item in target.relationships)
    assert any(item.kind == "calls" for item in target.relationships)
    assert not target.evidence
    assert all(not item.record_ids and not item.evidence_ids for item in target.entities)


def test_own_class_model_has_independent_type_dependencies(self_observation: Observation):
    target = _target()
    entities = {item.id: item for item in target.entities}
    references = tuple(item for item in target.relationships if item.kind == "references")
    assert {
        (
            entities[item.source_id].qualified_name.rsplit(".", 1)[-1],
            entities[item.target_id].qualified_name.rsplit(".", 1)[-1],
        )
        for item in references
    } == TYPE_DEPENDENCIES
    assert all(
        item.provenance and not item.record_ids and not item.evidence_ids for item in references
    )

    observed = observed_graph(self_observation)
    before = compare_graphs(observed, target)
    assert all(
        any(
            item.subject_id == reference.id
            and item.aspect == "relationship"
            and item.status == "PASS"
            for item in before.assessments
        )
        for reference in references
    )
    wanted = next(
        item
        for item in references
        if entities[item.source_id].qualified_name.endswith(".Signature")
    )
    source = next(
        item.id
        for item in observed.entities
        if item.qualified_name == entities[wanted.source_id].qualified_name
    )
    endpoint = next(
        item.id
        for item in observed.entities
        if item.qualified_name == entities[wanted.target_id].qualified_name
    )
    changed = replace(
        observed,
        relationships=tuple(
            item
            for item in observed.relationships
            if not (
                item.kind == "references"
                and item.source_id == source
                and item.target_id == endpoint
            )
        ),
    )
    after = compare_graphs(changed, target)
    assert any(
        item.subject_id == wanted.id and item.aspect == "relationship" and item.status == "UNKNOWN"
        for item in after.assessments
    )
    certified = replace(
        changed,
        coverage=tuple(
            replace(item, status="complete", reason=None)
            if "references" in item.relationship_kinds
            else item
            for item in changed.coverage
        ),
    )
    assert any(
        item.subject_id == wanted.id and item.aspect == "relationship" and item.status == "FAIL"
        for item in compare_graphs(certified, target).assessments
    )
    assert _target() == target


def test_own_target_does_not_follow_an_observed_method_change(self_observation: Observation):
    target = _target()
    model = self_observation
    observed = observed_graph(model)
    qualified_name = "archkeel.ir.architecture_graph.ArchitectureGraph.validate"
    wanted = next(item for item in target.entities if item.qualified_name == qualified_name)
    actual = next(item for item in observed.entities if item.qualified_name == qualified_name)
    before = compare_graphs(observed, target)
    assert any(
        item.subject_id == wanted.id and item.aspect == "signature" and item.status == "PASS"
        for item in before.assessments
    )

    assert actual.signature is not None
    changed = replace(actual, signature=replace(actual.signature, returns="str"))
    after = compare_graphs(
        replace(
            observed,
            entities=tuple(changed if item.id == actual.id else item for item in observed.entities),
        ),
        target,
    )
    assert any(
        item.subject_id == wanted.id and item.aspect == "signature" and item.status == "FAIL"
        for item in after.assessments
    )
    assert _target() == target


def test_own_target_distinguishes_a_field_from_its_value_binding(self_observation: Observation):
    target = _target()
    model = self_observation
    observed = observed_graph(model)
    name = "archkeel.ir.architecture_graph.Entity.visibility"
    wanted = next(item for item in target.entities if item.qualified_name == name)
    assert {item.kind for item in observed.entities if item.qualified_name == name} == {
        "attribute",
        "binding",
    }
    comparison = compare_graphs(observed, target)
    assert any(
        item.subject_id == wanted.id and item.aspect == "existence" and item.status == "PASS"
        for item in comparison.assessments
    )
    field = next(
        item
        for item in observed.entities
        if item.qualified_name == name and item.kind == "attribute"
    )
    duplicate = replace(field, id=field.id + ":duplicate")
    ambiguous = compare_graphs(replace(observed, entities=observed.entities + (duplicate,)), target)
    assert any(
        item.subject_id == wanted.id
        and item.aspect == "existence"
        and item.status == "UNKNOWN"
        and item.change == "ambiguous"
        for item in ambiguous.assessments
    )
    wrong_kind = compare_graphs(
        replace(
            observed, entities=tuple(item for item in observed.entities if item.id != field.id)
        ),
        target,
    )
    assert any(
        item.subject_id == wanted.id and item.aspect == "kind" and item.status == "FAIL"
        for item in wrong_kind.assessments
    )


def test_own_filtered_calls_keep_clear_routes_and_readable_arrow_endpoints(
    self_observation: Observation,
):
    api = pytest.importorskip("playwright.sync_api")
    model = self_observation
    result = RunResult("report", 0, "PASS", "UNKNOWN", "n/a", coverage=model.coverage)
    errors = []
    playwright, browser, page = _browser_page(
        api,
        render_html(result, model, repository="archkeel", architecture_href=None).decode(),
        width=1550,
        height=1150,
        errors=errors,
    )
    try:
        for label in ("ir", "governance", "architecture_graph"):
            page.locator(f'.flow-nodes [data-label="{label}"]').dblclick()
        graph_id = page.locator('.flow-nodes [data-label="ArchitectureGraph"]').get_attribute(
            "data-uml-id"
        )
        page.locator("#flow-focus").select_option(graph_id)
        page.locator('.flow-legend button[data-relationship-kind="calls"]').click()
        edges = page.locator(".flow-edges .edge")
        assert edges.count() > 10
        assert page.locator(".flow-edges .edge.undecided").count() > 0
        assert not _route_problems(edges)
        assert page.locator(".flow-edges [data-route-warning]").count() == 0
        assert edges.locator(".line").evaluate_all("""lines => lines.every(line => {
          const edge = line.closest('.edge');
          const target = document.querySelector(
            `.flow-nodes [data-uml-id="${edge.dataset.umlTarget}"] .card`);
          const box = target.getBoundingClientRect(), length = line.getTotalLength();
          const matrix = line.getScreenCTM();
          const end = line.getPointAtLength(length), before = line.getPointAtLength(length - 12);
          const point = new DOMPoint(end.x, end.y).matrixTransform(matrix);
          return getComputedStyle(line).markerEnd !== 'none'
            && Math.hypot(before.x-end.x, before.y-end.y) >= 11
            && (Math.min(Math.abs(point.y-box.top), Math.abs(point.y-box.bottom)) < 1
                && point.x >= box.left && point.x <= box.right
              || Math.min(Math.abs(point.x-box.left), Math.abs(point.x-box.right)) < 1
                && point.y >= box.top && point.y <= box.bottom);
        })""")
        assert page.locator(".flow-nodes .label").evaluate_all("""labels => labels.every(label =>
          parseFloat(getComputedStyle(label).fontSize)
            * Math.hypot(label.getScreenCTM().a, label.getScreenCTM().b) >= 12)
        """)
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
def test_own_ir_scope_sizes_the_canvas_after_collecting_shared_evidence(
    view, self_observation: Observation
):
    api = pytest.importorskip("playwright.sync_api")
    model = self_observation
    result = RunResult("report", 0, "PASS", "UNKNOWN", "n/a", coverage=model.coverage)
    errors = []
    playwright, browser, page = _browser_page(
        api,
        render_html(result, model, repository="archkeel", architecture_href=None).decode(),
        errors=errors,
    )
    try:
        page.get_by_role("button", name=view, exact=True).click()
        page.locator('.flow-nodes [data-label="ir"]').dblclick()
        assert not errors
        assert page.locator(".flow-graph").evaluate("""svg => {
          const box = svg.viewBox.baseVal, bounds = svg.querySelector('.flow-viewport').getBBox();
          return bounds.x >= box.x && bounds.y >= box.y
            && bounds.x + bounds.width <= box.x + box.width
            && bounds.y + bounds.height <= box.y + box.height;
        }""")
        page.locator('.flow-nodes [data-label="governance"]').dblclick()
        assert "governance" in page.locator(".flow-breadcrumb").inner_text()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
def test_own_graph_boundary_has_readable_members_and_directed_calls(
    view, self_observation: Observation
):
    api = pytest.importorskip("playwright.sync_api")
    model = self_observation
    result = RunResult("report", 0, "PASS", "UNKNOWN", "n/a", coverage=model.coverage)
    html = render_html(result, model, repository="archkeel", architecture_href=None).decode()
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        page.get_by_role("button", name=view, exact=True).click()
        module = "architecture_graph"
        for label in ("ir", "governance", module, "ArchitectureGraph"):
            page.locator(f'.flow-nodes [data-label="{label}"]').dblclick()
        validate = page.locator('.flow-nodes [data-label="validate"]:not([data-outside])')
        private = page.locator('.flow-nodes [data-label="_validate_entities"]')
        assert "+ (self): None" in validate.locator(".meta").text_content()
        assert private.locator(".meta").text_content().startswith("− (")
        validate.dblclick()
        validate = page.locator('.flow-nodes [data-label="validate"]:not([data-outside])')
        validate.click()
        page.get_by_role("button", name="Fit overview", exact=True).click()
        assert page.locator('.flow-nodes [data-label="origin"]').count() == 0
        private = page.locator('.flow-nodes [data-label="_validate_entities"]')
        assert "related" in private.get_attribute("class")
        identities = set(
            page.locator(".flow-nodes [data-uml-id]").evaluate_all(
                "nodes => nodes.map(node => node.dataset.umlId)"
            )
        )
        edges = page.locator('.flow-edges [data-relationship-kind="calls"]')
        assert edges.count() >= 5
        for edge in edges.all():
            assert edge.get_attribute("data-uml-source") in identities
            assert edge.get_attribute("data-uml-target") in identities
            assert edge.locator(".hit").get_attribute("d") == edge.locator(".line").get_attribute(
                "d"
            )
            assert "flow-arrow" in edge.locator(".line").evaluate(
                "line => getComputedStyle(line).markerEnd"
            )
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["Target", "Diff"])
def test_own_type_dependencies_have_visible_endpoints_and_connected_focus(
    view, self_observation: Observation
):
    api = pytest.importorskip("playwright.sync_api")
    model = self_observation
    result = RunResult("report", 0, "PASS", "UNKNOWN", "n/a", coverage=model.coverage)
    errors = []
    playwright, browser, page = _browser_page(
        api,
        render_html(result, model, repository="archkeel", architecture_href=None).decode(),
        width=1550,
        height=1150,
        errors=errors,
    )
    try:
        page.get_by_role("button", name=view, exact=True).click()
        for label in ("ir", "governance", "architecture_graph"):
            page.locator(f'.flow-nodes [data-label="{label}"]').dblclick()
        edges = page.locator('.flow-edges [data-relationship-kind="references"]')
        assert edges.count() == len(TYPE_DEPENDENCIES)
        page.get_by_role("button", name="Fit overview", exact=True).click()
        assert not _route_problems(page.locator(".flow-edges .edge"))
        identities = set(
            page.locator(".flow-nodes [data-uml-id]").evaluate_all(
                "nodes => nodes.map(node => node.dataset.umlId)"
            )
        )
        for edge in edges.all():
            assert edge.get_attribute("data-uml-source") in identities
            assert edge.get_attribute("data-uml-target") in identities
            assert edge.locator(".hit").get_attribute("d") == edge.locator(".line").get_attribute(
                "d"
            )
            assert "flow-arrow-uml-references" in edge.locator(".line").evaluate(
                "line => getComputedStyle(line).markerEnd"
            )
        page.locator('.flow-nodes [data-label="ArchitectureGraph"]').click()
        page.mouse.move(0, 0)
        for label in ("ArchitectureGraph", "Entity", "Relationship", "Coverage", "TargetScope"):
            assert "related" in page.locator(f'.flow-nodes [data-label="{label}"]').get_attribute(
                "class"
            )
        assert "dim" in page.locator('.flow-nodes [data-label="Parameter"]').get_attribute("class")
        assert page.locator('.flow-legend [data-relationship-kind="references"]').count() == 1
        page.locator('.flow-nodes [data-label="ArchitectureGraph"]').dblclick()
        page.get_by_role("button", name="Fit overview", exact=True).click()
        assert not _route_problems(page.locator(".flow-edges .edge"))
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
def test_member_previews_do_not_squeeze_the_overview_or_change_its_evidence(
    view, self_observation: Observation
):
    api = pytest.importorskip("playwright.sync_api")
    model = self_observation
    result = RunResult("report", 0, "PASS", "UNKNOWN", "n/a", coverage=model.coverage)
    errors = []
    playwright, browser, page = _browser_page(
        api,
        render_html(result, model, repository="archkeel", architecture_href=None).decode(),
        width=1550,
        height=1150,
        errors=errors,
    )
    try:
        payload = page.locator("#flow-data").text_content()
        page.get_by_role("button", name=view, exact=True).click()
        module = "architecture_graph"
        for label in ("ir", "governance", module):
            page.locator(f'.flow-nodes [data-label="{label}"]').dblclick()
        card = page.locator('.flow-nodes [data-label="ArchitectureGraph"]')
        card.click()
        previews = page.get_by_role("button", name="Member previews", exact=True)
        assert previews.get_attribute("aria-pressed") == "false"
        assert card.locator(".uml-member").count() == 0
        assert "12 fields · 7 methods" in card.locator(".meta").text_content()
        details = page.locator(".flow-inspector-content").inner_text()
        assert "+ origin: OriginKind" in details and "+ validate(self): None" in details
        page.get_by_role("button", name="Fit overview", exact=True).click()
        identities = page.locator(".flow-nodes [data-uml-id]").evaluate_all(
            "nodes => nodes.map(node => node.dataset.umlId).sort()"
        )
        relationships = page.locator(".flow-edges [data-uml-id]").evaluate_all(
            "edges => edges.map(edge => edge.dataset.umlId).sort()"
        )
        if view != "As-Is":
            assert len(identities) == 22 and len(relationships) == 22
            assert (
                card.locator(".label").evaluate("""node =>
              parseFloat(getComputedStyle(node).fontSize)
                * Math.hypot(node.getScreenCTM().a, node.getScreenCTM().b)
            """)
                >= 11
            )
            assert not _route_problems(page.locator(".flow-edges .edge"))
        previews.focus()
        previews.press("Space")
        assert previews.get_attribute("aria-pressed") == "true"
        assert card.locator(".uml-member").count() > 0
        if view != "As-Is":
            assert not _route_problems(page.locator(".flow-edges .edge"))
        assert (
            page.locator(".flow-nodes [data-uml-id]").evaluate_all(
                "nodes => nodes.map(node => node.dataset.umlId).sort()"
            )
            == identities
        )
        assert (
            page.locator(".flow-edges [data-uml-id]").evaluate_all(
                "edges => edges.map(edge => edge.dataset.umlId).sort()"
            )
            == relationships
        )
        assert page.locator("#flow-data").text_content() == payload
        previews.press("Space")
        card.dblclick()
        assert page.locator('.flow-nodes [data-label="origin"]').count() >= 1
        validate = page.locator('.flow-nodes [data-label="validate"]')
        assert "+ (self): None" in validate.locator(".meta").text_content()
        page.locator(".flow-back").click()
        assert card.locator(".uml-member").count() == 0
        assert (
            page.locator(".flow-nodes [data-uml-id]").evaluate_all(
                "nodes => nodes.map(node => node.dataset.umlId).sort()"
            )
            == identities
        )
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
def test_own_class_overview_keeps_distinct_routes_and_type_cues(
    view, self_observation: Observation
):
    api = pytest.importorskip("playwright.sync_api")
    model = self_observation
    result = RunResult("report", 0, "PASS", "UNKNOWN", "n/a", coverage=model.coverage)
    errors = []
    playwright, browser, page = _browser_page(
        api,
        render_html(result, model, repository="archkeel", architecture_href=None).decode(),
        width=1550,
        height=1150,
        errors=errors,
    )
    try:
        page.get_by_role("button", name=view, exact=True).click()
        module = "architecture_graph"
        for label in ("ir", "governance", module):
            page.locator(f'.flow-nodes [data-label="{label}"]').dblclick()
        complete = page.locator("#flow-data").text_content()
        page.get_by_label("Element kind", exact=True).select_option("class")
        cards = page.locator(".flow-nodes [data-uml-id]")
        assert cards.count() >= 12
        assert cards.evaluate_all('nodes => nodes.every(node => node.dataset.umlKind === "class")')
        assert cards.evaluate_all(
            "nodes => nodes.every(node => node.querySelector('.uml-icon rect'))"
        )
        edges = page.locator(".flow-edges .edge")
        assert edges.count() >= 12
        assert not _route_problems(edges)
        assert page.locator(".flow-edges [data-route-warning]").count() == 0
        assert page.locator("#flow-data").text_content() == complete
        assert not errors
    finally:
        browser.close()
        playwright.stop()
