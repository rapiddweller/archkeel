"""Large inspector lists stay useful without building every evidence row at once."""

import json
import re

import pytest
from browser_report_support import _browser_page
from test_uml_rendering import _open_module, _uml_report, _wait_for_layout


def _expand_observed_sites(html, payload, count=80):
    graph = payload["observed"]
    relationship = graph["relationships"][0]
    evidence = graph["evidence"][0]
    for index in range(count):
        evidence_id = f"EVD-pagination-{index}"
        relationship_id = f"REL-pagination-{index}"
        graph["evidence"].append(
            {**evidence, "id": evidence_id, "excerpt": f"proof excerpt {index}"}
        )
        graph["relationships"].append(
            {
                **relationship,
                "id": relationship_id,
                "evidence_ids": [evidence_id],
            }
        )
    match = re.search(r'(<script[^>]*id="flow-data"[^>]*>)(.*?)(</script>)', html, re.DOTALL)
    assert match
    encoded = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return html[: match.start(2)] + encoded + html[match.end(2) :]


def test_large_relationship_and_source_site_lists_render_incrementally(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    html, payload = _uml_report(tmp_path)
    html = _expand_observed_sites(html, payload)
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        page.locator('.flow-nodes [data-label="core"]').click()
        _wait_for_layout(page)
        inspector = page.locator(".flow-inspector-content")

        relationship_list = inspector.locator(
            "xpath=.//h3[contains(., 'Relationship sites')]/following-sibling::ul[1]"
        )
        source_list = inspector.locator(
            "xpath=.//h3[contains(., 'Source sites')]/following-sibling::ul[1]"
        )
        assert relationship_list.locator("li").count() == 20
        assert source_list.locator("li").count() == 20
        assert inspector.locator("h3").filter(has_text="Relationship sites · 88").count() == 1
        source_heading = inspector.locator("h3").filter(has_text="Source sites ·").inner_text()
        expected_source_sites = int(re.search(r"Source sites · (\d+)", source_heading).group(1))
        assert expected_source_sites > 80
        assert (
            inspector.get_by_role(
                "button", name=re.compile(r"Show next 20 of 88 Relationship sites · 68 remaining")
            ).count()
            == 1
        )
        inspector.get_by_role("button", name="Show all 88 Relationship sites").click()
        assert relationship_list.locator("li").count() == 88
        assert inspector.locator('[data-inspector-list-more="0"]').is_disabled()
        assert inspector.locator('[data-inspector-list-all="0"]').is_disabled()
        while True:
            more = inspector.locator('[data-inspector-list-more="1"]')
            if more.is_disabled():
                break
            more.click()
        assert inspector.locator('[data-inspector-list-all="1"]').is_disabled()
        assert relationship_list.locator("li").count() == 88
        assert source_list.locator("li").count() == expected_source_sites
        assert source_list.locator("pre").all_text_contents().count("proof excerpt 79") == 1

        _open_module(page, "Target")
        page.locator('.flow-nodes [data-label="Client"]').click()
        assert "proof excerpt" not in inspector.inner_text()
        assert not errors
    finally:
        browser.close()
        playwright.stop()
