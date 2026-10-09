# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Browser acceptance follows the native default and its published details."""

import contextlib
import io
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from fixtures.architecture_demo import replay


@pytest.mark.parametrize("width", [1440, 375])
def test_native_module_cards_match_local_cells_and_return_scope_theme(tmp_path, width):
    from test_atlas_report import _route_pages

    api = pytest.importorskip("playwright.sync_api")
    from tools.report_browser import _check_module_graph, _wait_for_layout

    index, graph = _route_pages(tmp_path, local_imports=True, package_empty=True)
    module = next(item for item in graph.entities if item.qualified_name == "sample.core")
    empty = next(item for item in graph.entities if item.qualified_name == "sample")
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            main = index.as_uri()
            page.goto(main + "?scope=core&view=diff&theme=dark")
            _check_module_graph(page)
            assert page.get_by_role("group", name="Content", exact=True).is_hidden()
            assert page.locator(".atlas-summary").inner_text() == (
                "Current level: 2 observed modules · 1 local dependency · 2 import sites"
                " · 1 cross-scope relationship not drawn at this level"
            )
            page.locator(".atlas-summary").evaluate("n => n.textContent = '0 imports'")
            with pytest.raises(AssertionError):
                _check_module_graph(page)
            page.reload()
            _wait_for_layout(page)
            page.locator(f'.flow-nodes [data-uml-id="{module.id}"]').dblclick()
            page.wait_for_url("**/architecture.detail.html?*")
            assert page.locator('.flow-nodes [data-label="Client"]').is_visible()
            page.get_by_role("link", name="Back to architecture map", exact=True).click()
            _wait_for_layout(page)
            assert parse_qs(urlsplit(page.url).query) == {
                "scope": ["core"],
                "view": ["diff"],
                "selected": [module.id],
                "theme": ["dark"],
            }
            page.locator(f'.flow-nodes [data-uml-id="{empty.id}"]').press("Enter")
            page.wait_for_url("**/architecture.detail.html?*")
            assert "No direct declarations" in page.locator(".flow-alternative").inner_text()
            assert "sample/__init__.py" in page.locator(".flow-alternative").inner_text()
            page.get_by_role("link", name="Back to architecture map", exact=True).click()
            _wait_for_layout(page)
            page.get_by_role("button", name="Target", exact=True).click()
            _wait_for_layout(page)
            assert not page.locator('.flow-nodes [data-uml-kind="module"]').count()
            assert "No declared modules recorded" in page.locator(".flow-alternative").inner_text()
            page.goto(main + "?view=diff&theme=dark")
            _check_module_graph(page)
            assert page.get_by_role("group", name="Content", exact=True).is_visible()
            page.locator(f'.flow-nodes [data-uml-id="{module.id}"]').press("Enter")
            page.wait_for_url("**/architecture.detail.html?*")
            assert parse_qs(urlsplit(page.url).query)["return_content"] == ["modules"]
            page.get_by_role("link", name="Back to architecture map", exact=True).click()
            assert parse_qs(urlsplit(page.url).query)["content"] == ["modules"]
            _check_module_graph(page)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors
        finally:
            browser.close()


def test_native_wide_inventory_opens_an_isolated_module_card(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    from tools.report_browser import _check_wide_inventory

    architecture = tmp_path / "architecture.json"
    with contextlib.redirect_stdout(io.StringIO()):
        assert replay("class-a-recursive-wide-package", architecture) == 0
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(architecture.with_suffix(".report.html").as_uri())
            _check_wide_inventory(page)
            assert page.locator('.flow-nodes [data-label="VALUE"]').is_visible()
        finally:
            browser.close()


@pytest.mark.parametrize("variant, exit_code", [("uml-complete", 0), ("tour", 2)])
def test_native_atlas_acceptance_rejects_a_corrupted_core_status(tmp_path, variant, exit_code):
    api = pytest.importorskip("playwright.sync_api")
    from tools.report_browser import _capture_assets, _check_atlas, _check_atlas_interactions

    architecture = tmp_path / "architecture.json"
    with contextlib.redirect_stdout(io.StringIO()):
        assert replay(variant, architecture) == exit_code
    report = architecture.with_suffix(".report.html")
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(report.as_uri())
            _check_atlas(page, architecture)
            _check_atlas_interactions(page)
            if variant == "tour":
                _capture_assets(browser, {"tour": report}, tmp_path)
            page.evaluate("""() => {
                const script = document.querySelector('#flow-data');
                const data = JSON.parse(script.textContent);
                data.atlas.components[0].status = 'PASS';
                script.textContent = JSON.stringify(data);
            }""")
            with pytest.raises(AssertionError):
                _check_atlas(page, architecture)
        finally:
            browser.close()


@pytest.mark.parametrize("initial_view", ["diagram", "diff"])
def test_native_shared_shell_retains_uml_and_returns_to_origin_scope(tmp_path, initial_view):
    api = pytest.importorskip("playwright.sync_api")
    from tools.report_browser import _check_inner_uml, _wait_for_layout

    architecture = tmp_path / "architecture.json"
    with contextlib.redirect_stdout(io.StringIO()):
        assert replay("uml-complete", architecture) == 0
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors, external = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda request: (
                    external.append(request.url)
                    if request.url.startswith(("http:", "https:"))
                    else None
                ),
            )
            main = architecture.with_suffix(".report.html").as_uri()
            page.goto(main + f"?theme=dark&view={initial_view}")
            from archkeel.ir.codec import decode_canonical_model, parse_observation
            from archkeel.ir.report_graph import architecture_report

            report = architecture_report(
                parse_observation(decode_canonical_model(json.loads(architecture.read_text())))
            )
            atlas = json.loads(page.locator("#flow-data").text_content())["atlas"]
            target_modules = {item.id for item in report.target.entities if item.kind == "module"}
            observed_modules = {
                item.id for item in report.observed.entities if item.kind == "module"
            }
            expected_module_correspondences = [
                {"target_id": item.target_id, "observed_ids": list(item.observed_ids)}
                for item in report.comparison.correspondences
                if item.target_id in target_modules
                and any(identity in observed_modules for identity in item.observed_ids)
            ]
            assert atlas["module_correspondences"] == expected_module_correspondences
            heading = page.locator(".atlas-heading").inner_text()
            verdict = page.locator(".atlas-status").inner_text()
            _check_inner_uml(page, "uml-complete", tmp_path)
            assert page.url.split("?")[0].endswith("architecture.detail.html")
            data = json.loads(page.locator("#flow-data").text_content())
            detail_query = parse_qs(urlsplit(page.url).query)
            source_selection = detail_query["return_selected"][0]
            return_scope = detail_query.get("return_scope", [None])[0]
            assert source_selection in {
                item.id for item in report.observed.entities if item.kind == "module"
            }
            assert "atlas" not in data
            assert page.locator(".atlas-heading").inner_text() == heading
            detail_status = page.locator(".atlas-detail-status")
            assert "Whole-run rules:" in detail_status.inner_text()
            assert verdict.replace("\n", " ") in detail_status.inner_text()
            assert not page.locator(".decision-banner, .atlas-verdict-grid").count()
            assert (
                detail_status.get_by_role("link", name="Architecture overview").get_attribute(
                    "href"
                )
                == "architecture.report.html"
            )
            assert page.locator("html").get_attribute("data-theme") == "dark"
            assert page.locator(".theme-toggle").count() == 1
            page.locator('[data-lexical-depth="1"]').click()
            observed_client = next(
                item
                for item in data["observed"]["entities"]
                if item["qualified_name"] == "demo.core.Client"
            )
            client_counterparts = {
                item.target_id
                for item in report.comparison.correspondences
                if item.observed_ids == (observed_client["id"],)
            }
            assert len(client_counterparts) <= 1
            client_id = next(iter(client_counterparts), observed_client["id"])
            page.locator(f'.flow-nodes [data-uml-id="{client_id}"]').press("Enter")
            assert parse_qs(urlsplit(page.url).query)["scope"] == [client_id]
            page.reload()
            _wait_for_layout(page)
            assert page.locator('.flow-nodes [data-label="reset"]').count() == 1
            assert (
                page.get_by_role("button", name="Diff", exact=True).get_attribute("aria-pressed")
                == "true"
            )
            page.locator(".flow-back").click()
            assert "scope" not in parse_qs(urlsplit(page.url).query)
            page.go_back()
            _wait_for_layout(page)
            assert page.locator('.flow-nodes [data-label="reset"]').count() == 1
            page.locator(".flow-back").click()
            page.locator(".flow-back").click()
            assert page.url.startswith(main + "?")
            assert parse_qs(urlsplit(page.url).query) == {
                "scope": [return_scope],
                "view": [initial_view],
                "selected": [source_selection],
                "theme": ["dark"],
            }
            assert page.locator('[data-atlas="true"]').is_visible()
            assert page.locator(".atlas-heading").inner_text() == heading
            assert page.locator(".atlas-status").inner_text() == verdict
            assert not errors and not external
        finally:
            browser.close()
