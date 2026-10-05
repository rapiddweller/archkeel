# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Legacy Target scenes retain authenticated graph identities and permission evidence."""

import json

import pytest
from browser_report_support import _browser_page
from test_target_graph import _nested_repository, _permission_contract
from test_uml_evaluation import _repository

from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.graph_codec import parse_graph
from archkeel.ir.target_records import recorded_target_graph
from archkeel.render.html import render_html


def test_layer_report_initializes_target_and_shows_layer_intent(tmp_path):
    from test_layers import _layer_contract
    from test_target_graph import _repository as _target_repository

    api = pytest.importorskip("playwright.sync_api")
    root, config = _target_repository(tmp_path)
    (root / config.contract).write_text(json.dumps(_layer_contract()))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    html = render_html(result, model, repository="sample", architecture_href=None).decode()
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        page.locator('[data-flow-view="target"]').click()
        page.locator('.flow-nodes [data-uml-id="core"]').click()
        details = page.locator(".flow-inspector-content").inner_text()
        assert "Layer" in details and "Core" in details
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def _legacy_report(tmp_path, *, nested=False, version="2.2.0", explicit_uml=False):
    root, config = _nested_repository(tmp_path) if nested else _repository(tmp_path)
    paths = (config.contract, "inside.json", "leaf.json") if nested else (config.contract,)
    owner_path = "inside.json" if nested else config.contract
    for path in paths:
        raw = json.loads((root / path).read_bytes())
        raw["schema_version"] = version
        if not explicit_uml:
            raw.get("declarations", {}).pop("uml", None)
        if path == owner_path:
            raw = _permission_contract(raw)
            owner = raw["components"][0]
            owner.update(role="foundation", public=[], planned=["sample.core:Future"])
            owner["requires"].extend(
                [
                    {"component": "peer", "rationale": "Read another published surface."},
                    dict(owner["requires"][0]),
                ]
            )
            raw["components"].append(
                {
                    **raw["components"][1],
                    "id": "OTHER",
                    "label": "other",
                    "namespace": "sample.core.other",
                    "packages": ["sample.core.other"],
                }
            )
        (root / path).write_text(json.dumps(raw))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    declaration = next(
        item
        for item in model.records("declarations")
        if item.kind == ("uml_target" if explicit_uml else "architecture_target")
    )
    graph = recorded_target_graph(model, declaration)
    html = render_html(
        result, model, repository="sample", architecture_href="architecture.json"
    ).decode()
    start = html.index('id="flow-data"')
    payload = json.loads(html[html.index(">", start) + 1 : html.index("</script>", start)])
    return html, payload, graph


@pytest.mark.parametrize("version", ["2.1.0", "2.2.0"])
@pytest.mark.parametrize("nested", [False, True])
def test_legacy_permission_projection_keeps_graph_ids_endpoints_and_evidence(
    tmp_path, nested, version
):
    _, payload, graph = _legacy_report(tmp_path, nested=nested, version=version)
    permissions = [item for item in graph.relationships if item.kind == "requires"]
    assert len(permissions) == 3 and len({item.id for item in permissions}) == 3
    projected = parse_graph(payload["target"])
    assert projected == graph
    assert [item for item in projected.relationships if item.kind == "requires"] == permissions
    assert all(item.reason and item.provenance and item.decided_by for item in permissions)
    assert payload["comparison"] is None
    assert not {"uml", "explorers", "components", "modules"}.intersection(payload)


@pytest.mark.parametrize("nested", [False, True])
def test_legacy_permission_browser_keeps_distinct_selection_and_connected_focus(tmp_path, nested):
    api = pytest.importorskip("playwright.sync_api")
    html, _, graph = _legacy_report(tmp_path, nested=nested)
    permissions = [item for item in graph.relationships if item.kind == "requires"]
    owner = next(item for item in graph.entities if item.id == permissions[0].source_id)
    intent = next(item for item in graph.component_intents if item.component_id == owner.id)
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        page.locator('[data-flow-view="target"]').click()
        if nested:
            page.locator(f'.flow-nodes [data-uml-id="{intent.parent_id}"]').press("Enter")
        owner_card = page.locator(f'.flow-nodes [data-uml-id="{owner.id}"]')
        assert "foundation" in owner_card.locator(".meta").text_content()
        owner_card.click()
        details = page.locator(".flow-inspector-content")
        text = details.inner_text()
        assert "Component role" in text and "foundation" in text
        assert "Published API" in text and "Explicitly empty" in text
        assert "Planned interface (proposed)" in text and "sample.core:Future" in text
        assert "Language visibility" not in text
        paths = []
        for permission in permissions:
            edge = page.locator(f'.flow-edges [data-uml-id="{permission.id}"]')
            assert edge.count() == 1
            edge.locator(".hit").press("Enter")
            assert edge.locator(".hit").get_attribute("aria-pressed") == "true"
            text = details.inner_text()
            assert permission.reason in text and permission.decided_by in text
            assert page.locator('.flow-edges .hit[aria-pressed="true"]').count() == 1
            assert "related" in owner_card.get_attribute("class")
            peer = page.locator(f'.flow-nodes [data-uml-id="{permission.target_id}"]')
            assert "related" in peer.get_attribute("class")
            other = next(item for item in graph.component_intents if item.label == "other")
            assert "dim" in page.locator(
                f'.flow-nodes [data-uml-id="{other.component_id}"]'
            ).get_attribute("class")
            path = edge.locator(".line")
            assert "flow-arrow-declared" in path.evaluate(
                "node => getComputedStyle(node).markerEnd"
            )
            assert "This does not require an import or call" in text
            paths.append(path.get_attribute("d"))
        assert len(set(paths)) == len(permissions)
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_target_graph_is_decoded_once_for_both_rendering_payloads(tmp_path, monkeypatch):
    import archkeel.ir.report_graph as producer

    decoded = []
    original = producer.recorded_target_graph
    original_render = render_html

    def record_decode(observation, declaration):
        decoded.append(declaration.id)
        return original(observation, declaration)

    def measured_render(*args, **kwargs):
        assert len(decoded) == 1
        decoded.clear()
        page = original_render(*args, **kwargs)
        assert len(decoded) == 1
        return page

    monkeypatch.setattr(producer, "recorded_target_graph", record_decode)
    monkeypatch.setattr(f"{__name__}.render_html", measured_render)
    _, payload, graph = _legacy_report(tmp_path, nested=True)
    assert len(decoded) == 1
    assert parse_graph(payload["target"]) == graph


@pytest.mark.parametrize("nested", [False, True])
def test_explicit_uml_keeps_each_dependency_permission_selectable(tmp_path, nested):
    api = pytest.importorskip("playwright.sync_api")
    html, payload, graph = _legacy_report(tmp_path, nested=nested, explicit_uml=True)
    assert payload["comparison"] is not None
    permissions = [item for item in graph.relationships if item.kind == "requires"]
    owner = next(item for item in graph.entities if item.id == permissions[0].source_id)
    intent = next(item for item in graph.component_intents if item.component_id == owner.id)
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        page.locator('[data-flow-view="target"]').click()
        if nested:
            page.locator(f'.flow-nodes [data-uml-id="{intent.parent_id}"]').press("Enter")
        edges = page.locator('.flow-edges [data-relationship-kind="requires"]')
        assert edges.count() == len(permissions)
        paths = []
        for permission in permissions:
            edge = page.locator(f'.flow-edges [data-uml-id="{permission.id}"]')
            assert edge.get_attribute("data-uml-source") == permission.source_id
            assert edge.get_attribute("data-uml-target") == permission.target_id
            edge.locator(".hit").press("Enter")
            text = page.locator(".flow-inspector-content").inner_text()
            assert permission.reason in text and permission.decided_by in text
            assert "This does not require an import or call" in text
            assert "declaration site" in edge.locator(".hit").get_attribute("aria-label")
            paths.append(edge.locator(".line").get_attribute("d"))
        assert len(set(paths)) == len(permissions)
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_target_cycle_self_loop_and_dependents_keep_every_permission(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    root, config = _repository(tmp_path)
    raw = json.loads((root / config.contract).read_bytes())
    raw.get("declarations", {}).pop("uml", None)
    template = raw["components"][0]
    dependencies = {
        "a": ["a", "b", "dependent"],
        "b": ["a"],
        "dependent": [],
        "entry": ["leaf"],
        "leaf": [],
    }
    raw["components"] = [
        {
            **template,
            "id": label,
            "label": label,
            "namespace": "sample.core" if label == "a" else f"sample.{label}",
            "packages": ["sample.core" if label == "a" else f"sample.{label}"],
            "public": [],
            "requires": [
                {"component": target, "rationale": "Keep this explicit permission."}
                for target in targets
            ],
        }
        for label, targets in dependencies.items()
    ]
    (root / config.contract).write_text(json.dumps(raw))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    html = render_html(result, model, repository="sample", architecture_href=None).decode()
    playwright, browser, page = _browser_page(api, html)
    try:
        page.get_by_role("button", name="Target", exact=True).click()
        payload = page.locator("#flow-data").text_content()
        assert page.locator('.flow-edges [data-relationship-kind="requires"]').count() == 5
        coordinates = page.locator(".flow-nodes [data-uml-id]").evaluate_all("""nodes =>
          Object.fromEntries(nodes.map(node => [node.dataset.label,
            node.transform.baseVal.getItem(0).matrix.f]))
        """)
        assert coordinates["a"] == coordinates["b"] == coordinates["dependent"]
        assert coordinates["leaf"] > coordinates["entry"]
        page.locator('.flow-nodes [data-label="dependent"]').press("Space")
        assert (
            "Keep this explicit permission" in page.locator(".flow-inspector-content").inner_text()
        )
        assert page.locator("#flow-data").text_content() == payload
    finally:
        browser.close()
        playwright.stop()


def test_large_component_chain_stays_readable_on_automatic_fit(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    root, config = _repository(tmp_path)
    raw = json.loads((root / config.contract).read_bytes())
    raw.get("declarations", {}).pop("uml", None)
    template = raw["components"][0]
    raw["components"] = [
        {
            **template,
            "id": f"layer-{index}",
            "label": f"layer-{index}",
            "namespace": f"sample.layer{index}",
            "packages": [f"sample.layer{index}"],
            "public": [],
            "requires": [{"component": f"layer-{index + 1}", "rationale": "Delegate one layer."}]
            if index < 11
            else [],
        }
        for index in range(12)
    ]
    (root / config.contract).write_text(json.dumps(raw))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    html = render_html(result, model, repository="sample", architecture_href=None).decode()
    playwright, browser, page = _browser_page(api, html)
    try:
        page.get_by_role("button", name="Target", exact=True).click()
        payload = page.locator("#flow-data").text_content()
        assert int(page.locator(".flow-zoom-value").inner_text().removesuffix("%")) >= 85
        assert page.locator(".flow-nodes .node").count() == 12
        assert page.locator(".flow-nodes .node").evaluate_all("""nodes => {
            const canvas = document.querySelector('.flow-canvas').getBoundingClientRect();
            return nodes.every(node => { const box = node.getBoundingClientRect();
                return box.left >= canvas.left && box.right <= canvas.right
                    && box.top >= canvas.top && box.bottom <= canvas.bottom; });
        }""")
        assert page.locator(".flow-edges .edge").count() == 11
        page.mouse.move(0, 0)
        assert (
            float(
                page.locator(".flow-edges .line").first.evaluate(
                    "node => getComputedStyle(node).opacity"
                )
            )
            < 0.5
        )
        page.locator('.flow-nodes [data-label="layer-0"]').press("Space")
        assert page.locator(".flow-nodes .related").count() == 2
        assert page.locator(".flow-nodes .dim").count() == 10
        assert (
            float(
                page.locator(".flow-edges .related .line").first.evaluate(
                    "node => getComputedStyle(node).opacity"
                )
            )
            == 1
        )
        assert page.locator("#flow-data").text_content() == payload
    finally:
        browser.close()
        playwright.stop()
