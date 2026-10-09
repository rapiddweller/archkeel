# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The own graph boundary has independent, testable UML intent."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from browser_report_support import _browser_page
from test_uml_rendering import _wait_for_layout
from test_uml_visual_acceptance import _route_problems

from archkeel.check.uml_compare import compare_graphs
from archkeel.ir.codec import parse_contract
from archkeel.ir.model import Observation, RunResult
from archkeel.ir.source_graph import observed_graph
from archkeel.ir.target_graph import declared_graph
from archkeel.render.html import render_html

ROOT = Path(__file__).parents[1]
TYPE_DEPENDENCIES = {
    ("ComponentIntent", "ComponentRole"),
    ("TargetDefinition", "GraphSchemaVersion"),
    ("ArchitectureGraph", "GraphSchemaVersion"),
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


def test_own_target_declares_the_component_role_enum_literals():
    target = _target()
    role = next(
        e
        for e in target.entities
        if e.qualified_name == "archkeel.ir.architecture_graph.ComponentRole"
    )
    assert role.kind == "enum"
    assert {
        e.qualified_name.rsplit(".", 1)[-1]
        for e in target.entities
        if e.parent_id == role.id and e.kind == "enum_literal"
    } == {"COMPONENT", "INTERFACE", "CONTRACT", "PROJECTION", "FOUNDATION"}
    assert target.schema_version == "1.1.0"


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
    references = tuple(
        item
        for item in target.relationships
        if item.kind == "references"
        and entities[item.source_id].qualified_name.startswith("archkeel.ir.architecture_graph.")
    )
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
    page.context.new_cdp_session(page).send("Emulation.setCPUThrottlingRate", {"rate": 4})
    try:
        for label in ("ir", "governance", "architecture_graph"):
            page.locator(f'.flow-nodes [data-label="{label}"]').dblclick(timeout=30000)
            _wait_for_layout(page)
        graph_id = page.locator('.flow-nodes [data-label="ArchitectureGraph"]').get_attribute(
            "data-uml-id"
        )
        page.locator(".flow-filters > summary").click()
        page.locator("#flow-focus").select_option(graph_id)
        page.locator(".flow-filters > summary").click()
        page.locator('.flow-legend button[data-relationship-kind="calls"]').click()
        _wait_for_layout(page)
        edges = page.locator(".flow-edges .edge")
        assert edges.count() > 10
        assert page.locator(".flow-edges .edge.undecided").count() > 0
        problems = _route_problems(edges)
        if problems:
            output = ROOT / "test-artifacts/report-browser"
            output.mkdir(parents=True, exist_ok=True)
            geometry = page.evaluate("""() => ({
              viewport: {width: innerWidth, height: innerHeight},
              fonts: document.fonts.status,
              transform: document.querySelector('.flow-viewport').getAttribute('transform'),
              cards: [...document.querySelectorAll('.flow-nodes > g')].map(node => ({
                id: node.dataset.umlId, transform: node.getAttribute('transform'),
                bounds: node.getBoundingClientRect().toJSON(),
                font: getComputedStyle(node.querySelector('text') || node).font
              })),
              routes: [...document.querySelectorAll('.flow-edges .edge')].map(edge => ({
                id: edge.dataset.umlId, path: edge.querySelector('.line').getAttribute('d')
              }))
            })""")
            geometry.update(browser=browser.version, problems=problems)
            (output / "own-filtered-calls.json").write_text(json.dumps(geometry, indent=2))
            page.screenshot(path=str(output / "own-filtered-calls.png"), full_page=True)
        assert not problems
        assert page.locator(".flow-edges [data-route-warning]").count() == 0
        endpoint_problems = edges.locator(".line").evaluate_all("""lines => lines.flatMap(line => {
          const edge = line.closest('.edge');
          const target = document.querySelector(
            `.flow-nodes [data-uml-id="${edge.dataset.umlTarget}"] .card`);
          const box = target.getBoundingClientRect(), length = line.getTotalLength();
          const matrix = line.getScreenCTM();
          const end = line.getPointAtLength(length), before = line.getPointAtLength(length - 12);
          const point = new DOMPoint(end.x, end.y).matrixTransform(matrix);
          const valid = getComputedStyle(line).markerEnd !== 'none'
            && Math.hypot(before.x-end.x, before.y-end.y) >= 11
            && (Math.min(Math.abs(point.y-box.top), Math.abs(point.y-box.bottom)) < 1
                && point.x >= box.left && point.x <= box.right
              || Math.min(Math.abs(point.x-box.left), Math.abs(point.x-box.right)) < 1
                && point.y >= box.top && point.y <= box.bottom);
          return valid ? [] : [{id: edge.dataset.umlId, targetId: edge.dataset.umlTarget,
            endpoint: {x: point.x, y: point.y}, target: box.toJSON(),
            delta: {left: point.x-box.left, right: point.x-box.right,
              top: point.y-box.top, bottom: point.y-box.bottom},
            pathEnd: {x: end.x, y: end.y}, transform: line.getAttribute('transform'),
            marker: getComputedStyle(line).markerEnd, d: line.getAttribute('d')}];
        })""")
        if endpoint_problems:
            output = ROOT / "test-artifacts/report-browser"
            output.mkdir(parents=True, exist_ok=True)
            (output / "own-filtered-call-endpoints.json").write_text(
                json.dumps(endpoint_problems, indent=2)
            )
            page.screenshot(path=str(output / "own-filtered-call-endpoints.png"), full_page=True)
        assert endpoint_problems == [], json.dumps(endpoint_problems, indent=2)
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
        _wait_for_layout(page)
        page.locator('.flow-nodes [data-label="ir"]').dblclick()
        _wait_for_layout(page)
        assert not errors
        assert page.locator(".flow-graph").evaluate("""svg => {
          const box = svg.viewBox.baseVal, bounds = svg.querySelector('.flow-viewport').getBBox();
          return bounds.x >= box.x && bounds.y >= box.y
            && bounds.x + bounds.width <= box.x + box.width
            && bounds.y + bounds.height <= box.y + box.height;
        }""")
        page.locator('.flow-nodes [data-label="governance"]').dblclick()
        _wait_for_layout(page)
        assert "governance" in page.locator(".flow-breadcrumb").inner_text()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_pointer_selection_keeps_card_under_second_tap(self_observation: Observation):
    api = pytest.importorskip("playwright.sync_api")
    model = self_observation
    result = RunResult("report", 0, "PASS", "UNKNOWN", "n/a", coverage=model.coverage)
    playwright, browser, page = _browser_page(
        api, render_html(result, model, repository="archkeel", architecture_href=None).decode()
    )
    try:
        page.get_by_role("button", name="Diff", exact=True).click()
        _wait_for_layout(page)
        card = page.locator('.flow-nodes [data-label="ir"]')
        card.scroll_into_view_if_needed()
        bounds = card.bounding_box()
        assert bounds is not None
        canvas = page.locator(".flow-canvas")
        scroll_before = canvas.evaluate("node => [node.scrollLeft, node.scrollTop]")
        point = (bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
        page.mouse.click(*point)
        after = card.bounding_box()
        assert after is not None
        assert after["x"] <= point[0] <= after["x"] + after["width"]
        assert after["y"] <= point[1] <= after["y"] + after["height"]
        assert canvas.evaluate("node => [node.scrollLeft, node.scrollTop]") == scroll_before
        page.mouse.click(*point)
        _wait_for_layout(page)
        assert "ir [component]" in page.locator(".flow-breadcrumb").inner_text()
        assert page.locator('.flow-nodes [data-label="governance"]').count() == 1
    finally:
        browser.close()
        playwright.stop()


def test_zoom_cancels_pending_pointer_reveal(self_observation: Observation):
    api = pytest.importorskip("playwright.sync_api")
    model = self_observation
    result = RunResult("report", 0, "PASS", "UNKNOWN", "n/a", coverage=model.coverage)
    html = render_html(result, model, repository="archkeel", architecture_href=None).decode()
    playwright, browser, page = _browser_page(api, html, width=375, height=1000)
    try:
        page.get_by_role("button", name="As-Is", exact=True).click()
        _wait_for_layout(page)
        page.get_by_role("button", name="Fit overview", exact=True).click()
        cards = page.locator(".flow-nodes [data-uml-id]")
        card = cards.nth(max(range(cards.count()), key=lambda i: cards.nth(i).bounding_box()["x"]))
        card.scroll_into_view_if_needed()
        bounds = card.bounding_box()
        assert bounds is not None

        page.clock.install()
        page.mouse.click(bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
        assert page.locator(".flow-details-toggle").get_attribute("aria-expanded") == "true"
        canvas = page.locator(".flow-canvas")
        zoom = page.locator(".flow-zoom-value")
        zoom_before = zoom.inner_text()
        page.get_by_role("button", name="Zoom in", exact=True).click()
        zoom_after = zoom.inner_text()
        assert zoom_after != zoom_before

        scroll_after_action = canvas.evaluate("node => [node.scrollLeft, node.scrollTop]")
        page.clock.fast_forward(501)
        assert canvas.evaluate("node => [node.scrollLeft, node.scrollTop]") == scroll_after_action
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
        _wait_for_layout(page)
        module = "architecture_graph"
        for label in ("ir", "governance", module, "ArchitectureGraph"):
            page.locator(f'.flow-nodes [data-label="{label}"]').dblclick()
            _wait_for_layout(page)
        validate = page.locator('.flow-nodes [data-label="validate"]:not([data-outside])')
        private = page.locator('.flow-nodes [data-label="_validate_entities"]')
        assert "+ (self): None" in validate.locator(".meta").text_content()
        assert private.locator(".meta").text_content().startswith("− (")
        validate.dblclick()
        _wait_for_layout(page)
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
        _wait_for_layout(page)
        for label in ("ir", "governance", "architecture_graph"):
            page.locator(f'.flow-nodes [data-label="{label}"]').dblclick()
            _wait_for_layout(page)
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
        _wait_for_layout(page)
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
        _wait_for_layout(page)
        module = "architecture_graph"
        for label in ("ir", "governance", module):
            page.locator(f'.flow-nodes [data-label="{label}"]').dblclick()
            _wait_for_layout(page)
        card = page.locator('.flow-nodes [data-label="ArchitectureGraph"]')
        card.click()
        previews = page.get_by_role("button", name="Member previews", exact=True)
        assert previews.get_attribute("aria-pressed") == "false"
        assert card.locator(".uml-member").count() == 0
        expected_methods = 8 if view == "As-Is" else 7
        assert f"12 fields · {expected_methods} methods" in card.locator(".meta").text_content()
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
            assert {"ComponentRole", "ComponentIntent", "GraphSchemaVersion"} <= set(
                page.locator(".flow-nodes [data-uml-id]").evaluate_all(
                    "nodes => nodes.map(node => node.dataset.label)"
                )
            )
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
        _wait_for_layout(page)
        assert previews.get_attribute("aria-pressed") == "true"
        assert card.locator(".uml-member").count() > 0
        assert card.locator(".uml-member").evaluate_all("""nodes => nodes.every(node =>
          parseFloat(getComputedStyle(node).fontSize)
            * Math.hypot(node.getScreenCTM().a, node.getScreenCTM().b) >= 11)
        """)
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
        _wait_for_layout(page)
        card.dblclick()
        _wait_for_layout(page)
        assert page.locator('.flow-nodes [data-label="origin"]').count() >= 1
        validate = page.locator('.flow-nodes [data-label="validate"]')
        assert "+ (self): None" in validate.locator(".meta").text_content()
        page.locator(".flow-back").click()
        _wait_for_layout(page)
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
        page.locator(".flow-filters > summary").click()
        page.get_by_label("Element kind", exact=True).select_option("class")
        page.locator(".flow-filters > summary").click()
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


@pytest.mark.parametrize("width", [1600, 1300])
def test_own_ports_context_relationship_routes_keep_sites(width, self_observation: Observation):
    api = pytest.importorskip("playwright.sync_api")
    model = self_observation
    result = RunResult("report", 0, "PASS", "UNKNOWN", "n/a", coverage=model.coverage)
    errors = []
    playwright, browser, page = _browser_page(
        api,
        render_html(result, model, repository="archkeel", architecture_href=None).decode(),
        width=width,
        height=1050,
        errors=errors,
    )
    try:
        for label in ("check", "inputs", "ports"):
            page.locator(f'.flow-nodes [data-label="{label}"]').dblclick()
        payload = page.locator("#flow-data").text_content()
        page.locator('.flow-nodes [data-label="SourceCollector"]').click()
        edges = page.locator(".flow-edges .edge")
        for kind in ("imports", "references"):
            page.locator(f'.flow-legend button[data-relationship-kind="{kind}"]').click()
            assert page.locator(f'.flow-edges [data-relationship-kind="{kind}"]').count() > 0
            assert not _route_problems(edges)
            assert edges.evaluate_all("""edges => edges.every(edge =>
              edge.querySelector('.line').getAttribute('d')
                === edge.querySelector('.hit').getAttribute('d'))""")
        assert page.locator("#flow-data").text_content() == payload
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
def test_own_protocol_settings_use_the_same_uml_cards_and_field_navigation(
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
        page.locator('.flow-nodes [data-label="ir"]').dblclick()
        boundary = page.locator('.flow-nodes [data-label="protocol"]')
        assert boundary.get_attribute("data-uml-kind") == "component"
        assert "Architecture boundary" in boundary.text_content()
        boundary_color = boundary.locator(".stereotype").evaluate(
            "node => getComputedStyle(node).fill"
        )
        boundary.dblclick()
        module = page.locator('.flow-nodes [data-label="protocol"]')
        assert module.get_attribute("data-uml-kind") == "module"
        assert ("protocol.py" if view == "As-Is" else "File not declared") in module.text_content()
        assert "protocol [component]" in page.locator(".flow-breadcrumb").inner_text()
        module.press("Space")
        if page.locator(".flow-details-toggle").get_attribute("aria-expanded") != "true":
            page.locator(".flow-details-toggle").click()
        details = page.locator(".flow-inspector-content").inner_text()
        assert "Python module" in details and "View group" in details
        if view == "As-Is":
            assert "src/archkeel/ir/protocol.py" in details
            assert "Code namespace" in details and "archkeel.ir [namespace group]" in details
        else:
            assert "Not declared" in details
        module_color = module.locator(".stereotype").evaluate("node => getComputedStyle(node).fill")
        assert boundary_color != module_color
        module.dblclick()
        assert "protocol [module]" in page.locator(".flow-breadcrumb").inner_text()
        for name in ("PythonSettings", "DartSettings", "TypeScriptSettings"):
            card = page.locator(f'.flow-nodes [data-label="{name}"]')
            assert card.get_attribute("data-uml-kind") == "class"
            assert "«class»" in card.text_content()
        assert (
            page.locator('.flow-nodes [data-label="ResolverSettings"]').get_attribute(
                "data-uml-kind"
            )
            == "type_alias"
        )
        assert (
            page.locator('.flow-nodes [data-label="PROTOCOL_VERSION"]').get_attribute(
                "data-uml-kind"
            )
            == "constant"
        )
        page.locator('.flow-nodes [data-label="TypeScriptSettings"]').dblclick()
        language = page.locator('.flow-nodes [data-label="language"][data-uml-kind="attribute"]')
        assert "Literal['typescript']" in language.text_content()
        assert (
            page.locator('.flow-nodes [data-label="tsconfig"]').get_attribute("data-uml-kind")
            == "attribute"
        )
        language.press("Space")
        if page.locator(".flow-details-toggle").get_attribute("aria-expanded") != "true":
            page.locator(".flow-details-toggle").click()
        details = page.locator(".flow-inspector-content").inner_text()
        assert "public" in details and "Literal['typescript']" in details
        heading = page.locator(".flow-inspector-content h2")
        assert heading.inner_text() == "language"
        qualified = page.locator(".flow-qualified-name")
        assert qualified.text_content() == "archkeel.ir.protocol.TypeScriptSettings.language"
        assert qualified.locator("wbr").count() == 4
        assert heading.evaluate(
            "node => node.getBoundingClientRect().height <= "
            "parseFloat(getComputedStyle(node).lineHeight) + 1"
        )
        excerpts = page.locator(".flow-inspector-content pre").all_text_contents()
        if view != "Target":
            assert excerpts
        page.set_viewport_size({"width": 1080, "height": 900})
        assert page.locator(".flow-inspector").evaluate(
            "node => node.scrollWidth <= node.clientWidth + 1"
        )
        assert page.locator(".flow-inspector-content pre").all_text_contents() == excerpts
        assert page.locator("#flow-data").text_content() == payload
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Diff"])
def test_own_dense_scenes_remain_actionable_at_reduced_cpu(view, self_observation: Observation):
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
        page.context.new_cdp_session(page).send("Emulation.setCPUThrottlingRate", {"rate": 2})
        payload = page.locator("#flow-data").text_content()
        page.get_by_role("button", name=view, exact=True).click()
        _wait_for_layout(page)
        for depth, label in enumerate(("ir", "governance", "architecture_graph"), start=2):
            page.locator(f'.flow-nodes [data-label="{label}"]').dblclick()
            _wait_for_layout(page)
            assert page.locator(".flow-breadcrumb button").count() == depth
        nodes = page.locator(".flow-nodes [data-uml-id]")
        edges = page.locator(".flow-edges [data-uml-id]")
        identities = nodes.evaluate_all("nodes => nodes.map(node => node.dataset.umlId).sort()")
        connections = edges.evaluate_all("edges => edges.map(edge => edge.dataset.umlId).sort()")
        previews = page.get_by_role("button", name="Member previews", exact=True)
        previews.focus()
        previews.press("Space")
        _wait_for_layout(page)
        assert previews.get_attribute("aria-pressed") == "true"
        assert (
            nodes.evaluate_all("nodes => nodes.map(node => node.dataset.umlId).sort()")
            == identities
        )
        assert (
            edges.evaluate_all("edges => edges.map(edge => edge.dataset.umlId).sort()")
            == connections
        )
        assert edges.evaluate_all("""edges => edges.every(edge =>
          edge.querySelector('.line').getAttribute('d') ===
          edge.querySelector('.hit').getAttribute('d'))""")
        page.locator(".flow-back").click()
        _wait_for_layout(page)
        assert "architecture_graph" not in page.locator(".flow-breadcrumb").inner_text()
        assert page.locator("#flow-data").text_content() == payload
        assert not errors
    finally:
        browser.close()
        playwright.stop()
