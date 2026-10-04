# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Browser fixtures for the standard architecture report."""

import json
from pathlib import Path
from typing import Any

from test_architecture_demo import CONFIG
from test_report_filter import _tour_root

from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.render.html import render_html


def _browser_page(
    playwright_api: Any,
    html: str,
    width: int = 1440,
    height: int = 1000,
    errors: list[str] | None = None,
    has_touch: bool = False,
):
    playwright = playwright_api.sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": width, "height": height}, has_touch=has_touch)
    page.set_default_timeout(10000)
    if errors is not None:
        page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.set_content(html, wait_until="load", timeout=30000)
    except Exception:
        browser.close()
        playwright.stop()
        raise
    return playwright, browser, page


def _open_details(page: Any) -> None:
    toggle = page.locator("[data-flow-details-toggle]")
    if toggle.count() and toggle.is_visible() and toggle.get_attribute("aria-expanded") != "true":
        toggle.click()


def _report_page(root: Path) -> tuple[str, dict[str, Any]]:
    result, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None, result.diagnostics
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    page_html = render_html(
        result, observation, repository="shop", architecture_href="architecture.json"
    ).decode()
    marker = page_html.index('id="flow-data"')
    start = page_html.index(">", marker) + 1
    payload = json.loads(page_html[start : page_html.index("</script>", start)])
    return page_html, payload


def _tour_report_page(tmp_path: Path) -> tuple[str, dict[str, Any]]:
    return _report_page(_tour_root(tmp_path))
