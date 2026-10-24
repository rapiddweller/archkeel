# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Browser fixtures for the standard architecture report."""

from typing import Any


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
