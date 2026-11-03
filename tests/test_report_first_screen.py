# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Explorer opens on what is here (AD-264): inventory, verdict, first-screen position.

Details starts closed (AD-286); the tests that read the inventory open it first.
"""

import json
import re
from pathlib import Path

import pytest
from browser_report_support import _browser_page, _open_details
from test_architecture_demo import _prepare_repo

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.decisions import agent_decisions
from archkeel.render.html import render_architecture_html
from fixtures.architecture_demo import replay

_TARGET = "The target is authored independently of source facts.\n"


def _report(tmp_path: Path, components, *, rule_deciders=(), hub_imports=False, intent=True):
    """Each component is (name, module count); a component's modules live in its own package.

    Each entry of `rule_deciders` is one complete_requires rule; the rules are the decisions
    the verdict counts, so agent_decisions sees exactly these.
    """
    files = {"sample/__init__.py": "", "docs/target.md": _TARGET}
    contract_components = []
    for name, modules in components:
        for index in range(modules):
            text = "import sample.hub.m0\n" if hub_imports and index == 0 else "VALUE = 1\n"
            files[f"sample/{name}/m{index}.py"] = text
        contract_components.append(
            {
                "id": name,
                "label": name,
                "role": "component",
                "packages": [f"sample.{name}"],
                "namespace": f"sample.{name}",
                "responsibilities": [f"Own the {name}."] if intent else [],
                "forbidden_responsibilities": [],
                "requires": [],
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            }
        )
    rules = [
        {
            "id": f"dependencies-{index}",
            "kind": "complete_requires",
            "rationale": "Each crossing must be explicitly granted.",
            "provenance": ["docs/target.md"],
            "decided_by": decider,
        }
        for index, decider in enumerate(rule_deciders)
    ]
    contract = {"schema_version": "2.2.0", "components": contract_components, "rules": rules}
    files["contract.json"] = json.dumps(contract)
    root = _prepare_repo(tmp_path, files)
    config = ScanConfig(("sample",), "sample", "contract.json", "0" * 64)
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None
    return result, encoded


def _html(result, encoded) -> str:
    return render_architecture_html(
        result, encoded, repository="Sample", architecture_href="architecture.json"
    ).decode()


def _verdict(page: str) -> str:
    (line,) = re.findall(r'<p class="verdict-line".*?</p>', page, re.S)
    return re.sub(r"<[^>]+>", "", line)


def _twelve(prefix: str = "part") -> list[tuple[str, int]]:
    return [(f"{prefix}{index:02d}", index + 1) for index in range(12)]


def _open(tmp_path: Path, components, **kwargs):
    api = pytest.importorskip("playwright.sync_api")
    result, encoded = _report(tmp_path, components, **kwargs)
    return api, _html(result, encoded)


@pytest.mark.browser
def test_inventory_lists_the_eight_largest_components_by_module_count(tmp_path):
    api, html = _open(tmp_path, _twelve())
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_details(page)
        rows = page.locator(".flow-inventory-row")
        rows.first.wait_for()
        assert rows.count() == 8
        assert [row.get_attribute("data-inventory-component") for row in rows.all()] == [
            f"part{index:02d}" for index in range(11, 3, -1)
        ]
        counts = [row.locator(".flow-inventory-count").inner_text() for row in rows.all()]
        assert counts == [str(count) for count in range(12, 4, -1)]
        assert "12 components" in page.locator(".flow-inventory").inner_text()
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_inventory_of_142_components_draws_eight_rows_until_show_all(tmp_path):
    components = [(f"part{index:03d}", 1) for index in range(142)]
    api, html = _open(tmp_path, components)
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_details(page)
        rows = page.locator(".flow-inventory-row")
        rows.first.wait_for()
        assert rows.count() == 8
        assert page.locator(".flow-inventory-filter").count() == 1
        show_all = page.get_by_role("button", name="Show all 142 components")
        show_all.click()
        assert page.locator(".flow-inventory-row").count() == 142
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_filter_narrows_the_rows_to_matches_beyond_the_eight_largest(tmp_path):
    components = [*_twelve(), ("service_legacy", 1)]
    api, html = _open(tmp_path, components)
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_details(page)
        page.locator(".flow-inventory-row").first.wait_for()
        page.locator(".flow-inventory-filter").fill("SERV")
        names = [
            row.get_attribute("data-inventory-component")
            for row in page.locator(".flow-inventory-row").all()
        ]
        assert names == ["service_legacy"]
        page.locator(".flow-inventory-filter").fill("")
        assert page.locator(".flow-inventory-row").count() == 8
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_clicking_a_name_selects_the_component_and_clearing_brings_the_inventory_back(tmp_path):
    api, html = _open(tmp_path, [*_twelve(), ("service_legacy", 1)])
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_details(page)
        page.locator(".flow-inventory-row").first.wait_for()
        page.locator('.flow-inventory-row[data-inventory-component="part11"]').click()
        node = page.locator('[data-uml-id="part11"]')
        assert node.get_attribute("aria-pressed") == "true"
        inspector = page.locator(".flow-inspector")
        assert inspector.locator("h2").inner_text() == "part11"
        assert page.locator(".flow-inventory").count() == 0
        node.focus()
        page.keyboard.press("Escape")
        assert page.locator(".flow-inventory").count() == 1
        assert page.locator(".flow-inventory-row").count() == 8
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_three_components_show_the_list_without_filter_or_show_all(tmp_path):
    api, html = _open(tmp_path, [("alpha", 2), ("beta", 1), ("gamma", 3)])
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_details(page)
        page.locator(".flow-inventory-row").first.wait_for()
        assert page.locator(".flow-inventory-row").count() == 3
        assert page.locator(".flow-inventory-filter").count() == 0
        assert page.get_by_role("button", name=re.compile("Show all")).count() == 0
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_explorer_top_edge_stays_on_the_first_screen_with_five_findings(tmp_path):
    components = [("hub", 1), *[(f"peer{index}", 1) for index in range(5)]]
    api, html = _open(tmp_path, components, hub_imports=True, rule_deciders=("architect",))
    playwright, browser, page = _browser_page(api, html, width=1440, height=900)
    try:
        _open_details(page)
        assert page.locator(".findings-list > li").count() == 5
        page.locator(".flow-inventory-row").first.wait_for()
        top = page.locator(".flow").bounding_box()["y"]
        assert 0 <= top <= 520
    finally:
        browser.close()
        playwright.stop()


def test_all_agent_decisions_are_worded_as_a_draft_awaiting_the_architect(tmp_path):
    result, encoded = _report(
        tmp_path, [("alpha", 1), ("beta", 1)], rule_deciders=("agent", "agent")
    )
    observation = parse_observation(decode_canonical_model(json.loads(encoded)))
    agent, total = agent_decisions(observation)
    assert agent == total > 0
    text = _verdict(_html(result, encoded))
    assert (
        f" · Draft contract: all {total} decisions are by the agent, awaiting the architect" in text
    )
    assert "Agent decisions" not in text


def test_mixed_decisions_keep_the_agent_fraction(tmp_path):
    result, encoded = _report(
        tmp_path, [("alpha", 1), ("beta", 1)], rule_deciders=("agent", "architect")
    )
    observation = parse_observation(decode_canonical_model(json.loads(encoded)))
    agent, total = agent_decisions(observation)
    assert 0 < agent < total
    text = _verdict(_html(result, encoded))
    assert f" · Agent decisions {agent}/{total}" in text
    assert "Draft contract" not in text


@pytest.mark.browser
def test_without_a_rule_the_inventory_line_and_the_explorer_share_the_first_screen(tmp_path):
    """AD-285: nothing declared, so one server-side line comes first; Details stays closed."""
    components = [("hub", 1), *[(f"peer{index}", 1) for index in range(5)]]
    api, html = _open(tmp_path, components, hub_imports=True, intent=False)
    playwright, browser, page = _browser_page(api, html, width=800, height=600)
    try:
        assert page.locator("#inventory-heading").is_visible()
        assert not page.locator(".findings-list").first.is_visible()
        assert page.locator("[data-flow-details-toggle]").get_attribute("aria-expanded") != "true"
        top = page.locator(".flow").bounding_box()["y"]
        assert 0 <= top <= 480
    finally:
        browser.close()
        playwright.stop()


def _card_text(page, component: str) -> tuple[str, str]:
    card = page.locator(f'.flow-nodes [data-uml-id="{component}"]')
    card.wait_for()
    return card.locator(".label").text_content(), card.locator(".meta").text_content()


@pytest.mark.browser
def test_a_card_shows_the_label_and_the_first_responsibility_only(tmp_path):
    """AD-288: the card shows one line of author text; Details lists every responsibility."""
    api = pytest.importorskip("playwright.sync_api")
    output = tmp_path / "out" / "architecture.json"
    assert replay("showcase-card-first-responsibility", output) == 0
    html = output.with_suffix(".report.html").read_text()
    playwright, browser, page = _browser_page(api, html, width=800, height=600)
    try:
        # The snapshot keeps responsibilities sorted, so the first entry is the sorted first.
        label, line = _card_text(page, "COMP-APP")
        assert (label, line) == ("app", "Keep the order rules out of the command line.")
        page.locator('.flow-nodes [data-uml-id="COMP-APP"]').click()
        details = page.locator(".flow-inspector").inner_text()
        assert "Use cases: place and summarise orders." in details
        assert "Keep the order rules out of the command line." in details
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.browser
def test_a_card_without_a_responsibility_shows_no_placeholder(tmp_path):
    """AD-288: no author text, no line: the card never invents one."""
    api, html = _open(tmp_path, [("alpha", 1), ("beta", 1)], intent=False)
    playwright, browser, page = _browser_page(api, html, width=800, height=600)
    try:
        assert _card_text(page, "alpha") == ("alpha", "")
        assert "Not declared" not in page.locator(".flow-nodes").text_content()
    finally:
        browser.close()
        playwright.stop()
