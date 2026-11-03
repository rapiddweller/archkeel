# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290: the Studio shell loads, navigates by keyboard and asks only its own server."""

from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from test_explore import _repository
from test_studio import _start, _stop, explore, login

from archkeel.studio.server import Studio

_LEGEND = ("Observed = code evidence", "Claim = agent hypothesis", "Target = architect decision")
# Data and blob URLs are page content, not requests to a host.
_LOCAL_SCHEMES = {"data", "blob", "about"}


@pytest.fixture(scope="module")
def studio(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Studio]:
    tmp_path = tmp_path_factory.mktemp("studio")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        server = _start(_repository(tmp_path / "shop"))
        assert explore(server, login(server))["explore"] == "done"
        yield server
        _stop(server)


def _check_the_embedded_explorer(page, width: int, height: int) -> None:
    """Only the Explorer canvas, dark from the start, filling the main area; selection shows."""
    element = page.locator("iframe[title='Explorer']")
    element.wait_for()
    page.frame_locator("iframe[title='Explorer']").locator(
        "#flow[data-layout-state='ready']"
    ).wait_for()
    page.locator("iframe[title='Explorer'].ready").wait_for()
    inner = element.element_handle().content_frame()
    # No light flash: an Explorer frame stays hidden until it has loaded and taken the tokens.
    unloaded = (
        "(() => { const frame = document.createElement('iframe'); document.body.append(frame);"
        " const visibility = getComputedStyle(frame).visibility; frame.remove();"
        " return visibility; })()"
    )
    assert page.evaluate(unloaded) == "hidden"
    assert inner.get_by_role("banner").count() == 0
    assert inner.evaluate(
        "[...document.querySelectorAll('.report-shell > :not(.flow-section)')]"
        ".every((item) => getComputedStyle(item).display === 'none')"
    )
    assert (
        inner.locator(".ak-brand, .flow-fullscreen, .flow-open-selected, .theme-toggle").count()
        == 4
    )
    assert inner.evaluate(
        "[...document.querySelectorAll('.ak-brand, .flow-fullscreen, .flow-open-selected,"
        " .theme-toggle')].every((item) => !item.checkVisibility())"
    )
    assert inner.get_by_role("button", name="Search").is_visible()
    assert inner.evaluate("getComputedStyle(flow).backgroundColor") == "rgb(10, 18, 24)"
    assert inner.evaluate("document.documentElement.scrollHeight <= innerHeight")
    box = element.bounding_box()
    assert box["y"] + box["height"] >= height - 32, box
    assert box["width"] >= (width - 260) / 2, box
    assert page.evaluate("document.documentElement.scrollHeight") <= height

    card = inner.locator("g.node[data-uml-id]").first
    component = card.get_attribute("data-uml-id")
    card.click()
    panel = page.get_by_role("complementary", name="Selected component")
    panel.get_by_text(component, exact=True).wait_for()


@pytest.mark.browser
@pytest.mark.parametrize(("width", "height"), [(1440, 900), (800, 600)])
def test_the_shell_navigates_and_stays_on_its_server(
    studio: Studio, width: int, height: int, tmp_path: Path
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    requests: list[str] = []
    errors: list[str] = []
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        # Slice 1 is always dark, also when the system prefers light.
        page = browser.new_page(viewport={"width": width, "height": height}, color_scheme="light")
        page.set_default_timeout(20000)
        page.on("request", lambda item: requests.append(item.url))
        page.on("pageerror", lambda error: errors.append(str(error)))
        # A request that the CSP header blocks shows as a console error.
        page.on("console", lambda item: item.type == "error" and errors.append(item.text))
        try:
            page.goto(studio.url)
            assert urlsplit(page.url).path == "/"
            page.get_by_role("heading", name="Understand the codebase").wait_for()
            for text in (*_LEGEND, "Contract: NOT CONFIGURED", "As-Is / Observed"):
                assert page.get_by_text(text, exact=True).is_visible(), text
            assert page.get_by_text("Target unavailable", exact=True).is_visible()
            background = "getComputedStyle(document.body).backgroundColor"
            assert page.evaluate(background) == "rgb(10, 18, 24)"
            contract = page.get_by_text("Contract: NOT CONFIGURED", exact=True)
            assert contract.bounding_box()["height"] < 24, "the contract state wraps"
            assert page.get_by_text("Open Explore").is_visible()

            page.get_by_role("link", name="Explore", exact=True).focus()
            page.keyboard.press("Enter")
            assert urlsplit(page.url).fragment == "/explore"
            _check_the_embedded_explorer(page, width, height)
            page.screenshot(path=tmp_path / f"explore-{width}.png")

            for name, fragment, heading in (
                ("Flows", "/flows", "Flows"),
                ("Impact", "/impact", "Change impact"),
                ("Target / Diff", "/target", "Target and diff"),
            ):
                page.get_by_role("link", name=name, exact=True).click()
                assert urlsplit(page.url).fragment == fragment
                page.get_by_role("heading", name=heading).wait_for()
                assert page.get_by_text("Not built in Studio yet.").is_visible(), name
            page.get_by_role("link", name="Overview", exact=True).click()
            page.locator('nav a[aria-current="page"]', has_text="Overview").wait_for()
            assert page.evaluate("document.documentElement.scrollWidth") <= width
        finally:
            browser.close()
    assert errors == []
    outside = [
        url
        for url in requests
        if urlsplit(url).scheme not in _LOCAL_SCHEMES
        and urlsplit(url).netloc != f"127.0.0.1:{studio.port}"
    ]
    assert outside == []
    assert any(urlsplit(url).path == "/api/v1/state" for url in requests)
    assert any(urlsplit(url).path == "/files/architecture.report.html" for url in requests)
