# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Diff projects recorded imports without requiring an optional UML comparison."""

import json

import pytest
from browser_report_support import _browser_page, _open_details
from test_architecture_demo import _prepare_repo
from test_exact_module_ownership import _component, _contract, _rule

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.render.html import render_html


def _import_report(
    tmp_path,
    *,
    imports=1,
    permitted=False,
    same_owner=False,
    unowned=False,
    sibling=False,
    explicit_uml=False,
):
    components = (
        []
        if unowned
        else [
            _component(
                "a",
                ["sample.a", "sample.b"] if same_owner else ["sample.a"],
                requires=[{"component": "b", "rationale": "Read values."}] if permitted else [],
            ),
            *([] if same_owner else [_component("b", ["sample.b"], requires=[])]),
            *([_component("c", ["sample.c"], requires=[])] if sibling else []),
        ]
    )
    for component in components:
        component.update(role="contract", decided_by="agent")
    contract = _contract(components, [_rule("complete_requires", id="NO-UNDECLARED")])
    if explicit_uml:
        contract["schema_version"] = "2.2.0"
        contract["declarations"] = {
            "uml": {
                "schema_version": "1.0.0",
                "entities": [
                    {
                        "id": name + "-module",
                        "kind": "module",
                        "qualified_name": "sample." + name,
                        "parent_id": "COMP-" + name.upper(),
                        "language": "python",
                        "presence": "planned",
                        "responsibilities": ["Own the module."],
                        "provenance": ["fixture"],
                    }
                    for name in ("a", "b")
                ],
                "relationships": [
                    {
                        "id": "planned-import",
                        "kind": "imports",
                        "source_id": "a-module",
                        "target_id": "b-module",
                        "provenance": ["fixture"],
                    }
                ],
            }
        }
    root = _prepare_repo(
        tmp_path,
        {
            "sample/a.py": "from sample.b import value\n" * imports or "value = 0\n",
            "sample/b.py": "value = 1\n",
            **({"sample/c.py": "value = 2\n"} if sibling else {}),
            "contract.json": json.dumps(contract),
        },
    )
    result, encoded = run_report(
        root, config=ScanConfig(("sample",), "sample", "contract.json", "0" * 64), analyzer=observe
    )
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    html = render_html(result, model, repository="sample", architecture_href=None).decode()
    start = html.index('id="flow-data"')
    payload = json.loads(html[html.index(">", start) + 1 : html.index("</script>", start)])
    assert (payload["comparison"] is not None) == explicit_uml
    return html, payload, result


def _payload_html(html, payload):
    start = html.index(">", html.index('id="flow-data"')) + 1
    return html[:start] + json.dumps(payload) + html[html.index("</script>", start) :]


@pytest.mark.parametrize("imports,permitted", [(0, False), (1, False), (3, False), (1, True)])
def test_diff_shows_real_imports_with_original_findings_sites_and_filters(
    tmp_path, imports, permitted
):
    api = pytest.importorskip("playwright.sync_api")
    html, _, result = _import_report(tmp_path, imports=imports, permitted=permitted)
    assert result.declared_rules == ("FAIL" if imports and not permitted else "PASS")
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        raw = page.locator("#flow-data").text_content()
        verdict = page.locator(".verdict-grid").inner_text()
        page.get_by_role("button", name="Diff", exact=True).click()
        edges = page.locator('.flow-edges [data-relationship-kind="imports"]')
        assert edges.count() == bool(imports)
        assert "Core: unavailable" not in page.locator(".flow-legend").inner_text()
        if permitted:
            assert (
                "unlisted observed relationships" not in page.locator(".flow-legend").inner_text()
            )
        if imports:
            assert ("violation" in edges.get_attribute("class")) == (not permitted)
            edges.locator(".hit").press("Enter")
            details = page.locator(".flow-inspector-content").inner_text()
            assert ("NO-UNDECLARED" in details) == (not permitted)
            assert "sample/a.py:1:" in details
            assert details.count("from sample.b import value") == imports
            page.locator(".flow-violations-only").check()
            assert edges.count() == (not permitted)
            page.locator("#flow").get_by_role("button", name="Reset filters", exact=True).click()
            page.locator('.flow-legend [data-relationship-kind="imports"]').click()
            assert edges.count() == 1
        assert page.locator("#flow-data").text_content() == raw
        assert page.locator(".verdict-grid").inner_text() == verdict
        page.get_by_role("button", name="Target", exact=True).click()
        assert page.locator('.flow-edges [data-relationship-kind="imports"]').count() == 0
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_diff_scope_uses_owned_module_children_and_keeps_outside_connection(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    html, _, _ = _import_report(tmp_path)
    playwright, browser, page = _browser_page(api, html)
    try:
        page.get_by_role("button", name="Diff", exact=True).click()
        page.locator('.flow-nodes [data-label="a"]').press("Enter")
        assert page.locator('.flow-nodes [data-uml-kind="module"][data-label="a"]').count() == 1
        edge = page.locator('.flow-edges [data-relationship-kind="imports"]')
        assert edge.count() == 1
        edge.locator(".hit").press("Enter")
        assert "sample/a.py:1:" in page.locator(".flow-inspector-content").inner_text()
        page.locator('.flow-nodes [data-uml-kind="module"][data-label="a"]').dblclick()
        assert page.locator(".flow-breadcrumb").inner_text().endswith("a")
        page.locator(".flow-back").click()
        assert edge.count() == 1
    finally:
        browser.close()
        playwright.stop()


def test_diff_same_owner_import_is_visible_inside_component(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    html, _, _ = _import_report(tmp_path, same_owner=True)
    playwright, browser, page = _browser_page(api, html)
    try:
        page.get_by_role("button", name="Diff", exact=True).click()
        assert page.locator('.flow-edges [data-relationship-kind="imports"]').count() == 0
        page.locator('.flow-nodes [data-label="a"]').press("Enter")
        assert page.locator('.flow-edges [data-relationship-kind="imports"]').count() == 1
    finally:
        browser.close()
        playwright.stop()


def test_diff_unowned_namespace_keeps_internal_import_navigation(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    html, _, _ = _import_report(tmp_path, unowned=True)
    playwright, browser, page = _browser_page(api, html)
    try:
        page.get_by_role("button", name="Diff", exact=True).click()
        assert page.locator('.flow-edges [data-relationship-kind="imports"]').count() == 1
        assert page.locator('.flow-nodes [data-uml-kind="package"]').count() == 2
    finally:
        browser.close()
        playwright.stop()


def test_diff_scope_findings_exclude_unrelated_sibling_and_offer_global_unknowns(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    html, payload, _ = _import_report(tmp_path, sibling=True)
    globals_ = [item for item in payload["findings"] if not item["graph_subject_ids"]]
    assert globals_
    unmapped = {
        **globals_[0],
        "id": "unmapped",
        "title": "Unmapped evidence is retained",
        "graph_subject_ids": ["missing-subject"],
    }
    payload["findings"].append(unmapped)
    globals_.append(unmapped)
    html = _payload_html(html, payload)
    playwright, browser, page = _browser_page(api, html)
    try:
        page.get_by_role("button", name="Diff", exact=True).click()
        page.locator('.flow-nodes [data-label="c"]').press("Enter")
        _open_details(page)
        details = page.locator(".flow-inspector-content")
        assert "NO-UNDECLARED" not in details.inner_text()
        assert globals_[0]["title"] not in details.inner_text()
        details.locator("summary", has_text="Global or unmapped findings").click()
        assert all(item["title"] in details.inner_text() for item in globals_)
        assert "NO-UNDECLARED" not in details.inner_text()
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("reverse", [False, True])
def test_ambiguous_same_depth_membership_does_not_assign_arbitrary_component(tmp_path, reverse):
    api = pytest.importorskip("playwright.sync_api")
    html, payload, _ = _import_report(tmp_path)
    module = next(
        item
        for item in payload["observed"]["entities"]
        if item["kind"] == "module" and item["qualified_name"] == "sample.a"
    )
    memberships = payload["memberships"]
    memberships[1]["module_ids"].append(module["id"])
    if reverse:
        memberships.reverse()
    playwright, browser, page = _browser_page(api, _payload_html(html, payload))
    try:
        page.get_by_role("button", name="Diff", exact=True).click()
        edge = page.locator('.flow-edges [data-relationship-kind="imports"]')
        assert edge.count() == 1
        source = edge.get_attribute("data-uml-source")
        assert source.startswith("observed:")
        assert (
            page.locator(f'.flow-nodes [data-uml-id="{source}"]').get_attribute("data-uml-kind")
            == "module"
        )
    finally:
        browser.close()
        playwright.stop()


def test_diff_deep_hierarchy_uses_memberships_and_keeps_outside_neighbor(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    html, payload, _ = _import_report(tmp_path)
    graph = payload["target"]
    template_entity = graph["entities"][0]
    template_intent = graph["component_intents"][0]
    for item in graph["entities"]:
        item["parent_id"] = "middle"
    for item in graph["component_intents"]:
        item["parent_id"] = "middle"
    for identity, parent in (("middle", "outer"), ("outer", None)):
        graph["entities"].append(
            {**template_entity, "id": identity, "parent_id": parent, "qualified_name": identity}
        )
        graph["component_intents"].append(
            {**template_intent, "component_id": identity, "parent_id": parent, "label": identity}
        )
    playwright, browser, page = _browser_page(api, _payload_html(html, payload))
    try:
        page.get_by_role("button", name="Diff", exact=True).click()
        assert page.locator('.flow-edges [data-relationship-kind="imports"]').count() == 0
        page.locator('.flow-nodes [data-label="outer"]').press("Enter")
        page.locator('.flow-nodes [data-label="middle"]').dblclick()
        assert page.locator('.flow-edges [data-relationship-kind="imports"]').count() == 1
        page.locator('.flow-nodes [data-label="a"]').press("Enter")
        edge = page.locator('.flow-edges [data-relationship-kind="imports"]')
        assert edge.count() == 1
        target = edge.get_attribute("data-uml-target")
        assert target == "COMP-B"
        assert (
            page.locator(f'.flow-nodes [data-uml-id="{target}"]').get_attribute("data-outside")
            == "true"
        )
        edge.locator(".hit").press("Enter")
        assert "NO-UNDECLARED" in page.locator(".flow-inspector-content").inner_text()
    finally:
        browser.close()
        playwright.stop()


def test_diff_repeated_partial_candidate_retains_one_site_and_its_evidence(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    html, payload, _ = _import_report(tmp_path)
    site = next(item for item in payload["observed"]["relationships"] if item["kind"] == "imports")
    site.update(
        candidate_ids=[site["target_id"], site["target_id"]], target_id=None, resolution="partial"
    )
    playwright, browser, page = _browser_page(api, _payload_html(html, payload))
    try:
        page.get_by_role("button", name="Diff", exact=True).click()
        edge = page.locator('.flow-edges [data-relationship-kind="imports"]')
        assert edge.count() == 1
        assert "candidate; not confirmed" in edge.locator(".hit").get_attribute("aria-label")
        edge.locator(".hit").press("Enter")
        details = page.locator(".flow-inspector-content").inner_text()
        assert details.count("from sample.b import value") == 1
        assert "sample/a.py:1:" in details
    finally:
        browser.close()
        playwright.stop()


def test_diff_matched_explicit_uml_import_does_not_duplicate_observed_sites(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    html, payload, _ = _import_report(tmp_path, imports=3, explicit_uml=True)
    assessment = next(
        item
        for item in payload["comparison"]["assessments"]
        if item["subject_id"] == "planned-import"
    )
    assert assessment["status"] == "PASS" and len(assessment["observed_ids"]) == 3
    playwright, browser, page = _browser_page(api, _payload_html(html, payload))
    try:
        page.get_by_role("button", name="Diff", exact=True).click()
        edge = page.locator('.flow-edges [data-relationship-kind="imports"]')
        assert edge.count() == 1
        edge.locator(".hit").press("Enter")
        details = page.locator(".flow-inspector-content").inner_text()
        assert all(f"sample/a.py:{line}:" in details for line in (1, 2, 3))
        assert "NO-UNDECLARED" in details
        assert "violation" in edge.get_attribute("class")
    finally:
        browser.close()
        playwright.stop()
