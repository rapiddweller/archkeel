# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Shared report navigation remains usable without the retired frame renderer."""

import json
from dataclasses import replace
from urllib.parse import parse_qs, urljoin, urlsplit

import pytest
from browser_report_support import _browser_page, _open_details
from test_architecture_demo import _prepare_repo
from test_atlas_report import _atlas
from test_atlas_report import _page as _atlas_page
from test_atlas_report import _result as _atlas_result
from test_module_explore import _sample
from test_report_159_160_e2e_oracle import _variant
from test_target_graph import _nested_repository, _permission_contract
from test_uml_rendering import _open_module, _uml_report

from archkeel.check.report import run_report
from archkeel.cli.config import load_config
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import Relationship
from archkeel.ir.codec import canonical_report_bytes, decode_canonical_model, parse_observation
from archkeel.ir.model import stable_id
from archkeel.render.html import (
    _atlas_document,
    render_architecture_details,
    render_architecture_html,
)


def _physical_target_pages(tmp_path, leaf_modules):
    root, config = _nested_repository(tmp_path)
    inventories = (
        (
            config.contract,
            [{"path": "sample/__init__.py", "responsibility": "Explain the boundary."}],
        ),
        (
            "inside.json",
            [
                {"path": "sample/core.py", "responsibility": "Own the service."},
                {"path": "sample/future.py", "responsibility": "Hold future intent."},
            ],
        ),
        ("leaf.json", leaf_modules),
    )
    for path, modules in inventories:
        raw = json.loads((root / path).read_bytes())
        raw["declarations"] = {} if modules is None else {"modules": modules}
        if path == "inside.json":
            # Equal labels must not collapse distinct component breadcrumbs.
            raw["components"][0]["label"] = "core"
        (root / path).write_text(json.dumps(raw))
    (root / "sample/observed_only.py").write_text("VALUE = 1\n")
    result, architecture = run_report(root, config=config, analyzer=observe)
    assert architecture is not None and not result.diagnostics, result.diagnostics
    index = tmp_path / "architecture.report.html"
    index.write_bytes(
        render_architecture_html(
            result,
            architecture,
            repository="Physical target",
            architecture_href="architecture.json",
        )
    )
    for name, content in render_architecture_details(
        result, architecture, repository="Physical target", architecture_href="architecture.json"
    ).items():
        (tmp_path / name).write_bytes(content)
    return index


@pytest.mark.parametrize("origin", ["", "&origin=declared"])
def test_target_component_detail_without_uml_keeps_component_route(tmp_path, origin):
    api = pytest.importorskip("playwright.sync_api")
    index = _physical_target_pages(tmp_path, [])
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        detail = tmp_path / "architecture.detail.html"
        page.goto(detail.as_uri() + f"?component=ROOT&view=target{origin}&theme=dark")
        query = parse_qs(urlsplit(page.url).query)
        assert query.get("component") == ["ROOT"], page.url
        assert "module" not in query, page.url
        assert "Requested scope unavailable" not in page.locator("body").inner_text()
        _open_details(page)
        details = page.locator(".flow-inspector-content")
        details.get_by_text("Module inventory · 2 planned files", exact=True).click()
        assert "Hold future intent." in details.inner_text()
        assert "inside.json" in details.inner_text()
        for view, button in (("diagram", "As-Is"), ("diff", "Diff"), ("target", "Target")):
            page.get_by_role("button", name=button, exact=True).click()
            query = parse_qs(urlsplit(page.url).query)
            assert query.get("component") == ["ROOT"] and query["view"] == [view]
            assert "module" not in query
            page.reload()
            assert "Requested scope unavailable" not in page.locator("body").inner_text()
        for invalid in (
            "component=missing",
            "component=ROOT&module=missing",
            "component=ROOT&scope=missing",
        ):
            page.goto(detail.as_uri() + f"?{invalid}&view=target&origin=declared")
            assert "Requested scope unavailable" in page.locator("body").inner_text()
            assert page.locator("[data-file-intent]").count() == 0
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize(
    "leaf_modules,label",
    [
        (None, "Not declared"),
        ([], "Explicitly empty"),
        ([{"path": "sample/deep.py", "responsibility": "Own the deep operation."}], None),
    ],
)
def test_target_navigation_exposes_physical_inventories_at_every_level(
    tmp_path, leaf_modules, label
):
    api = pytest.importorskip("playwright.sync_api")
    index = _physical_target_pages(tmp_path, leaf_modules)
    atlas = _atlas(index.read_text())
    assert any(item["path"] == "sample/observed_only.py" for item in atlas["modules"])
    assert not atlas["declared_modules"]
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri() + "?view=target&theme=dark")
        _open_details(page)
        details = page.locator(".flow-inspector-content")
        details.get_by_text("Module inventory · 1 planned file", exact=True).click()
        assert "sample/__init__.py" in details.inner_text()
        assert "Explain the boundary." in details.inner_text()
        assert "contract.json" in details.inner_text()
        assert page.locator('[data-uml-kind="module"]').count() == 0
        page.locator('.flow-nodes [data-uml-id="ROOT"]').press("Enter")
        assert parse_qs(urlsplit(page.url).query)["scope"] == ["ROOT"]
        details.get_by_text("Module inventory · 2 planned files", exact=True).click()
        for text in (
            "sample/core.py",
            "Own the service.",
            "sample/future.py",
            "Hold future intent.",
            "inside.json",
        ):
            assert text in details.inner_text()
        details.get_by_role("link", name="Open declared component details", exact=True).click()
        assert parse_qs(urlsplit(page.url).query)["component"] == ["ROOT"]
        assert page.locator(".flow-breadcrumb a:not([aria-label])").count() == 0
        assert (
            page.locator('.flow-breadcrumb [data-lexical-depth="1"]').inner_text()
            == "core [component]"
        )
        page.get_by_role("link", name="Back to architecture map", exact=True).click()
        query = parse_qs(urlsplit(page.url).query)
        assert query["scope"] == ["ROOT"] and query["view"] == ["target"]
        assert query["theme"] == ["dark"]
        page.locator('.flow-nodes [data-uml-id="core:core"]').press("Enter")
        assert parse_qs(urlsplit(page.url).query)["scope"] == ["core:core"]
        if leaf_modules:
            details.get_by_text("Module inventory · 1 planned file", exact=True).click()
            for text in ("sample/deep.py", "Own the deep operation.", "leaf.json"):
                assert text in details.inner_text()
        else:
            inventory = details.locator(".flow-module-inventory")
            assert label in inventory.inner_text()
            assert ("leaf.json" in inventory.inner_text()) == (leaf_modules == [])
            assert details.locator("[data-file-intent]").count() == 0
        assert "sample/observed_only.py" not in details.inner_text()
        assert page.locator('[data-uml-kind="module"]').count() == 0
        details.get_by_role("link", name="Open declared component details", exact=True).click()
        assert parse_qs(urlsplit(page.url).query)["component"] == ["core:core"]
        breadcrumb = page.locator(".flow-breadcrumb")
        parents = breadcrumb.locator("a:not([aria-label])")
        assert parents.count() == 1
        assert parse_qs(urlsplit(parents.get_attribute("href")).query)["scope"] == ["ROOT"]
        assert parents.inner_text() == "core [component]"
        assert breadcrumb.locator('[data-lexical-depth="1"]').inner_text() == "core [component]"
        detail_url = page.url
        parents.click()
        query = parse_qs(urlsplit(page.url).query)
        assert query["scope"] == ["ROOT"] and query["view"] == ["target"]
        assert query["theme"] == ["dark"]
        page.go_back()
        assert page.url == detail_url
        _open_details(page)
        inventory = details.locator(".flow-module-inventory")
        if leaf_modules:
            inventory.locator("summary").click()
            assert "Own the deep operation." in inventory.inner_text()
        else:
            assert label in inventory.inner_text()
        page.get_by_role("link", name="Back to architecture map", exact=True).click()
        assert parse_qs(urlsplit(page.url).query)["scope"] == ["core:core"]
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_atlas_labels_count_scopes_and_oversized_evidence_without_losing_route_state(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    positive = _sample(
        tmp_path / "positive",
        extra_files={
            "sample/core/helper.py": "def one():\n    return 1\n",
            "sample/core/helper2.py": "def two():\n    return 2\n",
        },
    )
    empty = _sample(tmp_path / "empty")
    unavailable_model = replace(
        empty,
        sections=tuple(section for section in empty.sections if section.name != "dependency_edges"),
    )
    unavailable = _atlas_document(
        _atlas_result(unavailable_model),
        unavailable_model,
        repository="One target",
        architecture_href="architecture.json",
    ).decode()
    assert "oversized_insides" not in _atlas(unavailable)
    cases = (
        (_atlas_page(positive), "1 candidate", "core\t3\t0"),
        (_atlas_page(empty), "no candidates measured", None),
        (unavailable, "UNKNOWN", None),
    )
    for index, (html, claim_label, measurement) in enumerate(cases):
        report = tmp_path / f"atlas-{index}.report.html"
        report.write_text(html)
        errors = []
        playwright, browser, page = _browser_page(api, html, errors=errors)
        try:
            page.goto(f"{report.as_uri()}?view=target&theme=dark")
            assert "whole-contract components" in page.locator(".report-heading").inner_text()
            summary = page.locator(".atlas-summary").inner_text()
            assert "Current level: 2 components" in summary
            assert "agent-authored contract entries (authorship only): 0/2 components" in summary
            claim = page.locator(".atlas-review-claim")
            assert claim.locator("summary").inner_text().endswith(claim_label)
            claim.locator("summary").click()
            if measurement:
                assert measurement in claim.inner_text()
                link = claim.get_by_role("link", name="core")
                link.click()
                query = parse_qs(urlsplit(page.url).query)
                assert query["selected"] == ["core"]
                assert "scope" not in query
                assert (
                    page.locator('.flow-nodes [aria-pressed="true"]').get_attribute("data-uml-id")
                    == "core"
                )
                assert "core" in page.locator(".flow-inspector-content").inner_text()
                assert page.locator('.flow-scope-notice[role="status"]').count() == 0
                assert query["view"] == ["target"]
                assert query["theme"] == ["dark"]
                assert page.locator("html").get_attribute("data-theme") == "dark"
            else:
                assert claim.locator("table").count() == 0
            assert not errors
        finally:
            browser.close()
            playwright.stop()


def test_atlas_unknown_rule_links_its_analyzer_gap_while_failures_remain_visible(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    variant = _variant("class-a-boundary-types-ordinary-reexport-chain-unknown")
    root = _prepare_repo(tmp_path, dict(variant.files), variant.fixture)
    config = load_config(root, variant.config)
    result, architecture = run_report(root, config=config, analyzer=observe)
    assert architecture is not None and result.declared_rules == "UNKNOWN"
    html = render_architecture_html(
        result, architecture, repository="shop", architecture_href="architecture.json"
    ).decode()
    atlas = _atlas(html)
    unknown = next(item for item in atlas["rule_assessments"] if item["status"] == "UNKNOWN")
    assert any(entry["evidence_class"] == "UNKNOWN" for entry in unknown["evidence"])
    component = next(item for item in atlas["components"] if item["label"] in unknown["components"])
    report = tmp_path / "atlas-unknown.report.html"
    report.write_text(html)
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        page.goto(f"{report.as_uri()}?view=diagram&theme=dark")
        assert page.locator('.flow-nodes [data-uml-id="' + component["id"] + '"]').count() == 1
        page.locator('.flow-nodes [data-uml-id="' + component["id"] + '"]').press("Space")
        inspector = page.locator(".flow-inspector-content")
        inspector.locator(".atlas-rule-assessments summary").click()
        assert unknown["id"] in inspector.inner_text()
        assert "unsupported analysis" in inspector.inner_text()
        assert "A contract decision cannot resolve this analysis gap" in inspector.inner_text()
        assert "boundary_type_route" in inspector.inner_text()
        assert (
            inspector.locator(
                '[data-uncertainty-cause="unsupported_analysis"][data-architect-actionable="false"]'
            ).count()
            >= 1
        )
        assert "UNKNOWN" in page.locator(".decision-banner").inner_text()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_atlas_unknown_ownership_gap_points_to_the_required_decision(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    observed = _sample(tmp_path)
    model = replace(
        observed,
        sections=tuple(
            replace(section, records=()) if section.name == "violations" else section
            for section in observed.sections
        ),
    )
    result = replace(_atlas_result(model), declared_rules="UNKNOWN")
    html = render_architecture_html(
        result,
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    ).decode()
    atlas = _atlas(html)
    unknown = next(item for item in atlas["rule_assessments"] if item["status"] == "UNKNOWN")
    assert any(entry["kind"] == "rule_ownership_blocker" for entry in unknown["evidence"])
    component = atlas["components"][0]
    playwright, browser, page = _browser_page(api, html)
    try:
        page.locator(f'.flow-nodes [data-uml-id="{component["id"]}"]').press("Space")
        inspector = page.locator(".flow-inspector-content")
        inspector.locator(".atlas-rule-assessments summary").click()
        assert "rule_ownership_blocker" in inspector.inner_text()
        assert "Assign it to one existing component" in inspector.inner_text()
        assert "missing ownership" in inspector.inner_text()
        assert (
            inspector.locator(
                '[data-uncertainty-cause="missing_ownership"][data-architect-actionable="true"]'
            ).count()
            >= 1
        )
    finally:
        browser.close()
        playwright.stop()


def test_atlas_whole_contract_and_nested_level_counts_have_distinct_scopes(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    root, config = _nested_repository(tmp_path)
    result, architecture = run_report(root, config=config, analyzer=observe)
    assert architecture is not None and result.architecture_projection is not None
    html = render_architecture_html(
        result, architecture, repository="nested", architecture_href="architecture.json"
    ).decode()
    atlas = _atlas(html)
    components = atlas["components"]
    parent = next(
        item for item in components if any(child["parent_id"] == item["id"] for child in components)
    )
    children = [item for item in components if item["parent_id"] == parent["id"]]
    roots = [item for item in components if item["parent_id"] is None]
    report = tmp_path / "nested.report.html"
    report.write_text(html)
    playwright, browser, page = _browser_page(api, html)
    try:
        page.goto(f"{report.as_uri()}?view=target&theme=dark")
        assert (
            f"{len(components)} whole-contract components"
            in page.locator(".report-heading").inner_text()
        )
        root_count = len(roots)
        root_label = "component" if root_count == 1 else "components"
        assert (
            f"Current level: {root_count} {root_label}"
            in page.locator(".atlas-summary").inner_text()
        )
        page.goto(f"{report.as_uri()}?view=target&component={parent['id']}&theme=dark")
        assert (
            f"{len(components)} whole-contract components"
            in page.locator(".report-heading").inner_text()
        )
        child_count = len(children)
        child_label = "component" if child_count == 1 else "components"
        assert (
            f"Current level: {child_count} {child_label}"
            in page.locator(".atlas-summary").inner_text()
        )
    finally:
        browser.close()
        playwright.stop()


def test_atlas_unperformed_check_is_only_a_legend_definition(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    model = _sample(tmp_path)
    result = replace(
        _atlas_result(model),
        observation_complete="UNKNOWN",
        declared_rules="UNKNOWN",
        rule_assessments=None,
    )
    html = render_architecture_html(
        result,
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    ).decode()
    playwright, browser, page = _browser_page(api, html)
    try:
        card = page.locator(".verdict-card").nth(3)
        assert "NOT CHECKED" in card.inner_text()
        assert "Status definition" in card.inner_text()
        assert "A check was not performed or could not be completed" in card.inner_text()
        assert "Count unavailable" not in card.inner_text()
        assert "0 rules" not in card.inner_text()
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("width,height", [(1440, 1000), (375, 844)])
def test_equal_root_diagram_uses_one_viewport_alignment_in_every_architecture_view(
    tmp_path, width, height
):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    playwright, browser, page = _browser_page(api, html, width, height)
    try:
        geometry = []
        for name in ("As-Is", "Target", "Diff", "As-Is"):
            page.get_by_role("button", name=name, exact=True).click()
            card = page.locator('.flow-nodes [data-label="core"] .card')
            assert card.count() == 1
            box = card.bounding_box()
            canvas = page.locator(".flow-canvas").bounding_box()
            geometry.append(
                {
                    "x": box["x"] - canvas["x"],
                    "y": box["y"] - canvas["y"],
                    "width": box["width"],
                    "height": box["height"],
                }
            )
        for box in geometry[1:]:
            assert box == pytest.approx(geometry[0], abs=1)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("width,height", [(1440, 1000), (375, 844)])
def test_architecture_views_are_grouped_separately_from_evidence_views(tmp_path, width, height):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    playwright, browser, page = _browser_page(api, html, width, height)
    try:
        architecture = page.get_by_role("group", name="Architecture diagrams", exact=True)
        evidence = page.get_by_role("group", name="Evidence views", exact=True)
        assert architecture.locator("button").all_text_contents() == ["As-Is", "Target", "Diff"]
        assert evidence.locator("button").all_text_contents() == ["Structure", "Review", "Actual"]
        for name in ("Target", "Diff", "Review", "As-Is"):
            page.get_by_role("button", name=name, exact=True).click()
            assert (
                page.get_by_role("button", name=name, exact=True).get_attribute("aria-pressed")
                == "true"
            )
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
@pytest.mark.parametrize("width,height", [(1440, 1000), (375, 844)])
def test_scope_selection_and_geometry_survive_view_switch_and_resize(tmp_path, view, width, height):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    errors = []
    playwright, browser, page = _browser_page(api, html, width, height, errors)
    try:
        _open_module(page, view)
        payload = page.locator("#flow-data").text_content()
        client = page.locator('.flow-nodes [data-label="Client"]')
        client.click()
        identity = client.get_attribute("data-uml-id")
        scope = page.locator(".flow-breadcrumb").inner_text()
        page.get_by_role("button", name=view, exact=True).click()
        assert client.get_attribute("aria-pressed") == "true"
        page.get_by_role(
            "button", name="Target" if view != "Target" else "As-Is", exact=True
        ).click()
        page.get_by_role("button", name=view, exact=True).click()
        assert page.locator(".flow-breadcrumb").inner_text() == scope
        assert client.get_attribute("data-uml-id") == identity
        assert client.get_attribute("aria-pressed") == "true"
        transform = client.get_attribute("transform")
        page.set_viewport_size({"width": width + 40, "height": height + 60})
        assert client.get_attribute("transform") == transform
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        _open_details(page)
        assert "Client" in page.locator(".flow-inspector-content").inner_text()
        assert (
            client.locator(".label").evaluate("n => getComputedStyle(n).writingMode")
            == "horizontal-tb"
        )
        assert page.locator(".flow-frames [tabindex]").count() == 0
        assert page.locator(".flow-chips [tabindex]").count() == 0
        assert page.locator("#flow-data").text_content() == payload
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_atlas_fail_with_undecided_and_mixed_evidence_keeps_all_actions(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    variant = _variant("class-a-boundary-types-ordinary-reexport-chain-unknown")
    root = _prepare_repo(tmp_path, dict(variant.files), variant.fixture)
    config = load_config(root, variant.config)
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assessment = next(item for item in result.rule_assessments if item.status == "UNKNOWN")
    ownership_model = _sample(tmp_path / "ownership")
    blocker = next(
        item
        for item in ownership_model.records("scope_observations") or ()
        if item.kind == "rule_ownership_blocker"
    )
    sections = tuple(
        replace(
            section,
            records=(
                *section.records,
                replace(
                    blocker,
                    id=stable_id("scope-observation", assessment.id, blocker.id),
                    rule_ids=(assessment.id,),
                ),
            ),
        )
        if section.name == "scope_observations"
        else section
        for section in model.sections
    )
    model = replace(model, sections=sections)
    result = replace(
        result,
        rule_assessments=tuple(
            replace(item, status="FAIL", undecided=1) if item.id == assessment.id else item
            for item in result.rule_assessments
        ),
    )
    html = render_architecture_html(
        result,
        canonical_report_bytes(model),
        repository="shop",
        architecture_href="architecture.json",
    ).decode()
    report = tmp_path / "atlas-mixed-evidence.report.html"
    report.write_text(html)
    playwright, browser, page = _browser_page(api, html)
    try:
        page.goto(f"{report.as_uri()}?theme=dark")
        page.locator(".flow-inspector-content .atlas-rule-assessments summary").click()
        inspector = page.locator(".flow-inspector-content")
        assert assessment.id in inspector.inner_text()
        assert "FAIL" in inspector.inner_text()
        assert "undecided result" in inspector.inner_text()
        assert "unsupported analysis" in inspector.inner_text()
        assert "A contract decision cannot resolve this analysis gap" in inspector.inner_text()
        assert "rule_ownership_blocker" in inspector.inner_text()
        assert "Assign it to one existing component" in inspector.inner_text()
    finally:
        browser.close()
        playwright.stop()


def test_atlas_nested_rule_scope_link_uses_parent_identity_with_duplicate_labels(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    root, config = _nested_repository(tmp_path)
    inside_path = root / "inside.json"
    inside = json.loads(inside_path.read_text())
    inside["components"][0]["label"] = "core"
    inside_path.write_text(json.dumps(inside))
    result, architecture = run_report(root, config=config, analyzer=observe)
    assert architecture is not None
    assessment = next(item for item in result.rule_assessments if item.id == "core:layout")
    result = replace(
        result,
        rule_assessments=tuple(
            replace(item, status="UNKNOWN", undecided=1) if item.id == assessment.id else item
            for item in result.rule_assessments
        ),
    )
    html = render_architecture_html(
        result, architecture, repository="nested", architecture_href="architecture.json"
    ).decode()
    atlas = _atlas(html)
    parent = next(
        item
        for item in atlas["components"]
        if item["label"] == "core" and item["parent_id"] is None
    )
    child = next(
        item
        for item in atlas["components"]
        if item["label"] == "core" and item["parent_id"] == parent["id"]
    )
    report = tmp_path / "atlas-nested-rule.report.html"
    report.write_text(html)
    playwright, browser, page = _browser_page(api, html)
    try:
        page.goto(f"{report.as_uri()}?theme=dark")
        page.locator(f'.flow-nodes [data-uml-id="{parent["id"]}"]').press("Space")
        rules = page.locator(".flow-inspector-content .atlas-rule-assessments")
        rules.locator("summary").click()
        row = rules.locator("li").filter(has=page.locator("code", has_text="core:layout")).first
        scope = row.get_by_role("link", name="core", exact=True).first
        affected = row.get_by_role("link", name="core:core", exact=True)
        assert parse_qs(urlsplit(scope.get_attribute("href")).query)["scope"] == [parent["id"]]
        assert parse_qs(urlsplit(affected.get_attribute("href")).query)["scope"] == [child["id"]]
        page.evaluate("window.navigationSentinel = 42")
        affected.click()
        query = parse_qs(urlsplit(page.url).query)
        assert query["scope"] == [child["id"]]
        assert page.evaluate("window.navigationSentinel") == 42
        assert page.locator("html").get_attribute("data-theme") == "dark"
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("reject", [False, True])
@pytest.mark.parametrize("width", [375, 1024])
def test_fullscreen_fallback_restores_scope_selection_focus_and_scroll(tmp_path, reject, width):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    errors = []
    playwright, browser, page = _browser_page(api, html, width=width, height=844, errors=errors)
    try:
        _open_module(page, "Target")
        page.locator('.flow-nodes [data-label="Client"]').click()
        before = page.locator(".flow-breadcrumb").inner_text()
        selected = page.locator('.flow-nodes [aria-pressed="true"]').get_attribute("data-uml-id")
        page.evaluate("window.scrollTo(0, 100)")
        page.evaluate(
            """reject => {
          Element.prototype.requestFullscreen = reject
            ? async () => { throw new DOMException('embedding denied', 'NotAllowedError'); }
            : undefined;
        }""",
            reject,
        )
        page.locator(".flow-fullscreen").scroll_into_view_if_needed()
        scroll = page.evaluate("window.scrollY")
        page.locator(".flow-fullscreen").click()
        assert page.locator("#flow").get_attribute("data-expanded") == "fallback"
        assert page.locator("#flow").get_attribute("aria-modal") == "true"
        bounds = page.locator(".flow-canvas").bounding_box()
        assert bounds and bounds["height"] >= 200
        page.keyboard.press("Escape")
        assert page.locator("#flow").get_attribute("data-expanded") is None
        assert page.locator("#flow").get_attribute("aria-modal") is None
        assert page.locator(".flow-breadcrumb").inner_text() == before
        assert (
            page.locator('.flow-nodes [aria-pressed="true"]').get_attribute("data-uml-id")
            == selected
        )
        assert page.evaluate("window.scrollY") == scroll
        assert page.locator(".flow-fullscreen").evaluate("n => n === document.activeElement")
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("reject", [False, True])
def test_atlas_fullscreen_uses_available_canvas_and_background_drag_pans(tmp_path, reject):
    api = pytest.importorskip("playwright.sync_api")
    html = _atlas_page(_sample(tmp_path))
    playwright, browser, page = _browser_page(api, html, width=1440, height=800)
    try:
        canvas = page.locator(".flow-canvas")
        normal_height = canvas.bounding_box()["height"]
        page.set_viewport_size({"width": 1440, "height": 1000})
        resized_height = canvas.bounding_box()["height"]
        assert resized_height >= normal_height + 100
        page.evaluate(
            """reject => {
          Element.prototype.requestFullscreen = reject
            ? async () => { throw new DOMException('embedding denied', 'NotAllowedError'); }
            : Element.prototype.requestFullscreen;
        }""",
            reject,
        )
        page.locator(".flow-fullscreen").click()
        page.locator("#flow[data-expanded]").wait_for()
        page.wait_for_timeout(100)
        bounds = canvas.bounding_box()
        assert bounds and bounds["height"] > resized_height + 50
        graph = page.locator(".flow-graph")
        assert graph.evaluate("n => getComputedStyle(n).cursor") == "grab"
        before = page.locator(".flow-viewport").get_attribute("transform")
        x, y = bounds["x"] + bounds["width"] - 20, bounds["y"] + bounds["height"] - 20
        page.mouse.move(x, y)
        page.mouse.down()
        assert graph.evaluate("n => getComputedStyle(n).cursor") == "grabbing"
        page.mouse.move(x - 45, y - 35, steps=4)
        page.mouse.up()
        assert page.locator(".flow-viewport").get_attribute("transform") != before
        assert graph.evaluate("n => getComputedStyle(n).cursor") == "grab"
        node_count = page.locator(".flow-nodes [data-label]").count()
        edge_count = page.locator(".flow-edges .line").count()
        zoom = page.locator(".flow-zoom-value").inner_text()
        first_node = page.locator(".flow-nodes [data-label]").first
        first_node_width = first_node.bounding_box()["width"]
        page.get_by_role("button", name="Zoom in").click()
        assert page.locator(".flow-zoom-value").inner_text() != zoom
        assert first_node.bounding_box()["width"] > first_node_width
        page.get_by_role("button", name="Fit overview").click()
        assert page.locator(".flow-viewport").get_attribute("transform") is None
        page.locator(".flow-fullscreen").click()
        page.locator("#flow:not([data-expanded])").wait_for()
        assert page.locator(".flow-nodes [data-label]").count() == node_count
        assert page.locator(".flow-edges .line").count() == edge_count
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
def test_native_card_drag_reroutes_all_hits_and_keeps_architecture_unchanged(tmp_path, view):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_module(page, view)
        page.locator(".flow-toolbar").get_by_role(
            "button", name="Reset filters", exact=True
        ).click()
        canvas = page.locator(".flow-canvas")
        canvas.scroll_into_view_if_needed()
        payload = page.locator("#flow-data").text_content()
        card = page.locator('.flow-nodes [data-label="Client"]')
        box = card.bounding_box()
        before = card.get_attribute("transform")
        assert box
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + 40, y + 30, steps=4)
        page.mouse.up()
        assert card.get_attribute("transform") != before
        assert page.locator(".flow-edges .line").count()
        assert page.locator(".flow-edges .edge").evaluate_all("""edges => edges.every(edge =>
          edge.querySelector('.line').getAttribute('d')
          === edge.querySelector('.hit').getAttribute('d')
          && getComputedStyle(edge.querySelector('.line')).markerEnd !== 'none')""")
        page.get_by_role("button", name="Fit overview").click()
        assert page.locator("#flow-data").text_content() == payload
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
@pytest.mark.parametrize("zoom_steps", [0, 2, 4])
def test_left_up_drag_keeps_other_cards_fixed_and_small_scope_starts_unscrolled(
    tmp_path, view, zoom_steps
):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        _open_module(page, view)
        page.locator(".flow-toolbar").get_by_role(
            "button", name="Reset filters", exact=True
        ).click()
        for _ in range(zoom_steps):
            page.get_by_role("button", name="Zoom in", exact=True).click()
        payload = page.locator("#flow-data").text_content()
        client = page.locator('.flow-nodes [data-label="Client"]')
        other = page.locator('.flow-nodes [data-label="Other"]')
        canvas = page.locator(".flow-canvas")
        canvas.scroll_into_view_if_needed()
        before = client.get_attribute("transform")
        anchor = other.bounding_box()
        box = client.bounding_box()
        viewport = canvas.bounding_box()
        assert anchor and box and viewport
        page.mouse.move(box["x"] + 40, box["y"] + 35)
        page.mouse.down()
        page.mouse.move(viewport["x"] + 8, viewport["y"] + 8, steps=32)
        page.mouse.up()
        assert client.get_attribute("transform") != before
        after = other.bounding_box()
        assert after
        assert abs(after["x"] - anchor["x"]) < 1
        assert abs(after["y"] - anchor["y"]) < 1
        assert page.locator(".flow-edges .edge").evaluate_all("""edges => edges.every(edge =>
          edge.querySelector('.line').getAttribute('d')
          === edge.querySelector('.hit').getAttribute('d')
          && getComputedStyle(edge.querySelector('.line')).markerEnd !== 'none')""")
        client.press("Space")
        for _ in range(4):
            page.get_by_role("button", name="Zoom in", exact=True).click()
        scroll = canvas.evaluate(
            """n => {
                n.scrollLeft=n.scrollWidth;
                n.scrollTop=n.scrollHeight;
                return [n.scrollLeft,n.scrollTop];
            }"""
        )
        assert max(scroll) > 0
        page.get_by_role("button", name="Open selected Client", exact=True).click()
        assert canvas.evaluate("n => [n.scrollLeft,n.scrollTop]") == [0, 0]
        assert page.locator('.flow-nodes [data-uml-kind="method"]').count() > 0
        assert page.locator("#flow-data").text_content() == payload
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
@pytest.mark.parametrize("input_method", ["mouse", "keyboard"])
@pytest.mark.parametrize("width", [375, 1000])
def test_opening_details_reveals_selected_card_without_changing_scene(
    tmp_path, view, input_method, width
):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    errors = []
    playwright, browser, page = _browser_page(api, html, width=width, height=1000, errors=errors)
    try:
        _open_module(page, view)
        details = page.locator(".flow-details-toggle")
        if details.get_attribute("aria-expanded") == "true":
            details.click()
        page.get_by_role("button", name="Fit overview", exact=True).click()
        cards = page.locator(".flow-nodes [data-uml-id]")
        rightmost = max(range(cards.count()), key=lambda i: cards.nth(i).bounding_box()["x"])
        card = cards.nth(rightmost)
        card.focus()
        scene = page.locator(".flow-nodes [data-uml-id]").evaluate_all(
            "nodes => nodes.map(n => [n.dataset.umlId,n.getAttribute('transform')])"
        )
        routes = page.locator(".flow-edges .line").evaluate_all(
            "edges => edges.map(e => e.getAttribute('d'))"
        )
        zoom = page.locator(".flow-zoom-value").inner_text()
        payload = page.locator("#flow-data").text_content()
        if input_method == "mouse":
            card.click()
        else:
            card.press("Space")
        assert details.get_attribute("aria-expanded") == "true"
        bounds = card.bounding_box()
        viewport = page.locator(".flow-canvas").bounding_box()
        assert bounds and viewport
        assert bounds["x"] >= viewport["x"] - 1
        assert bounds["x"] + bounds["width"] <= viewport["x"] + viewport["width"] + 1
        assert bounds["y"] >= viewport["y"] - 1
        assert bounds["y"] + bounds["height"] <= viewport["y"] + viewport["height"] + 1
        assert page.locator(".flow-zoom-value").inner_text() == zoom
        assert (
            page.locator(".flow-nodes [data-uml-id]").evaluate_all(
                "nodes => nodes.map(n => [n.dataset.umlId,n.getAttribute('transform')])"
            )
            == scene
        )
        assert (
            page.locator(".flow-edges .line").evaluate_all(
                "edges => edges.map(e => e.getAttribute('d'))"
            )
            == routes
        )
        assert page.locator("#flow-data").text_content() == payload
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
def test_keyboard_back_restores_the_open_component(tmp_path, view):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_module(page, view)
        client = page.locator('.flow-nodes [data-label="Client"]')
        client.focus()
        client.press("Enter")
        page.locator(".flow-back").click()
        assert client.is_visible()
        assert client.evaluate("n => n === document.activeElement")
        client.press("Space")
        assert client.get_attribute("aria-pressed") == "true"
        client.press("Escape")
        assert client.get_attribute("aria-pressed") == "false"
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("touch", [False, True])
def test_blocked_route_keeps_accessible_warning_endpoints_and_evidence(tmp_path, touch):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(
        tmp_path,
        extra_target_relationships=(
            Relationship(
                "reference", "references", "client", "other", provenance=("docs/target.md",)
            ),
        ),
    )
    playwright, browser, page = _browser_page(api, html, has_touch=touch)
    try:
        _open_module(page, "Target")
        page.locator(".flow-toolbar").get_by_role(
            "button", name="Reset filters", exact=True
        ).click()
        page.locator(".flow-canvas").scroll_into_view_if_needed()
        payload = page.locator("#flow-data").text_content()
        for label, dx, dy in (("Base", 10, 20), ("Port", -10, -20)):
            client = page.locator('.flow-nodes [data-label="Client"] .card').bounding_box()
            blocker = page.locator(f'.flow-nodes [data-label="{label}"] .card').bounding_box()
            assert client and blocker
            x, y = blocker["x"] + 40, blocker["y"] + 35
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(
                x + client["x"] - blocker["x"] + dx, y + client["y"] - blocker["y"] + dy, steps=4
            )
            page.mouse.up()
        warnings = page.locator(".flow-edges .hit[data-route-warning]")
        assert warnings.count() > 0
        assert "routing warnings" in page.locator(".flow-legend").inner_text()
        edge = page.locator(
            '.flow-edges [data-relationship-kind="references"] .hit[data-route-warning]'
        )
        assert edge.count() == 1
        assert "architectural status is unchanged" in edge.get_attribute("aria-label")
        assert edge.get_attribute("d") == edge.locator("..").locator(".line").get_attribute("d")
        edge.press("Enter")
        assert (
            "Renderer layout warning"
            in page.locator(".flow-inspector-content [role=status]").inner_text()
        )
        assert page.locator("#flow-data").text_content() == payload
        if touch:
            point = edge.evaluate("""node => {
              const matrix = node.getScreenCTM(), length = node.getTotalLength();
              for (let fraction = .1; fraction < .95; fraction += .05) {
                const point = node.getPointAtLength(length * fraction).matrixTransform(matrix);
                if (document.elementFromPoint(point.x, point.y)?.closest('.hit') === node)
                  return {x: point.x, y: point.y};
              }
              return null;
            }""")
            assert point
            page.touchscreen.tap(point["x"], point["y"])
            assert edge.get_attribute("aria-pressed") == "true"
            assert "Renderer layout warning" in page.locator(".flow-inspector-content").inner_text()
            assert page.locator("#flow-data").text_content() == payload
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_mobile_check_wraps_long_failure_identity_without_changing_result(scheme):
    from dataclasses import replace

    from test_html_report import FAILED_CHECK

    from archkeel.render.html import render_check_html

    api = pytest.importorskip("playwright.sync_api")
    identity = "8ef830a60aba1c9fee50741b004956eafcfe09cf614f86c77ddf48971c36505b"
    result = replace(FAILED_CHECK, failures=(f"guardrail changed unknowns fingerprint {identity}",))
    html = render_check_html(result, repository="sample", result_href="result.json").decode()
    playwright, browser, page = _browser_page(api, html, width=375, height=844)
    try:
        page.emulate_media(color_scheme=scheme)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert page.locator(".failure-list code").inner_text().endswith(identity)
        assert (
            page.locator(".verdict-card")
            .filter(has=page.locator(".verdict-key", has_text="expectation_fulfilled"))
            .get_attribute("data-verdict")
            == "fail"
        )
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_native_theme_keeps_target_cards_readable_and_evidence_unchanged(tmp_path, scheme):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path)
    errors = []
    playwright, browser, page = _browser_page(api, html, width=375, height=844, errors=errors)
    try:
        page.emulate_media(color_scheme=scheme)
        before = page.locator("#flow-data").text_content()
        assert page.evaluate("getComputedStyle(document.documentElement).colorScheme") == scheme
        _open_module(page, "Target")
        page.locator('.flow-nodes [data-label="Client"]').click()
        colors = page.locator(".flow-nodes .node").evaluate_all(r"""nodes => {
          const rgb = s => s.match(/[\d.]+/g).slice(0,3).map(Number);
          const luminance = c => c.map(v => {v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4})
            .reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
          const contrast = (a,b) => (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
          return nodes.filter(n => n.getBoundingClientRect().width).map(n => {
            const label=n.querySelector('.label'), card=n.querySelector('.card');
            return contrast(luminance(rgb(getComputedStyle(label).fill)),
              luminance(rgb(getComputedStyle(card).fill)));
          });
        }""")
        assert colors and min(colors) >= 4.5
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert page.locator("#flow-data").text_content() == before
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("component_labels", [(), ("core", "peer")])
def test_atlas_rule_scope_and_components_have_distinct_native_routes(tmp_path, component_labels):
    api = pytest.importorskip("playwright.sync_api")
    root, config = _nested_repository(tmp_path)
    contract_path = root / config.contract
    contract_path.write_text(
        json.dumps(_permission_contract(json.loads(contract_path.read_text())))
    )
    result, architecture = run_report(root, config=config, analyzer=observe)
    assert architecture is not None
    root_rule = next(item for item in result.rule_assessments if item.scope == "root")
    nested_rule = next(item for item in result.rule_assessments if item.id == "core:layout")
    result = replace(
        result,
        rule_assessments=(
            replace(root_rule, status="UNKNOWN", components=component_labels),
            replace(nested_rule, status="UNKNOWN", components=()),
        ),
    )
    html = render_architecture_html(
        result, architecture, repository="nested", architecture_href="architecture.json"
    ).decode()
    atlas = _atlas(html)
    root_row, nested_row = atlas["rule_assessments"]
    assert root_row["scope_id"] is None
    assert len(root_row["component_ids"]) == len(component_labels)
    assert nested_row["scope_id"] == "ROOT"
    assert nested_row["component_ids"] == []
    report = tmp_path / "routes.report.html"
    report.write_text(html)
    playwright, browser, page = _browser_page(api, html)
    try:
        page.goto(f"{report.as_uri()}?theme=dark&view=diagram")
        page.locator('.flow-nodes [data-uml-id="ROOT"]').press("Space")
        rules = page.locator(".flow-inspector-content .atlas-rule-assessments")
        rules.locator("summary").click()
        links = rules.get_by_role("link", name="root", exact=True)
        assert links.count() >= 1
        for link in links.all():
            query = parse_qs(urlsplit(link.get_attribute("href")).query)
            assert "scope" not in query and "component" not in query
            assert query["theme"] == ["dark"] and query["view"] == ["diagram"]
        link = rules.get_by_role("link", name="core", exact=True).last
        assert parse_qs(urlsplit(link.get_attribute("href")).query)["scope"] == ["ROOT"]
        page.evaluate("""document.querySelector('main').addEventListener('click', event => {
            if (!event.isTrusted) {
                window.routePrevented = event.defaultPrevented;
                event.preventDefault();
            }
        })""")
        for options in ({"ctrlKey": True}, {"metaKey": True}, {"button": 1}):
            link.evaluate(
                "(node, options) => node.dispatchEvent(new MouseEvent('click', "
                "{bubbles: true, cancelable: true, ...options}))",
                options,
            )
            assert page.evaluate("window.routePrevented") is False
        page.evaluate("window.navigationSentinel = 42")
        link.click()
        assert parse_qs(urlsplit(page.url).query)["scope"] == ["ROOT"]
        assert page.evaluate("window.navigationSentinel") == 42
    finally:
        browser.close()
        playwright.stop()


def test_atlas_component_routes_select_leafs_and_open_inside_scopes(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    root, config = _nested_repository(tmp_path)
    contract_path = root / config.contract
    contract = json.loads(contract_path.read_text())
    contract["components"].append(_permission_contract()["components"][1])
    contract_path.write_text(json.dumps(contract))
    result, architecture = run_report(root, config=config, analyzer=observe)
    assert architecture is not None
    html = render_architecture_html(
        result, architecture, repository="nested", architecture_href="architecture.json"
    ).decode()
    atlas = _atlas(html)
    root_leaf = next(item for item in atlas["components"] if item["id"] == "PEER")
    nested_leaf = next(
        item
        for item in atlas["components"]
        if item["parent_id"]
        and not any(child["parent_id"] == item["id"] for child in atlas["components"])
    )
    inside = next(
        item
        for item in atlas["components"]
        if any(child["parent_id"] == item["id"] for child in atlas["components"])
    )
    report = tmp_path / "atlas-leaf-routes.report.html"
    report.write_text(html)
    playwright, browser, page = _browser_page(api, html)
    try:
        page.goto(f"{report.as_uri()}?theme=dark")
        page.evaluate("""() => {
            const link = document.createElement('a');
            link.href = '#'; link.dataset.atlasComponentRoute = ''; link.textContent = 'root';
            document.querySelector('main').append(link);
        }""")
        page.evaluate("window.navigationSentinel = 42")
        page.get_by_role("link", name="root", exact=True).click()
        assert "scope" not in parse_qs(urlsplit(page.url).query)
        assert page.evaluate("window.navigationSentinel") == 42
        assert page.locator('.flow-scope-notice[role="status"]').count() == 0
        for component in (root_leaf, nested_leaf, inside):
            page.evaluate(
                """id => {
                const link = document.createElement('a');
                link.href = '#'; link.dataset.atlasComponentRoute = id; link.textContent = id;
                document.querySelector('main').append(link);
            }""",
                component["id"],
            )
            page.get_by_role("link", name=component["id"], exact=True).last.click()
            query = parse_qs(urlsplit(page.url).query)
            assert page.locator('.flow-scope-notice[role="status"]').count() == 0
            inspector = page.locator(".flow-inspector-content")
            assert component["label"] in inspector.inner_text()
            if component in (root_leaf, nested_leaf):
                assert (
                    page.locator('.flow-nodes [aria-pressed="true"]').get_attribute("data-uml-id")
                    == component["id"]
                )
                assert query["selected"] == [component["id"]]
                if component["parent_id"]:
                    assert query["scope"] == [component["parent_id"]]
                else:
                    assert "scope" not in query
            else:
                assert query["scope"] == [component["id"]]
                assert "selected" not in query
            href = page.get_by_role("link", name=component["id"], exact=True).last.get_attribute(
                "href"
            )
            assert parse_qs(urlsplit(href).query) == query
            page.goto(urljoin(page.url, href))
            assert page.locator('.flow-scope-notice[role="status"]').count() == 0
            assert component["label"] in page.locator(".flow-inspector-content").inner_text()
            if component in (root_leaf, nested_leaf):
                assert (
                    page.locator('.flow-nodes [aria-pressed="true"]').get_attribute("data-uml-id")
                    == component["id"]
                )
    finally:
        browser.close()
        playwright.stop()


def test_atlas_uncertainty_preview_is_bounded_and_excludes_success_receipts(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    model = _sample(tmp_path)
    blocker = next(
        record
        for record in model.records("scope_observations")
        if record.kind == "rule_ownership_blocker"
    )
    copies = tuple(
        replace(blocker, id=stable_id("scope-observation", blocker.id, str(index)))
        for index in range(12)
    )
    model = replace(
        model,
        sections=tuple(
            replace(section, records=(*section.records, *copies))
            if section.name == "scope_observations"
            else replace(section, records=())
            if section.name == "violations"
            else section
            for section in model.sections
        ),
    )
    html = _atlas_page(model)
    atlas = _atlas(html)
    row = next(item for item in atlas["rule_assessments"] if item["id"] == blocker.rule_ids[0])
    assert row["evidence_count"] == 13
    assert len(row["evidence"]) == 5
    assert all(item["kind"] == "rule_ownership_blocker" for item in row["evidence"])
    playwright, browser, page = _browser_page(api, html)
    try:
        page.locator('.flow-nodes [data-uml-id="core"]').press("Space")
        rules = page.locator(".flow-inspector-content .atlas-rule-assessments")
        rules.locator("summary").click()
        assert "5 of 13 records" in rules.inner_text()
        assert "Complete evidence in architecture JSON" in rules.inner_text()
        assert "rule_evaluation" not in rules.inner_text()
    finally:
        browser.close()
        playwright.stop()


def test_atlas_incomplete_execution_keeps_evidence_action_separate_from_intent(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    observed = _sample(tmp_path)
    model = replace(
        observed,
        coverage=replace(
            observed.coverage, status="FAIL", files_parsed=0, ast_coverage_percent=0.0
        ),
    )
    result = _atlas_result(model)
    result = replace(
        result,
        observation_complete="UNKNOWN",
        declared_rules="UNKNOWN",
        rule_assessments=tuple(replace(item, status="UNKNOWN") for item in result.rule_assessments),
    )
    html = render_architecture_html(
        result,
        canonical_report_bytes(model),
        repository="partial",
        architecture_href="architecture.json",
    ).decode()
    atlas = _atlas(html)
    assert any(
        action["cause"] == "incomplete_execution" and action["architect_actionable"] is False
        for row in atlas["rule_assessments"]
        for action in row["uncertainty_actions"]
    )
    playwright, browser, page = _browser_page(api, html)
    try:
        page.locator(".flow-inspector-content .atlas-rule-assessments summary").click()
        inspector = page.locator(".flow-inspector-content")
        assert "Complete source observation before judging this rule" in inspector.inner_text()
        assert (
            inspector.locator(
                '[data-uncertainty-cause="incomplete_execution"][data-architect-actionable="false"]'
            ).count()
            >= 1
        )
    finally:
        browser.close()
        playwright.stop()
