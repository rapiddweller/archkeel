# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Browser acceptance follows the native default and its published details."""

import contextlib
import io
import json

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


def test_native_component_sidecar_retains_constants_and_own_members(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    from tools.report_browser import _check_inner_uml

    architecture = tmp_path / "architecture.json"
    with contextlib.redirect_stdout(io.StringIO()):
        assert replay("uml-complete", architecture) == 0
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(architecture.with_suffix(".report.html").as_uri())
            _check_inner_uml(page, "uml-complete", tmp_path)
            assert "detail-component-" in page.url
            assert "atlas" not in json.loads(page.locator("#flow-data").text_content())
            page.get_by_role("link", name="Back to architecture map", exact=True).click()
            assert page.locator('[data-atlas="true"]').is_visible()
        finally:
            browser.close()
