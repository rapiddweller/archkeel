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


@pytest.mark.parametrize("variant, exit_code", [("uml-complete", 0), ("tour", 2)])
def test_native_atlas_acceptance_rejects_a_corrupted_core_status(tmp_path, variant, exit_code):
    api = pytest.importorskip("playwright.sync_api")
    from tools.report_browser import _check_atlas, _check_atlas_interactions

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


def test_native_shared_shell_retains_uml_and_returns_to_origin_scope(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    from tools.report_browser import _check_inner_uml

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
            page.goto(main + "?theme=dark")
            heading = page.locator(".atlas-heading").inner_text()
            verdict = page.locator(".atlas-status").inner_text()
            page.get_by_role("button", name="Diff", exact=True).click()
            _check_inner_uml(page, "uml-complete", tmp_path)
            assert "detail-component-" in page.url
            data = json.loads(page.locator("#flow-data").text_content())
            assert "atlas" not in data
            assert page.locator(".atlas-heading").inner_text() == heading
            assert page.locator(".atlas-status").inner_text() == verdict
            assert page.locator("html").get_attribute("data-theme") == "dark"
            assert page.locator(".theme-toggle").count() == 1
            page.locator('[data-lexical-depth="1"]').click()
            client = next(
                item
                for item in data["observed"]["entities"]
                if item["qualified_name"] == "demo.core.Client"
            )
            page.locator(f'.flow-nodes [data-uml-id="{client["id"]}"]').press("Enter")
            assert parse_qs(urlsplit(page.url).query)["scope"] == [client["id"]]
            page.reload()
            assert page.locator('.flow-nodes [data-label="reset"]').count() == 1
            assert (
                page.get_by_role("button", name="Diff", exact=True).get_attribute("aria-pressed")
                == "true"
            )
            page.locator(".flow-back").click()
            assert "scope" not in parse_qs(urlsplit(page.url).query)
            page.go_back()
            assert page.locator('.flow-nodes [data-label="reset"]').count() == 1
            page.locator(".flow-back").click()
            page.locator(".flow-back").click()
            assert page.url.startswith(main + "?")
            assert parse_qs(urlsplit(page.url).query) == {
                "scope": [data["navigation"]["component_id"]],
                "view": ["diff"],
                "theme": ["dark"],
            }
            assert page.locator('[data-atlas="true"]').is_visible()
            assert page.locator(".atlas-heading").inner_text() == heading
            assert page.locator(".atlas-status").inner_text() == verdict
            assert not errors and not external
        finally:
            browser.close()
