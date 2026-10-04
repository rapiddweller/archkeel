# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""UML type cues and a small call graph must be readable in every view."""

import pytest
from browser_report_support import _browser_page, _tour_report_page
from test_uml_rendering import _open_module, _uml_report

from archkeel.ir.architecture_graph import Entity, Parameter, Relationship, Signature

HELPERS = (
    "_validate_entities",
    "_validate_physical_intent",
    "_validate_public_api",
    "_validate_relationships",
    "_validate_scopes",
)


def _route_problems(edges):
    return edges.evaluate_all("""edges => {
      const routes = edges.map(edge => {
        const line = edge.querySelector('.line'), matrix = line.getScreenCTM();
        const scale = Math.hypot(matrix.a, matrix.b), step = 2 / scale;
        const points = [];
        for (let at = 0; at <= line.getTotalLength(); at += step) {
          const p = line.getPointAtLength(at);
          points.push(new DOMPoint(p.x, p.y).matrixTransform(matrix));
        }
        return {id: edge.dataset.umlId, points};
      });
      const cards = [...document.querySelectorAll('.flow-nodes .card')]
        .map(card => card.getBoundingClientRect());
      const overlaps = routes.filter(route => route.points.some(p => cards.some(box =>
        p.x > box.left + 1 && p.x < box.right - 1
        && p.y > box.top + 1 && p.y < box.bottom - 1)))
        .map(route => 'card intersection: ' + route.id);
      routes.forEach((route, index) => {
        for (const other of routes.slice(index + 1)) {
          let stretch = 0;
          for (const p of route.points) {
            stretch = other.points.some(q => Math.hypot(p.x-q.x, p.y-q.y) < 3)
              ? stretch + 2 : 0;
            if (stretch >= 14) {
              overlaps.push([route.id, other.id]);
              break;
            }
          }
        }
      });
      return overlaps;
    }""")


@pytest.mark.parametrize(
    "view,neighbors,connections",
    [
        ("As-Is", ["Base", "Client", "core"], 2),
        ("Target", ["Base", "Client"], 1),
        ("Diff", ["Base", "Client"], 1),
    ],
)
def test_uml_focus_keeps_direct_neighbors_and_restores_the_complete_scope(
    tmp_path, view, neighbors, connections
):
    context = {
        "presence": "planned",
        "provenance": ("docs/target.md",),
        "responsibilities": ("Remain separate from the focused classifier.",),
    }
    html, _ = _uml_report(
        tmp_path,
        mismatch=True,
        extra_source="".join(f"class Separate{i}: pass\n" for i in range(24)),
        extra_target_entities=tuple(
            Entity(
                f"separate-{i}", "class", f"sample.core.Separate{i}", "python", "module", **context
            )
            for i in range(24)
        ),
    )
    api = pytest.importorskip("playwright.sync_api")
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        _open_module(page, view)
        payload = page.locator("#flow-data").text_content()
        nodes = page.locator(".flow-nodes [data-uml-id]")
        edges = page.locator(".flow-edges [data-uml-id]")
        all_nodes = nodes.evaluate_all("nodes => nodes.map(node => node.dataset.umlId).sort()")
        all_edges = edges.evaluate_all("edges => edges.map(edge => edge.dataset.umlId).sort()")
        base = page.locator('.flow-nodes [data-label="Base"]')
        base_id = base.get_attribute("data-uml-id")
        focus = page.locator("#flow-focus")
        assert focus.is_visible()
        focus.select_option(base_id)
        assert (
            nodes.evaluate_all("nodes => nodes.map(node => node.dataset.label).sort()") == neighbors
        )
        assert edges.count() == connections
        inheritance = page.locator('.flow-edges [data-relationship-kind="inherits"]')
        assert inheritance.count() == 1
        assert inheritance.get_attribute("data-uml-target") == base_id
        assert f"{len(neighbors)} of " in page.locator(".flow-filter-status").inner_text()
        assert (
            f"of {focus.locator('option').count() - 1} elements"
            in page.locator(".flow-filter-status").inner_text()
        )
        assert (
            base.locator(".label").evaluate("""node =>
          parseFloat(getComputedStyle(node).fontSize)
            * Math.hypot(node.getScreenCTM().a, node.getScreenCTM().b)
        """)
            >= 12
        )
        assert not _route_problems(edges)
        if view == "Diff":
            assert "Core: FAIL" in page.locator(".flow-legend").inner_text()
        client = page.locator('.flow-nodes [data-label="Client"]')
        before = client.get_attribute("transform")
        client.hover()
        assert client.get_attribute("transform") == before
        client.dblclick()
        assert page.locator('.flow-nodes [data-label="run"]').count() == 1
        assert focus.input_value() == ""
        page.locator(".flow-back").click()
        assert focus.input_value() == base_id
        assert nodes.count() == len(neighbors) and edges.count() == connections
        page.get_by_role(
            "button", name="As-Is" if view == "Target" else "Target", exact=True
        ).click()
        page.get_by_role("button", name=view, exact=True).click()
        assert focus.input_value() == base_id
        assert nodes.count() == len(neighbors) and edges.count() == connections
        page.locator("#flow").get_by_role("button", name="Reset filters", exact=True).click()
        assert (
            nodes.evaluate_all("nodes => nodes.map(node => node.dataset.umlId).sort()") == all_nodes
        )
        assert (
            edges.evaluate_all("edges => edges.map(edge => edge.dataset.umlId).sort()") == all_edges
        )
        other_id = page.locator('.flow-nodes [data-label="Other"]').get_attribute("data-uml-id")
        focus.select_option(other_id)
        assert nodes.count() == 1 and nodes.get_attribute("data-uml-id") == other_id
        assert page.locator(".flow-edges .hit").count() == 0
        assert page.locator("#flow-data").text_content() == payload
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
def test_relationship_filter_keeps_evidence_and_restores_scope_state(tmp_path, view):
    html, _ = _uml_report(
        tmp_path,
        mismatch=True,
        extra_source="from .other import external\ndef extra(value): return external(value)\n",
        extra_files={"sample/other.py": "def external(value): return value\n"},
        closed_relationships=("calls",),
    )
    api = pytest.importorskip("playwright.sync_api")
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        _open_module(page, view)
        payload = page.locator("#flow-data").text_content()
        nodes = page.locator(".flow-nodes [data-uml-id]")
        edges = page.locator(".flow-edges [data-uml-id]")
        all_nodes = nodes.evaluate_all("nodes => nodes.map(node => node.dataset.umlId).sort()")
        all_edges = edges.evaluate_all("edges => edges.map(edge => edge.dataset.umlId).sort()")
        inheritance_count = page.locator('.flow-edges [data-relationship-kind="inherits"]').count()
        client_id = page.locator('.flow-nodes [data-label="Client"]').get_attribute("data-uml-id")
        focus = page.locator("#flow-focus")
        focus.select_option(client_id)
        page.locator('.flow-legend button[data-relationship-kind="inherits"]').click()
        assert edges.count() == 1 and edges.get_attribute("data-relationship-kind") == "inherits"
        assert nodes.evaluate_all("nodes => nodes.map(node => node.dataset.label).sort()") == [
            "Base",
            "Client",
        ]
        assert not _route_problems(edges)
        assert "Relationships: inherits" in page.locator(".flow-filter-status").inner_text()
        assert "1 of " in page.locator(".flow-filter-status").inner_text()
        assert page.locator('.flow-legend button[data-relationship-kind="realizes"]').count() == 1
        assert (
            page.locator('.flow-legend button[aria-pressed="true"]').get_attribute(
                "data-relationship-kind"
            )
            == "inherits"
        )
        page.locator('.flow-nodes [data-label="Client"]').click()
        assert "realizes" in page.locator(".flow-inspector-content").inner_text()
        if view == "Diff":
            assert "Core: FAIL" in page.locator(".flow-legend").inner_text()
            assert "unlisted observed relationships" in page.locator(".flow-legend").inner_text()
        edges.locator(".hit").focus()
        edges.locator(".hit").press("Enter")
        page.locator('.flow-legend button[data-relationship-kind="realizes"]').focus()
        page.locator('.flow-legend button[data-relationship-kind="realizes"]').press("Enter")
        assert edges.count() == 1 and edges.get_attribute("data-relationship-kind") == "realizes"
        assert page.locator('.flow-edges [data-relationship-kind="inherits"] .hit').count() == 0
        assert not _route_problems(edges)
        assert page.locator(".flow-inspector-content h2").inner_text() == "sample.core"
        page.locator('.flow-legend button[data-relationship-kind="inherits"]').click()
        page.locator('.flow-nodes [data-label="Client"]').dblclick()
        assert focus.input_value() == ""
        assert page.locator('.flow-nodes [data-label="run"]').count() == 1
        assert (
            page.locator('.flow-legend button[aria-pressed="true"]')
            .inner_text()
            .startswith("All relationships")
        )
        page.locator(".flow-back").click()
        assert focus.input_value() == client_id
        assert edges.count() == 1 and edges.get_attribute("data-relationship-kind") == "inherits"
        page.get_by_role(
            "button", name="As-Is" if view == "Target" else "Target", exact=True
        ).click()
        page.get_by_role("button", name=view, exact=True).click()
        assert edges.count() == 1 and edges.get_attribute("data-relationship-kind") == "inherits"
        page.locator("#flow").get_by_role("button", name="Reset filters", exact=True).click()
        assert (
            nodes.evaluate_all("nodes => nodes.map(node => node.dataset.umlId).sort()") == all_nodes
        )
        assert (
            edges.evaluate_all("edges => edges.map(edge => edge.dataset.umlId).sort()") == all_edges
        )
        page.locator('.flow-legend button[data-relationship-kind="inherits"]').click()
        assert edges.count() == inheritance_count
        assert nodes.evaluate_all("""nodes => nodes.every(node =>
          !node.querySelector('.stereotype').textContent.includes('outside')
          || [...document.querySelectorAll('.flow-edges [data-uml-id]')].some(edge =>
            edge.dataset.umlSource === node.dataset.umlId
          || edge.dataset.umlTarget === node.dataset.umlId))""")
        assert page.locator('.flow-nodes [data-label="Other"]').count() == 1
        page.locator('.flow-legend button[data-relationship-kind=""]').click()
        assert edges.count() == len(all_edges)
        assert page.locator("#flow-data").text_content() == payload
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_cyclic_component_connections_do_not_share_stretches(tmp_path):
    html, _ = _tour_report_page(tmp_path)
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, html)
    try:
        app = page.locator('.flow-nodes [data-uml-kind="component"][data-label="app"]')
        page.locator("#flow-focus").select_option(app.get_attribute("data-uml-id"))
        page.locator("#flow-violations-only").check()
        page.get_by_role("button", name="Fit overview", exact=True).click()
        edges = page.locator(".flow-edges .edge")
        assert edges.count() > 0
        assert edges.evaluate_all(
            "edges => edges.every(edge => edge.dataset.assessmentStatus === 'FAIL')"
        )
        assert not _route_problems(edges)
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
def test_element_kind_filter_retains_evidence_and_navigation(tmp_path, view):
    html, _ = _uml_report(tmp_path, mismatch=True)
    api = pytest.importorskip("playwright.sync_api")
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        _open_module(page, view)
        payload = page.locator("#flow-data").text_content()
        nodes = page.locator(".flow-nodes [data-uml-id]")
        edges = page.locator(".flow-edges [data-uml-id]")
        all_nodes = nodes.evaluate_all("nodes => nodes.map(node => node.dataset.umlId).sort()")
        all_edges = edges.evaluate_all("edges => edges.map(edge => edge.dataset.umlId).sort()")
        complete_count = page.locator("#flow-focus option").count() - 1
        wanted = page.locator('.flow-nodes [data-uml-kind="class"]')
        wanted_ids = nodes.evaluate_all(
            'nodes => nodes.filter(node => node.dataset.umlKind === "class")'
            ".map(node => node.dataset.umlId).sort()"
        )
        kinds = page.get_by_label("Element kind", exact=True)
        kinds.select_option("class")
        assert (
            nodes.evaluate_all("nodes => nodes.map(node => node.dataset.umlId).sort()")
            == wanted_ids
        )
        assert nodes.evaluate_all('nodes => nodes.every(node => node.dataset.umlKind === "class")')
        assert "Elements: class" in page.locator(".flow-filter-status").inner_text()
        assert f"of {complete_count} elements" in page.locator(".flow-filter-status").inner_text()
        assert edges.evaluate_all("""edges => edges.every(edge =>
          document.querySelector(`.flow-nodes [data-uml-id="${edge.dataset.umlSource}"]`)
          && document.querySelector(`.flow-nodes [data-uml-id="${edge.dataset.umlTarget}"]`))""")
        assert not _route_problems(edges)
        assert wanted.count() == len(wanted_ids)
        client = page.locator('.flow-nodes [data-label="Client"]')
        client.click()
        assert "run" in page.locator(".flow-inspector-content").inner_text()
        if view == "Diff":
            assert "Core: FAIL" in page.locator(".flow-legend").inner_text()
        client.dblclick()
        assert kinds.input_value() == ""
        assert page.locator('.flow-nodes [data-label="run"]').count() == 1
        page.locator(".flow-back").click()
        assert kinds.input_value() == "class"
        page.get_by_role(
            "button", name="Target" if view == "As-Is" else "As-Is", exact=True
        ).click()
        page.get_by_role("button", name=view, exact=True).click()
        assert kinds.input_value() == "class"
        kinds.select_option("interface")
        assert nodes.count() == 1 and nodes.get_attribute("data-uml-kind") == "interface"
        assert page.locator(".flow-edges .hit").count() == 0
        page.locator("#flow").get_by_role("button", name="Reset filters", exact=True).click()
        assert kinds.input_value() == ""
        assert (
            nodes.evaluate_all("nodes => nodes.map(node => node.dataset.umlId).sort()") == all_nodes
        )
        assert (
            edges.evaluate_all("edges => edges.map(edge => edge.dataset.umlId).sort()") == all_edges
        )
        assert page.locator("#flow-data").text_content() == payload
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
def test_card_height_and_arrow_endpoints_follow_each_cards_content(tmp_path, view):
    context = {
        "presence": "planned",
        "provenance": ("docs/target.md",),
        "responsibilities": ("Keep the model and helpers distinct.",),
    }
    html, _ = _uml_report(
        tmp_path,
        extra_source=(
            "class Model:\n"
            " first: str\n second: str\n third: str\n fourth: str\n"
            " def run(self):\n  helper()\n"
            "def helper():\n return Model()\n"
        ),
        extra_target_entities=(
            Entity("model", "class", "sample.core.Model", "python", "module", **context),
            *(
                Entity(
                    name,
                    "attribute",
                    f"sample.core.Model.{name}",
                    "python",
                    "model",
                    annotation="str",
                    **context,
                )
                for name in ("first", "second", "third", "fourth")
            ),
            Entity("run", "method", "sample.core.Model.run", "python", "model", **context),
            Entity("helper", "function", "sample.core.helper", "python", "module", **context),
        ),
        extra_target_relationships=(
            Relationship("run-helper", "calls", "run", "helper", provenance=context["provenance"]),
            Relationship(
                "helper-model", "creates", "helper", "model", provenance=context["provenance"]
            ),
        ),
    )
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_module(page, view)
        page.get_by_role("button", name="Member previews", exact=True).click()
        model = page.locator('.flow-nodes [data-label="Model"]')
        helper = page.locator('.flow-nodes [data-label="helper"]')
        assert float(model.locator(".card").get_attribute("height")) > 200
        assert float(helper.locator(".card").get_attribute("height")) < 120
        edges = page.locator(".flow-edges .edge")
        creation = page.locator('.flow-edges [data-relationship-kind="creates"]')
        assert creation.count() == 1
        assert not _route_problems(creation)
        assert page.locator(".flow-nodes .card").evaluate_all("""cards => {
          const boxes = cards.map(card => card.getBoundingClientRect());
          return boxes.every((box, index) => boxes.slice(index + 1).every(other =>
            box.right <= other.left || other.right <= box.left
            || box.bottom <= other.top || other.bottom <= box.top));
        }""")
        assert edges.evaluate_all("""edges => edges.every(edge => {
          const target = document.querySelector(`[data-uml-id="${edge.dataset.umlTarget}"] .card`);
          const box = target.getBoundingClientRect(), line = edge.querySelector('.line');
          const end = line.getPointAtLength(line.getTotalLength());
          const p = new DOMPoint(end.x, end.y).matrixTransform(line.getScreenCTM());
          return Math.min(Math.abs(p.y-box.top), Math.abs(p.y-box.bottom)) < 1
            && p.x >= box.left && p.x <= box.right;
        })""")
        assert edges.evaluate_all("""edges => edges.every(edge => {
          const source = document.querySelector(`[data-uml-id="${edge.dataset.umlSource}"] .card`);
          const box = source.getBoundingClientRect(), line = edge.querySelector('.line');
          const start = line.getPointAtLength(0);
          const p = new DOMPoint(start.x, start.y).matrixTransform(line.getScreenCTM());
          return Math.min(Math.abs(p.y-box.top), Math.abs(p.y-box.bottom)) < 1
            && p.x >= box.left && p.x <= box.right;
        })""")
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
def test_reciprocal_and_recursive_calls_use_distinct_ports_and_lanes(tmp_path, view):
    context = {
        "presence": "planned",
        "provenance": ("docs/target.md",),
        "responsibilities": ("Exercise cyclic calls.",),
    }
    pairs = (("first", "second"), ("second", "first"), ("first", "first"))
    html, _ = _uml_report(
        tmp_path,
        extra_source=(
            "class Cycle:\n"
            " def first(self):\n  self.first()\n  self.second()\n"
            " def second(self):\n  self.first()\n"
        ),
        extra_target_entities=(
            Entity("cycle", "class", "sample.core.Cycle", "python", "module", **context),
            *(
                Entity(name, "method", f"sample.core.Cycle.{name}", "python", "cycle", **context)
                for name in ("first", "second")
            ),
        ),
        extra_target_relationships=tuple(
            Relationship(
                f"{source}-{target}", "calls", source, target, provenance=context["provenance"]
            )
            for source, target in pairs
        ),
    )
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_module(page, view)
        page.locator('.flow-nodes [data-label="Cycle"]').dblclick()
        page.get_by_role("button", name="Fit overview", exact=True).click()
        edges = page.locator('.flow-edges [data-relationship-kind="calls"]')
        assert edges.count() == 3
        assert not _route_problems(edges)
        assert edges.locator(".line").evaluate_all("""lines => lines.every(line => {
          const length = line.getTotalLength(), end = line.getPointAtLength(length);
          const near = line.getPointAtLength(length - 2);
          return length > 40 && near.y > end.y;
        })""")
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
def test_type_cues_and_five_direct_calls_remain_readable(tmp_path, view):
    context = {
        "presence": "planned",
        "provenance": ("docs/target.md",),
        "responsibilities": ("Validate the model boundary.",),
    }
    entities = (
        Entity("mode", "enum", "sample.core.Mode", "python", "module", **context),
        Entity("service", "class", "sample.core.Service", "python", "module", **context),
        *(
            Entity(
                name,
                "method",
                f"sample.core.Service.{name}",
                "python",
                "service",
                signature=Signature(
                    (Parameter("self", kind="positional", default_known=True),), "None"
                ),
                **context,
            )
            for name in ("validate", *HELPERS)
        ),
    )
    html, _ = _uml_report(
        tmp_path,
        extra_source=(
            "from enum import Enum\nclass Mode(Enum):\n LOCAL = 'local'\n"
            "class Service:\n"
            " def validate(self) -> None:\n"
            "  self._validate_entities()\n  self._validate_physical_intent()\n"
            "  self._validate_public_api()\n  self._validate_relationships()\n"
            "  self._validate_scopes()\n"
            " def _validate_entities(self) -> None: pass\n"
            " def _validate_physical_intent(self) -> None: pass\n"
            " def _validate_public_api(self) -> None: pass\n"
            " def _validate_relationships(self) -> None: pass\n"
            " def _validate_scopes(self) -> None: pass\n"
        ),
        extra_target_entities=entities,
        extra_target_relationships=tuple(
            Relationship(
                "call-" + name, "calls", "validate", name, provenance=context["provenance"]
            )
            for name in HELPERS
        ),
    )
    api = pytest.importorskip("playwright.sync_api")
    errors = []
    playwright, browser, page = _browser_page(api, html, width=1550, height=1150, errors=errors)
    try:
        _open_module(page, view)
        interface = page.locator('.flow-nodes [data-label="Port"]')
        classifier = page.locator('.flow-nodes [data-label="Service"]')
        enumeration = page.locator('.flow-nodes [data-label="Mode"]')
        assert interface.locator(".uml-icon circle").count() == 1
        assert classifier.locator(".uml-icon rect").count() == 1
        assert enumeration.locator(".stereotype").text_content() == "«enumeration»"
        colors = {
            item.locator(".stereotype").evaluate("node => getComputedStyle(node).fill")
            for item in (interface, classifier, enumeration)
        }
        assert len(colors) == 3
        classifier.dblclick()
        page.locator('.flow-nodes [data-label="validate"]').dblclick()
        page.locator('.flow-nodes [data-label="validate"]').click()
        page.get_by_role("button", name="Fit overview", exact=True).click()
        for name in ("validate", *HELPERS):
            card = page.locator(f'.flow-nodes [data-label="{name}"]')
            assert card.locator(".label tspan").count() == 1
            assert card.locator(".uml-icon").text_content() == "()"
            assert card.locator(".meta tspan").first.text_content().strip() not in {"+", "−", "?"}
        boxes = {
            name: page.locator(f'.flow-nodes [data-label="{name}"]').bounding_box()
            for name in ("validate", *HELPERS)
        }
        first_row = min(boxes[name]["y"] for name in HELPERS)
        row = [boxes[name] for name in HELPERS if abs(boxes[name]["y"] - first_row) < 1]
        row_center = (
            min(box["x"] for box in row) + max(box["x"] + box["width"] for box in row)
        ) / 2
        assert abs(boxes["validate"]["x"] + boxes["validate"]["width"] / 2 - row_center) < 1
        edges = page.locator('.flow-edges [data-relationship-kind="calls"]')
        assert edges.count() == 5
        assert page.locator('.flow-legend [data-relationship-kind="calls"]').count() == 1
        geometry = edges.evaluate_all("""edges => {
          const cards = [...document.querySelectorAll('.flow-nodes .uml-card')].map(node => ({
            id: node.dataset.umlId, box: node.querySelector('.card').getBoundingClientRect()
          }));
          const problems = [];
          const routes = edges.map(edge => {
            const line = edge.querySelector('.line'), matrix = line.getScreenCTM();
            const length = line.getTotalLength();
            const scale = Math.hypot(matrix.a, matrix.b), step = 2 / scale;
            const point = at => {
              const p = line.getPointAtLength(at);
              return new DOMPoint(p.x, p.y).matrixTransform(matrix);
            };
            const markerId = getComputedStyle(line).markerEnd.match(/#([^")]+)/)?.[1];
            const marker = document.getElementById(markerId)?.querySelector('path');
            if (!marker || getComputedStyle(marker).stroke !== getComputedStyle(line).stroke) {
              problems.push('missing or mismatched arrow: ' + edge.dataset.umlId);
            }
            if (line.getAttribute('d') !== edge.querySelector('.hit').getAttribute('d')) {
              problems.push('invisible hit geometry: ' + edge.dataset.umlId);
            }
            const source = cards.find(card => card.id === edge.dataset.umlSource).box;
            const target = cards.find(card => card.id === edge.dataset.umlTarget).box;
            const end = point(length), near = point(length - step);
            if (Math.abs(end.y - target.top) > 1 || near.y >= end.y) {
              problems.push('arrow does not approach callee from above: ' + edge.dataset.umlId);
            }
            const start = point(0);
            if (Math.abs(start.y - source.bottom) > 1) {
              problems.push('line does not leave caller: ' + edge.dataset.umlId);
            }
            const points = [];
            for (let at = 0; at <= length; at += step) {
              const p = point(at);
              points.push(p);
              if (cards.some(({box}) => p.x > box.left + 1 && p.x < box.right - 1
                && p.y > box.top + 1 && p.y < box.bottom - 1)) {
                problems.push('line crosses a card: ' + edge.dataset.umlId);
                break;
              }
            }
            return points;
          });
          const cross = (a, b, c) => (b.x-a.x)*(c.y-a.y) - (b.y-a.y)*(c.x-a.x);
          const intersects = (a, b, c, d) => {
            const ac = cross(a,b,c), ad = cross(a,b,d);
            const ca = cross(c,d,a), cb = cross(c,d,b);
            return ac*ad <= 0 && ca*cb <= 0
              && (ac !== 0 || ad !== 0) && (ca !== 0 || cb !== 0);
          };
          routes.forEach((points, index) => {
            for (const other of routes.slice(index + 1)) {
              if (points.slice(1).some((p, i) => other.slice(1).some((q, j) =>
                intersects(points[i], p, other[j], q)))) {
                problems.push('direct calls cross');
              }
              let overlap = 0;
              for (const p of points) {
                overlap = other.some(q => Math.hypot(p.x-q.x, p.y-q.y) < 3) ? overlap + 2 : 0;
                if (overlap >= 14) {
                  problems.push('connections share a visible stretch');
                  break;
                }
              }
            }
          });
          return problems;
        }""")
        assert not geometry, geometry
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
def test_explicit_fit_reveals_every_card_in_a_large_level(tmp_path, view):
    names = tuple(f"Box{i:02}" for i in range(20))
    html, _ = _uml_report(
        tmp_path,
        extra_source="\n".join(f"class {name}: pass" for name in names) + "\n",
        extra_target_entities=tuple(
            Entity(
                name,
                "class",
                "sample.core." + name,
                "python",
                "module",
                presence="planned",
                responsibilities=("Store one value.",),
                provenance=("docs/target.md",),
            )
            for name in names
        ),
    )
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, html, width=1300, height=800)
    try:
        _open_module(page, view)
        page.get_by_role("button", name="Fit overview", exact=True).click()
        visible = page.locator(".flow-canvas").evaluate("""canvas => {
          const bounds = canvas.getBoundingClientRect();
          return [...canvas.querySelectorAll('.flow-nodes .card')].every(card => {
            const box = card.getBoundingClientRect();
            return box.left >= bounds.left && box.right <= bounds.right
              && box.top >= bounds.top && box.bottom <= bounds.bottom;
          });
        }""")
        assert visible
        assert page.locator('.flow-nodes [data-uml-kind="class"]').count() >= 20
        assert page.locator(".flow-canvas").evaluate("""canvas => {
          const cards = [...canvas.querySelectorAll('.flow-nodes .card')]
            .map(card => card.getBoundingClientRect());
          const width = Math.max(...cards.map(box => box.right))
            - Math.min(...cards.map(box => box.left));
          return width > canvas.clientWidth * 0.65;
        }""")
    finally:
        browser.close()
        playwright.stop()
