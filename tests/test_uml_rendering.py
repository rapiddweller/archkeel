# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The report draws independent source and Target graphs through one UML boundary."""

import json
from dataclasses import asdict

import pytest
from browser_report_support import _browser_page, _open_details
from test_target_graph import _nested_repository, _permission_contract
from test_uml_evaluation import _repository

from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import (
    Entity,
    Parameter,
    Relationship,
    Signature,
    TargetDefinition,
    TargetScope,
    Visibility,
)
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.graph_codec import parse_comparison, parse_graph
from archkeel.render.html import render_html


def _uml_report(
    tmp_path,
    *,
    mismatch=False,
    extra_source="",
    extra_files=None,
    component_changes=None,
    declaration_changes=None,
    rules=(),
    closed_relationships=(),
    extra_target_entities=(),
    extra_target_relationships=(),
):
    provenance = ("docs/target.md",)

    def entity(identity, kind, suffix, parent, **details):
        return Entity(
            identity,
            kind,
            "sample.core" + suffix,
            "python",
            parent_id=parent,
            presence="planned",
            responsibilities=("Own " + identity,),
            provenance=provenance,
            **details,
        )

    signature = Signature(
        (
            Parameter("self", kind="positional", default_known=True),
            Parameter("value", "int", "positional", default_known=True),
        ),
        "str",
    )
    target = TargetDefinition(
        entities=(
            entity("module", "module", "", "core"),
            entity("port", "interface", ".Port", "module"),
            entity("base", "class", ".Base", "module"),
            entity("client", "class", ".Client", "module"),
            entity("other", "class", ".Other", "module"),
            entity(
                "port-run",
                "method",
                ".Port.run",
                "port",
                signature=signature,
                visibility=Visibility("public", "declared"),
            ),
            entity(
                "client-run",
                "method",
                ".Client.run",
                "client",
                signature=signature,
                visibility=Visibility("public", "declared"),
            ),
            entity(
                "token",
                "attribute",
                ".Client._token",
                "client",
                annotation="str",
                visibility=Visibility("private", "declared"),
            ),
            *((entity("missing", "class", ".Missing", "module"),) if mismatch else ()),
            *extra_target_entities,
        ),
        relationships=(
            Relationship("extends", "inherits", "client", "base", provenance=provenance),
            Relationship("implements", "realizes", "client", "port", provenance=provenance),
            *extra_target_relationships,
        ),
        scopes=(
            (
                TargetScope(
                    "module",
                    "closed",
                    "Keep relationships explicit.",
                    provenance,
                    relationship_kinds=closed_relationships,
                ),
            )
            if closed_relationships
            else ()
        )
        + (
            (
                TargetScope(
                    "module",
                    "closed",
                    "Keep the classifier boundary explicit",
                    provenance,
                    entity_kinds=("class", "interface"),
                ),
            )
            if mismatch
            else ()
        ),
    )
    contract = {
        "schema_version": "2.2.0",
        "rules": list(rules),
        "components": [
            {
                "id": "core",
                "label": "core",
                "role": "component",
                "packages": ["sample.core"],
                "namespace": "sample.core",
                "responsibilities": ["Own classifiers"],
                "forbidden_responsibilities": [],
                "provenance": list(provenance),
            }
        ],
        "declarations": {"uml": asdict(target)},
    }
    contract["components"][0].update(component_changes or {})
    contract["declarations"].update(declaration_changes or {})
    source = (
        "from typing import Protocol\nclass Port(Protocol):\n"
        " def run(self, value: int) -> str: ...\nclass Base: pass\n"
        "class Other: pass\nclass Client(Base, Port):\n _token: str\n"
        " def run(self, value: int) -> str:\n  return str(value)\n"
    )
    if mismatch:
        source = source.replace(
            "def run(self, value: int) -> str:\n", "def run(self, value: int) -> int:\n"
        )
        source += "class Extra: pass\n"
    source += extra_source
    root, config = _repository(tmp_path, contract=contract, source=source)
    for path, contents in (extra_files or {}).items():
        (root / path).write_text(contents)
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics, result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    page = render_html(
        result, model, repository="sample", architecture_href="architecture.json"
    ).decode()
    start = page.index('id="flow-data"')
    payload = json.loads(page[page.index(">", start) + 1 : page.index("</script>", start)])
    return page, payload


@pytest.mark.parametrize("public,description", [(None, "Not declared"), ([], "Explicitly empty")])
def test_shared_component_card_and_details_preserve_role_and_api_intent(
    tmp_path, public, description
):
    api = pytest.importorskip("playwright.sync_api")
    changes = {"role": "foundation", "planned": ["sample.core:Future"], "decided_by": "architect"}
    if public is not None:
        changes["public"] = public
    html, _ = _uml_report(tmp_path, component_changes=changes)
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        page.locator('[data-flow-view="target"]').click()
        card = page.locator('[data-uml-id="core"]')
        assert "foundation" in card.text_content()
        card.click()
        details = page.locator(".flow-inspector-content").inner_text()
        assert "Component role" in details and "foundation" in details
        assert "Published API" in details and description in details
        assert "Planned interface (proposed)" in details and "sample.core:Future" in details
        assert "architect" in details and "sample.core" in details
        assert "Language visibility" not in details
        assert page.locator('[data-uml-id="sample.core:Future"]').count() == 0
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("modules,label", [(None, "Not declared"), ([], "Explicitly empty")])
def test_standard_target_details_distinguish_absent_and_empty_module_inventory(
    tmp_path, modules, label
):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(
        tmp_path, declaration_changes={} if modules is None else {"modules": modules}
    )
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        page.locator('[data-flow-view="target"]').click()
        if not page.locator(".flow-inspector-content").is_visible():
            page.locator("[data-flow-details-toggle]").click()
        details = page.locator(".flow-inspector-content").inner_text()
        assert "Module inventory" in details and label in details
        assert "Permitted package layout" in details and "Not declared" in details
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_standard_target_shows_file_intent_and_layout_permissions_without_ghost_cards(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    modules = [
        {"path": "src/sample/core.py", "responsibility": "Own the domain."},
        {"path": "src/sample/future.py", "responsibility": "Keep independent future intent."},
    ]
    rules = [
        {
            "id": "layout",
            "kind": "root_layout",
            "root": "sample",
            "allowed_children": ["sample.core", "sample.future"],
            "rationale": "Limit the immediate packages.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        }
    ]
    html, payload = _uml_report(tmp_path, declaration_changes={"modules": modules}, rules=rules)
    target = parse_graph(payload["target"])
    assert len(target.module_inventories) == 1 and len(target.layout_rules) == 1
    assert not any(item.qualified_name == "sample.future" for item in target.entities)
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        for view in ("target", "diff"):
            page.locator(f'[data-flow-view="{view}"]').click()
            details = page.locator(".flow-inspector-content")
            if not details.is_visible():
                page.locator("[data-flow-details-toggle]").click()
            details.get_by_text("Module inventory · 2 planned files", exact=True).click()
            details.get_by_text("Permitted package layout · 1 rule", exact=True).click()
            text = details.inner_text()
            for expected in (
                "src/sample/future.py",
                "Keep independent future intent.",
                "sample.future",
                "Permission does not require existence",
                "docs/target.md",
                "architect",
            ):
                assert expected in text
            assert page.locator('[data-uml-id="sample.future"]').count() == 0
            assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_report_embeds_the_standard_graph_schema_with_independent_target(tmp_path):
    _, payload = _uml_report(tmp_path)
    observed = parse_graph(payload["observed"])
    target = parse_graph(payload["target"])
    assert observed.origin == "observed" and target.origin == "declared"
    assert observed.evidence and not target.evidence
    assert {edge.kind for edge in target.relationships} == {"inherits", "realizes"}
    assert {entity.id for entity in observed.entities}.isdisjoint(
        {entity.id for entity in target.entities}
    )
    assert all(entity.provenance for entity in target.entities)


@pytest.mark.parametrize("view", ["target", "diff"])
def test_global_api_intent_stays_inspectable_without_inventing_uml_or_visibility(tmp_path, view):
    api = pytest.importorskip("playwright.sync_api")
    html, payload = _uml_report(
        tmp_path,
        declaration_changes={
            "public_api": ["sample.core:Future", "sample.core:Client"],
            "public_api_provenance": ["docs/target.md"],
        },
    )
    graph = parse_graph(payload["target"])
    assert {entry.selector for entry in graph.public_api} == {
        "sample.core:Future",
        "sample.core:Client",
    }
    assert not any(entity.qualified_name.endswith(".Future") for entity in graph.entities)
    assert not any(
        receipt["subject_id"] in {entry.id for entry in graph.public_api}
        for receipt in payload["comparison"]["assessments"]
    )
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        page.locator(f'[data-flow-view="{view}"]').click()
        page.locator(".flow-details-toggle").click()
        details = page.locator(".flow-inspector-content")
        assert "Global published API" in details.inner_text()
        assert "sample.core:Future" in details.inner_text()
        assert "docs/target.md" in details.inner_text()
        assert page.locator('[data-uml-id="sample.core:Future"]').count() == 0
        page.locator('[data-uml-id="core"]').click()
        assert "Global published API" not in details.inner_text()
        assert "Language visibility" not in details.inner_text()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("view", ["target", "diff"])
def test_shared_permission_edges_retain_approval_and_connected_focus(tmp_path, nested, view):
    api = pytest.importorskip("playwright.sync_api")
    root, config = _nested_repository(tmp_path)
    path = root / ("inside.json" if nested else config.contract)
    raw = _permission_contract(json.loads(path.read_bytes()))
    other = {
        **raw["components"][1],
        "id": "OTHER",
        "label": "other",
        "namespace": "sample.core.other",
        "packages": ["sample.core.other"],
    }
    raw["components"].append(other)
    raw["components"][0]["requires"].append(
        {"component": "peer", "rationale": "Use the published boundary."}
    )
    path.write_text(json.dumps(raw))
    if nested:
        outer = root / config.contract
        outer.write_text(json.dumps(_permission_contract(json.loads(outer.read_bytes()))))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    html = render_html(
        result, model, repository="sample", architecture_href="architecture.json"
    ).decode()
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        page.locator(f'[data-flow-view="{view}"]').click()
        if nested:
            page.locator('[data-uml-id="ROOT"]').dblclick()
        owner = "core:core" if nested else "ROOT"
        peer = "core:PEER" if nested else "PEER"
        unrelated = "core:OTHER" if nested else "OTHER"
        page.locator(f'.flow-nodes [data-uml-id="{owner}"]').click()
        for identity in (owner, peer):
            assert "related" in page.locator(
                f'.flow-nodes [data-uml-id="{identity}"]'
            ).get_attribute("class")
        assert "dim" in page.locator(f'.flow-nodes [data-uml-id="{unrelated}"]').get_attribute(
            "class"
        )
        graph = parse_graph(json.loads(page.locator("#flow-data").text_content())["target"])
        permissions = [
            item
            for item in graph.relationships
            if item.kind == "requires" and item.source_id == owner
        ]
        assert len(permissions) == 2
        permission_edges = page.locator('.flow-edges [data-relationship-kind="requires"]')
        assert permission_edges.count() == 2
        assert permission_edges.evaluate_all(
            "edges => edges.every(edge => edge.classList.contains('related'))"
        )
        paths = []
        for permission in permissions:
            edge = page.locator(f'.flow-edges [data-uml-id="{permission.id}"]')
            assert "Allowed component import" in edge.locator(".hit").get_attribute("aria-label")
            marker = edge.locator(".line").evaluate("line => getComputedStyle(line).markerEnd")
            assert "flow-arrow" in marker
            path = edge.locator(".line").get_attribute("d")
            assert path == edge.locator(".hit").get_attribute("d")
            paths.append(path)
            edge.locator(".hit").press("Space")
            page.mouse.move(0, 0)
            assert "related" in edge.get_attribute("class")
            for other in permissions:
                if other.id != permission.id:
                    assert "dim" in page.locator(
                        f'.flow-edges [data-uml-id="{other.id}"]'
                    ).get_attribute("class")
            text = page.locator(".flow-inspector-content").inner_text()
            for expected in (
                "Allowed component import",
                "does not require an import or call",
                permission.reason,
                f"Decided by: {permission.decided_by}",
                *(permission.through or ("Published interface not narrowed",)),
            ):
                assert expected in text
            assert all(item.reason not in text for item in permissions if item.id != permission.id)
            assert "Target checks" not in text
            assert "Component intent" not in text
            assert (
                page.locator(".flow-inspector-content h2").inner_text()
                == "Allowed component import"
            )
        assert len(set(paths)) == 2
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["target", "diff"])
def test_nested_intent_uses_component_ids_and_keeps_physical_scope(tmp_path, view):
    api = pytest.importorskip("playwright.sync_api")
    root, config = _nested_repository(tmp_path, "2.1.0")
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    html = render_html(
        result, model, repository="sample", architecture_href="architecture.json"
    ).decode()
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        page.locator(f'[data-flow-view="{view}"]').click()
        assert page.locator('.flow-nodes [data-uml-kind="component"]').evaluate_all(
            "nodes => nodes.map(n => n.dataset.umlId)"
        ) == ["ROOT"]
        assert page.locator(".flow-nodes [data-uml-id]").count() == 1
        if view == "diff":
            _open_details(page)
            details = page.locator(".flow-inspector-content")
            assert "Observed code without a component assignment" in details.inner_text()
            payload = json.loads(page.locator("#flow-data").text_content())
            namespace_ids = {
                item["id"] for item in payload["observed"]["entities"] if item["kind"] == "package"
            }
            assert any(
                item["status"] == "UNKNOWN"
                and namespace_ids.intersection(item["graph_subject_ids"])
                for item in payload["findings"]
            )
        page.locator('[data-uml-id="ROOT"]').dblclick()
        assert page.locator('.flow-nodes [data-uml-kind="component"]').evaluate_all(
            "nodes => nodes.map(n => n.dataset.umlId)"
        ) == ["core:core"]
        file = page.locator('.flow-nodes [data-uml-kind="file"]')
        assert file.count() == 0
        details = page.locator(".flow-inspector-content")
        if not details.is_visible():
            page.locator("[data-flow-details-toggle]").click()
        details.get_by_text("Module inventory · 1 planned file", exact=True).click()
        details.get_by_text("Permitted package layout · 1 rule", exact=True).click()
        assert (
            "sample/core.py" in details.inner_text() and "core:layout" not in details.inner_text()
        )
        assert "sample.future" in details.inner_text()
        page.locator('[data-uml-id="core:core"]').dblclick()
        assert "service" in page.locator(".flow-breadcrumb").inner_text()
        assert set(
            page.locator(".flow-nodes [data-uml-id]").evaluate_all(
                "nodes => nodes.map(n => n.dataset.umlId)"
            )
        ) == {"core:service:core", "core:service", "core:interface"}
        assert "Explicitly empty" in details.inner_text()
        assert "Permitted package layout" not in details.inner_text()
        page.locator('[data-uml-id="core:service:core"]').dblclick()
        assert "operations" in page.locator(".flow-breadcrumb").inner_text()
        assert set(
            page.locator(".flow-nodes [data-uml-id]").evaluate_all(
                "nodes => nodes.map(n => n.dataset.umlId)"
            )
        ) == {"core:service:service", "core:service:interface"}
        page.locator('[data-uml-id="core:service:service"]').dblclick()
        assert page.locator('[data-uml-id="core:service:run"]').count() == 1
        page.locator('[data-uml-id="core:service:run"]').click()
        assert "Execute one request" in details.inner_text()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_report_embeds_core_comparison_receipts_without_reassessment(tmp_path):
    _, payload = _uml_report(tmp_path, mismatch=True)
    comparison = parse_comparison(payload["comparison"])
    assert comparison.status == "FAIL"
    assert any(
        item.subject_id == "client-run" and item.aspect == "signature" and item.status == "FAIL"
        for item in comparison.assessments
    )
    assert any(item.change == "unexpected" for item in comparison.assessments)
    assert any(
        item.subject_id == "missing" and item.status == "UNKNOWN" for item in comparison.assessments
    )


def test_diff_uses_class_cards_and_preserves_fail_unknown_and_unexpected(tmp_path):
    html, _ = _uml_report(tmp_path, mismatch=True)
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, html, width=1550, height=1150)
    try:
        _open_module(page, "Diff")
        client = page.locator('.flow-nodes [data-uml-id="client"]')
        assert client.get_attribute("data-uml-kind") == "class"
        assert client.get_attribute("data-assessment-status") == "FAIL"
        assert (
            page.locator('.flow-nodes [data-uml-id="missing"]').get_attribute(
                "data-assessment-status"
            )
            == "UNKNOWN"
        )
        extra = page.locator('.flow-nodes [data-label="Extra"]')
        assert extra.get_attribute("data-assessment-status") == "FAIL"
        client.click()
        assert client.locator(".uml-assessment").text_content() == "FAIL"
        assert "Return annotation differs" in page.locator(".flow-inspector").inner_text()
        assert "+ run(self, value: int): int" in page.locator(".flow-inspector").inner_text()
        extra.click()
        assert "unlisted definition" in page.locator(".flow-inspector").inner_text()
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("kind", ["calls", "imports"])
def test_diff_draws_core_unlisted_relationships_with_real_endpoints_and_sites(tmp_path, kind):
    html, payload = _uml_report(
        tmp_path,
        closed_relationships=(kind,),
        extra_source=(
            "from .other import external\n"
            "def extra(value): return external(value) + external(value)\n"
        ),
        extra_files={"sample/other.py": "def external(value): return value\n"},
    )
    comparison = parse_comparison(payload["comparison"])
    assert any(item.change == "unexpected" for item in comparison.assessments)
    api = pytest.importorskip("playwright.sync_api")
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        _open_module(page, "Diff")
        site = "sample.core.extra" if kind == "calls" else "sample.other"
        edge = page.locator(f'.flow-edges [data-relationship-kind="{kind}"]').filter(has_text=site)
        assert edge.count() == 1
        assert edge.get_attribute("data-assessment-status") == "FAIL"
        assert "unlisted" in edge.locator(".hit").get_attribute("aria-label")
        assert edge.locator(".line").get_attribute("d") == edge.locator(".hit").get_attribute("d")
        assert "flow-arrow" in edge.locator(".line").evaluate("n => getComputedStyle(n).markerEnd")
        edge.locator(".hit").press("Enter")
        text = page.locator(".flow-inspector-content").inner_text()
        assert "FAIL" in text and "Closed scope contains an unlisted relationship" in text
        assert "sample/core.py:" in text and "sample.other" in text
        assert "undefined" not in text
        if kind == "calls":
            assert "2 source or declaration sites" in edge.locator(".hit").get_attribute(
                "aria-label"
            )
            assert "sample.core.extra → sample.other.external" in text
        else:
            owner = page.locator('.flow-nodes [data-uml-id="module"]')
            assert owner.count() == 1
            breadcrumb = page.locator(".flow-breadcrumb").inner_text()
            owner.dblclick()
            assert page.locator(".flow-breadcrumb").inner_text() == breadcrumb
        assert page.locator('.flow-nodes [data-label="other"]').count() == 1
        if kind == "calls":
            page.locator('.flow-nodes [data-uml-id="client"]').click()
            text = page.locator(".flow-inspector-content").inner_text()
            assert "sample.core.Client.run → builtins.str" in text and "FAIL" in text
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_diff_never_borrows_a_target_identity_for_repeated_class_definitions(tmp_path):
    html, payload = _uml_report(
        tmp_path,
        closed_relationships=("calls",),
        extra_source=(
            "class Twin:\n def run(self): return str(1)\n"
            "class Twin:\n def run(self): return str(2)\n"
        ),
        extra_target_entities=(
            Entity(
                "twin",
                "class",
                "sample.core.Twin",
                "python",
                parent_id="module",
                presence="planned",
                responsibilities=("Own Twin operations.",),
                provenance=("docs/target.md",),
            ),
        ),
    )
    matches = next(
        item for item in payload["comparison"]["correspondences"] if item["target_id"] == "twin"
    )
    assert len(matches["observed_ids"]) == 2
    api = pytest.importorskip("playwright.sync_api")
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        _open_module(page, "Diff")
        assert (
            page.locator('[data-uml-id="twin"]').get_attribute("data-assessment-status")
            == "UNKNOWN"
        )
        for id in matches["observed_ids"]:
            card = page.locator(f'[data-uml-id="observed:{id}"]')
            assert card.count() == 1 and card.get_attribute("data-assessment-status") == "FAIL"
            assert "relationship endpoint" in card.text_content()
            assert "unlisted definition" not in card.text_content()
            card.click()
            assert "sample/core.py:" in page.locator(".flow-inspector-content").inner_text()
            card.press("Enter")
            method = page.locator('.flow-nodes [data-uml-kind="method"]')
            assert method.count() == 1
            method.click()
            details = page.locator(".flow-inspector-content").inner_text()
            assert "Closed scope contains an unlisted relationship" in details
            assert "sample/core.py:" in details
            page.locator(".flow-back").click()
            assert card.get_attribute("aria-pressed") == "true"
        assert page.locator('.flow-nodes [data-label="Twin"]').count() == 3
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_diff_opens_observed_only_class_method_and_preserves_navigation(tmp_path):
    html, _ = _uml_report(
        tmp_path,
        mismatch=True,
        closed_relationships=("calls",),
        extra_source=(
            "class Spare:\n _hidden: int\n def run(self, value: int) -> str: return str(value)\n"
        ),
    )
    api = pytest.importorskip("playwright.sync_api")
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        _open_module(page, "Diff")
        spare = page.locator('.flow-nodes [data-label="Spare"]')
        identity = spare.get_attribute("data-uml-id")
        spare.click()
        page.locator(".flow-inspector-content [data-uml-detail]").click()
        assert "Observed: run" in page.locator(".flow-breadcrumb").inner_text()
        page.locator(".flow-back").click()
        assert spare.get_attribute("aria-pressed") == "true"
        assert page.evaluate("document.activeElement.dataset.umlId") == identity
        page.get_by_role("button", name="Open selected Spare", exact=True).click()
        assert "Observed: Spare" in page.locator(".flow-breadcrumb").inner_text()
        method = page.locator('.flow-nodes [data-uml-kind="method"]')
        assert method.count() == 1
        assert page.locator('.flow-nodes [data-uml-kind="attribute"]').count() == 1
        page.locator('.flow-nodes [data-uml-kind="attribute"]').click()
        details = page.locator(".flow-inspector-content").inner_text()
        assert "private · convention" in details and "− _hidden: int" in details
        method.click()
        details = page.locator(".flow-inspector-content").inner_text()
        assert "+ run(self, value: int): str" in details
        assert "Closed scope contains an unlisted relationship" in details
        assert "sample/core.py:" in details
        page.get_by_role("button", name="Target", exact=True).click()
        assert page.locator('.flow-nodes [data-label="Spare"]').count() == 0
        page.get_by_role("button", name="Diff", exact=True).click()
        assert "Observed: Spare" in page.locator(".flow-breadcrumb").inner_text()
        assert method.get_attribute("aria-pressed") == "true"
        method.press("Enter")
        edge = page.locator('.flow-edges [data-relationship-kind="calls"]')
        assert edge.count() == 1 and edge.get_attribute("data-assessment-status") == "FAIL"
        assert edge.locator(".line").get_attribute("d") == edge.locator(".hit").get_attribute("d")
        edge.locator(".hit").press("Enter")
        assert (
            "sample.core.Spare.run → builtins.str"
            in page.locator(".flow-inspector-content").inner_text()
        )
        page.locator(".flow-back").click()
        assert method.get_attribute("aria-pressed") == "true"
        page.locator(".flow-back").click()
        assert page.locator(f'[data-uml-id="{identity}"]').get_attribute("aria-pressed") == "true"
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_diff_unresolved_operation_remains_inspectable_without_ghost_endpoints(tmp_path):
    html, _ = _uml_report(
        tmp_path,
        mismatch=True,
        closed_relationships=("calls",),
        extra_source="class Pending:\n def run(self): return missing()\n",
    )
    api = pytest.importorskip("playwright.sync_api")
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        _open_module(page, "Diff")
        page.locator('.flow-nodes [data-label="Pending"]').dblclick()
        page.locator('.flow-nodes [data-uml-kind="method"]').press("Enter")
        assert page.locator(".flow-nodes .node").count() == 0
        assert page.locator(".flow-edges .hit").count() == 0
        details = page.locator(".flow-inspector-content").inner_text()
        assert "sample.core.Pending.run" in details
        assert "missing()" in details and "unresolved" in details
        assert "No recorded check for this observed scope" in details and "PASS" not in details
        assert "sample/core.py:" in details
        assert "No elements or resolved connections" in page.locator(".flow-empty").text_content()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.fixture
def uml_page(tmp_path):
    html, payload = _uml_report(tmp_path)
    api = pytest.importorskip("playwright.sync_api")
    errors = []
    playwright, browser, page = _browser_page(api, html, width=1550, height=1150, errors=errors)
    try:
        page.locator("#flow").scroll_into_view_if_needed()
        yield page, payload
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def _open_module(page, view):
    page.get_by_role("button", name=view, exact=True).click()
    if view == "As-Is":
        page.locator('.flow-nodes [data-label="core"]').dblclick()
        page.locator('.flow-nodes [data-uml-kind="module"][data-label="core"]').dblclick()
    else:
        page.locator('.flow-nodes [data-uml-id="core"]').dblclick()
        page.locator('.flow-nodes [data-uml-id="module"]').dblclick()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
def test_operation_calls_keep_the_callee_method_instead_of_its_class(tmp_path, view):
    provenance = ("docs/target.md",)
    html, _ = _uml_report(
        tmp_path,
        extra_source="def invoke():\n return Client.run(None, 1)\n",
        extra_target_entities=(
            Entity(
                "invoke",
                "function",
                "sample.core.invoke",
                "python",
                "module",
                presence="planned",
                responsibilities=("Call the declared operation.",),
                provenance=provenance,
            ),
        ),
        extra_target_relationships=(
            Relationship("invoke-run", "calls", "invoke", "client-run", provenance=provenance),
        ),
    )
    api = pytest.importorskip("playwright.sync_api")
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        _open_module(page, view)
        page.locator('.flow-nodes [data-label="invoke"]').dblclick()
        assert page.locator('.flow-nodes [data-label="Client"]').count() == 0
        callee = page.locator('.flow-nodes [data-label="run"]')
        assert callee.get_attribute("data-uml-kind") == "method"
        edge = page.locator('.flow-edges [data-relationship-kind="calls"]')
        assert edge.count() == 1
        assert edge.get_attribute("data-uml-target") == callee.get_attribute("data-uml-id")
        edge.locator(".hit").press("Enter")
        details = page.locator(".flow-inspector-content").inner_text()
        assert "sample.core.invoke → sample.core.Client.run" in details
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_conditional_definitions_use_visible_cards_and_inspectable_contexts(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    html, payload = _uml_report(
        tmp_path,
        extra_source=(
            "if configuration_flag:\n"
            " class Conditional:\n"
            "  def run(self): return str(1)\n"
            "Conditional()\n"
        ),
    )
    observed = parse_graph(payload["observed"])
    classifier = next(
        item for item in observed.entities if item.qualified_name.endswith(".Conditional")
    )
    method = next(item for item in observed.entities if item.parent_id == classifier.id)
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        _open_module(page, "As-Is")
        card = page.locator(f'.flow-nodes [data-uml-id="{classifier.id}"]')
        assert card.is_visible()
        card.click()
        details = page.locator(".flow-inspector-content").inner_text()
        assert "Definition context" in details and "if · body" in details
        assert "Runtime name binding is not proven" in details
        card.dblclick()
        operation = page.locator(f'.flow-nodes [data-uml-id="{method.id}"]')
        assert operation.is_visible()
        operation.click()
        assert "if · body" in page.locator(".flow-inspector-content").inner_text()
        assert operation.get_attribute("data-uml-kind") == "method"
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
def test_static_binding_and_constructor_sites_use_the_shared_renderer(tmp_path, view):
    api = pytest.importorskip("playwright.sync_api")
    provenance = ("docs/target.md",)
    extra = (
        Entity(
            "unit",
            "class",
            "sample.core.Unit",
            "python",
            "module",
            presence="planned",
            responsibilities=("Represent the work value.",),
            provenance=provenance,
        ),
        Entity(
            "build",
            "function",
            "sample.core.build",
            "python",
            "module",
            presence="planned",
            responsibilities=("Create the work value.",),
            provenance=provenance,
        ),
        Entity(
            "item",
            "binding",
            "sample.core.build.item",
            "python",
            "build",
            presence="planned",
            initializer="Unit()",
            responsibilities=("Hold the created value at this site.",),
            provenance=provenance,
        ),
    )
    html, payload = _uml_report(
        tmp_path,
        extra_source="class Unit: pass\ndef build():\n item = Unit()\n return item\n",
        extra_target_entities=extra,
        extra_target_relationships=(
            Relationship("creates-unit", "creates", "build", "unit", provenance=provenance),
            Relationship("item-unit", "instance_of", "item", "unit", provenance=provenance),
        ),
    )
    observed = parse_graph(payload["observed"])
    observed_build = next(
        item for item in observed.entities if item.qualified_name == "sample.core.build"
    )
    observed_item = next(
        item for item in observed.entities if item.qualified_name == "sample.core.build.item"
    )
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        _open_module(page, view)
        build_id = observed_build.id if view == "As-Is" else "build"
        item_id = observed_item.id if view == "As-Is" else "item"
        page.locator(f'.flow-nodes [data-uml-id="{build_id}"]').dblclick()
        card = page.locator(f'.flow-nodes [data-uml-id="{item_id}"]')
        assert card.is_visible() and card.get_attribute("data-uml-kind") == "binding"
        assert "Unit()" in card.text_content()
        card.click()
        details = page.locator(".flow-inspector-content").inner_text()
        assert "Static assignment site" in details and "live object" in details
        assert "Unit()" in details
        assert (
            card.locator(".label").evaluate("node => getComputedStyle(node).textDecorationLine")
            == "underline"
        )
        edge = page.locator('.flow-edges [data-relationship-kind="instance_of"]')
        assert edge.is_visible()
        assert edge.locator(".line").evaluate("node => getComputedStyle(node).markerEnd") != "none"
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target"])
def test_class_compartments_show_visibility_and_typed_operations(uml_page, view):
    page, _ = uml_page
    _open_module(page, view)
    page.get_by_role("button", name="Member previews", exact=True).click()
    client = page.locator('.flow-nodes [data-label="Client"]')
    assert client.get_attribute("data-uml-kind") == "class"
    members = client.locator(".uml-member").evaluate_all(
        "nodes => nodes.map(n => Array.from(n.querySelectorAll('tspan'),"
        "t => t.textContent).join(' ').replace(/\\s+/g, ' ').trim())"
    )
    assert "− _token: str" in members
    assert "+ run(self, value: int): str" in members
    assert client.locator(".uml-divider").count() == 2
    assert (
        page.locator('.flow-nodes [data-label="Port"]').get_attribute("data-uml-kind")
        == "interface"
    )
    client.dblclick()
    assert page.locator('.flow-nodes [data-uml-kind="method"]').count() == 1
    assert page.locator('.flow-nodes [data-uml-kind="attribute"]').count() == 1
    page.locator(".flow-back").click()
    assert page.locator('.flow-nodes [data-label="Client"]').count() == 1


@pytest.mark.parametrize("view", ["As-Is", "Target"])
def test_classifier_edges_share_clear_notation_and_connected_focus(uml_page, view):
    page, _ = uml_page
    _open_module(page, view)
    page.locator('.flow-nodes [data-label="Client"]').click()
    for label in ("Client", "Base", "Port"):
        assert "related" in page.locator(f'.flow-nodes [data-label="{label}"]').get_attribute(
            "class"
        )
    assert "dim" in page.locator('.flow-nodes [data-label="Other"]').get_attribute("class")
    for kind, dash in (("inherits", "none"), ("realizes", "6px, 4px")):
        edge = page.locator(f'.flow-edges [data-relationship-kind="{kind}"]').filter(
            has=page.locator(".line")
        )
        selected = edge.locator(".line").evaluate_all(
            "lines => lines.filter(n => n.parentNode.classList.contains('related')).map(n => ({"
            "marker:getComputedStyle(n).markerEnd,dash:getComputedStyle(n).strokeDasharray,"
            "d:n.getAttribute('d'),hit:n.parentNode.querySelector('.hit').getAttribute('d')}))"
        )
        assert selected and all("uml-triangle" in item["marker"] for item in selected)
        assert all(item["dash"] == dash and item["d"] == item["hit"] for item in selected)


@pytest.mark.parametrize("view", ["As-Is", "Target"])
def test_graph_routes_avoid_card_interiors_and_share_visible_hit_geometry(uml_page, view):
    page, _ = uml_page
    _open_module(page, view)
    collisions = page.evaluate("""() => {
      const cards = Array.from(document.querySelectorAll('.flow-nodes .node'), group => {
        const rect = group.querySelector('.card');
        const matrix = group.transform.baseVal.consolidate().matrix;
        return {id:group.dataset.umlId, x:matrix.e, y:matrix.f,
          w:Number(rect.getAttribute('width')), h:Number(rect.getAttribute('height'))};
      });
      const conflicts = [];
      for (const path of document.querySelectorAll('.flow-edges .line')) {
        const length = path.getTotalLength();
        for (let at=2; at<length-2; at+=2) {
          const p=path.getPointAtLength(at);
          for (const card of cards) if (p.x>card.x+1 && p.x<card.x+card.w-1
              && p.y>card.y+1 && p.y<card.y+card.h-1) {
            conflicts.push({edge:path.parentNode.dataset.umlId, card:card.id}); break;
          }
        }
      }
      return conflicts;
    }""")
    assert collisions == []
    assert page.locator(".flow-edges .hit").count() == page.locator(".flow-edges .line").count()
    assert page.locator(".flow-frames [tabindex]").count() == 0
    for selector in ("html", ".flow-canvas", ".flow-inspector"):
        assert page.locator(selector).evaluate("n => getComputedStyle(n).scrollbarWidth") == "none"


def test_keyboard_drilldown_and_view_roundtrip_keep_the_source_scope(uml_page):
    page, _ = uml_page
    _open_module(page, "As-Is")
    client = page.locator('.flow-nodes [data-label="Client"]')
    client.focus()
    client.press("Enter")
    page.locator('.flow-nodes [data-uml-kind="method"]').press("Space")
    page.get_by_role("button", name="Target", exact=True).click()
    page.get_by_role("button", name="Diff", exact=True).click()
    page.get_by_role("button", name="As-Is", exact=True).click()
    assert (
        page.locator('.flow-nodes [data-uml-kind="method"]').get_attribute("aria-pressed") == "true"
    )
    page.locator(".flow-back").click()
    assert page.locator('.flow-nodes [data-label="Client"]').count() == 1


def test_source_scope_retains_unresolved_calls_and_parameter_kinds(tmp_path):
    html, _ = _uml_report(
        tmp_path,
        extra_source=(
            "def options(value: int, /, *, flag: bool = False) -> None:\n unknown(value)\n"
        ),
    )
    api = pytest.importorskip("playwright.sync_api")
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        _open_module(page, "As-Is")
        options = page.locator('.flow-nodes [data-label="options"]')
        options.click()
        details = page.locator(".flow-inspector").inner_text()
        assert "value: int, /, *, flag: bool = False" in details
        assert "unknown(value)" in details and "unresolved" in details
        assert page.locator('.flow-nodes [data-label="unknown"]').count() == 0
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_recursive_calls_do_not_create_false_layout_depth(tmp_path):
    html, _ = _uml_report(
        tmp_path, extra_source=("def first(): return second()\ndef second(): return first()\n")
    )
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_module(page, "As-Is")
        positions = page.locator(
            '.flow-nodes [data-label="first"], .flow-nodes [data-label="second"]'
        ).evaluate_all("nodes => nodes.map(n => n.transform.baseVal.consolidate().matrix.f)")
        assert len(positions) == 2
        assert positions[0] == positions[1]
        page.get_by_role("button", name="Fit overview", exact=True).click()
        assert page.locator(".flow-canvas").evaluate("""canvas => {
          const bounds = canvas.getBoundingClientRect();
          return [...canvas.querySelectorAll('.flow-nodes .card')].every(card => {
            const box = card.getBoundingClientRect();
            return box.left >= bounds.left && box.right <= bounds.right
              && box.top >= bounds.top && box.bottom <= bounds.bottom;
          });
        }""")
    finally:
        browser.close()
        playwright.stop()


def test_long_operations_stay_compact_and_keep_full_details(tmp_path):
    parameters = ", ".join(f"value{i}: tuple[str, int, bool]" for i in range(8))
    html, _ = _uml_report(
        tmp_path,
        extra_source=(f"class Long:\n def convert(self, {parameters}) -> str: return ''\n"),
    )
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_module(page, "As-Is")
        page.get_by_role("button", name="Member previews", exact=True).click()
        card = page.locator('.flow-nodes [data-label="Long"]')
        assert card.locator(".uml-member tspan").count() <= 2
        assert "…" in card.locator(".uml-member").text_content()
        card.click()
        assert parameters in page.locator(".flow-inspector").inner_text()
    finally:
        browser.close()
        playwright.stop()


def test_outside_callers_use_their_recorded_module_and_keep_every_site(tmp_path):
    html, _ = _uml_report(
        tmp_path,
        extra_files={
            "sample/other.py": (
                "from .core import Client\ndef one(): return Client()\ndef two(): return Client()\n"
            )
        },
    )
    api = pytest.importorskip("playwright.sync_api")
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_module(page, "As-Is")
        outside = page.locator('.flow-nodes [data-label="other"]')
        assert outside.get_attribute("data-uml-kind") == "module"
        assert (
            page.locator('.flow-nodes [data-label="one"], .flow-nodes [data-label="two"]').count()
            == 0
        )
        edge = page.locator('.flow-edges [data-relationship-kind="calls"] .hit').filter(
            has_text="sample.other.one"
        )
        assert "2 source or declaration sites" in edge.get_attribute("aria-label")
        edge.press("Enter")
        details = page.locator(".flow-inspector").inner_text()
        assert "sample.other.one → sample.core.Client" in details
        assert "sample.other.two → sample.core.Client" in details
        assert "sample/other.py:2:" in details and "sample/other.py:3:" in details
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["target", "diff"])
def test_file_intent_distinguishes_observed_inventory_from_core_verdict(tmp_path, view):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(
        tmp_path,
        declaration_changes={
            "modules": [
                {"path": "sample/core.py", "responsibility": "Own recorded operations."},
                {
                    "path": "src/sample/future.py",
                    "responsibility": "Keep independent future intent.",
                },
            ]
        },
    )
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        page.locator(f'[data-flow-view="{view}"]').click()
        _open_details(page)
        details = page.locator(".flow-inspector-content")
        details.get_by_text("Module inventory · 2 planned files", exact=True).click()
        assert (
            "Observed module: sample.core"
            in details.locator('[data-file-intent="sample/core.py"]').inner_text()
        ) == (view == "diff")
        assert ("separate from a Core verdict" in details.inner_text()) == (view == "diff")
        assert (
            "Not in the observed file inventory"
            in details.locator('[data-file-intent="src/sample/future.py"]').inner_text()
        ) == (view == "diff")
        assert "does not define classes, methods, imports or calls" in details.inner_text()
        assert page.locator('.flow-nodes [data-uml-kind="file"]').count() == 0
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_module_overview_keeps_referenced_symbols_in_explicit_relationship_views(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    html, _ = _uml_report(tmp_path, extra_source="def runner():\n    print('value')\n")
    playwright, browser, page = _browser_page(api, html)
    try:
        _open_module(page, "As-Is")
        payload = page.locator("#flow-data").text_content()
        assert page.locator('.flow-nodes [data-label="runner"]').count() == 1
        assert page.locator('.flow-nodes [data-label="print"]').count() == 0
        assert "referenced symbols" in page.locator(".flow-filter-status").inner_text()
        page.locator('.flow-legend button[data-relationship-kind="calls"]').click()
        referenced = page.locator('.flow-nodes [data-label="print"]')
        assert referenced.count() == 1
        referenced.press("Space")
        assert "builtins.print" in page.locator(".flow-inspector-content").inner_text()
        assert page.locator("#flow-data").text_content() == payload
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
def test_static_members_are_underlined_in_previews_and_drilldown(tmp_path, view):
    context = {
        "presence": "planned",
        "provenance": ("docs/target.md",),
        "responsibilities": ("Keep shared state and its reset operation on the class.",),
    }
    html, _ = _uml_report(
        tmp_path,
        extra_source=(
            "class Data:\n limit = 10\n _cache = {}\n @staticmethod\n def reset() -> None: pass\n"
        ),
        extra_target_entities=(
            Entity("data", "class", "sample.core.Data", "python", "module", **context),
            Entity(
                "limit",
                "attribute",
                "sample.core.Data.limit",
                "python",
                "data",
                visibility=Visibility("public", "declared"),
                modifiers=("static",),
                **context,
            ),
            Entity(
                "cache",
                "attribute",
                "sample.core.Data._cache",
                "python",
                "data",
                visibility=Visibility("private", "declared"),
                modifiers=("static",),
                **context,
            ),
            Entity(
                "reset",
                "method",
                "sample.core.Data.reset",
                "python",
                "data",
                visibility=Visibility("public", "declared"),
                signature=Signature((), "None"),
                modifiers=("static",),
                **context,
            ),
        ),
    )
    api = pytest.importorskip("playwright.sync_api")
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        _open_module(page, view)
        page.get_by_role("button", name="Member previews", exact=True).click()
        card = page.locator('.flow-nodes [data-label="Data"]')
        assert card.locator(".uml-member").count() == 3
        assert card.locator(".uml-member").evaluate_all("""lines => lines.every(line =>
            getComputedStyle(line).textDecorationLine.includes('underline'))""")
        assert page.locator('.flow-nodes [data-label="Client"] .uml-member').evaluate_all(
            "lines => lines.every(line => getComputedStyle(line).textDecorationLine === 'none')"
        )
        card.dblclick()
        for name in ("limit", "_cache", "reset"):
            member = page.locator(f'.flow-nodes [data-label="{name}"]')
            assert member.count() == 1
            assert member.locator(".label").evaluate("""line =>
                getComputedStyle(line).textDecorationLine.includes('underline')""")
            assert member.locator(".meta").evaluate("""line =>
                getComputedStyle(line).textDecorationLine.includes('underline')""")
        assert (
            page.locator('.flow-nodes [data-label="_cache"] .meta').text_content().startswith("−")
        )
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["As-Is", "Target", "Diff"])
def test_enum_literals_share_a_distinct_compartment_and_drilldown_kind(tmp_path, view):
    context = {
        "presence": "planned",
        "provenance": ("docs/target.md",),
        "responsibilities": ("Expose the ready and failed states.",),
    }
    html, _ = _uml_report(
        tmp_path,
        extra_source=(
            "from enum import Enum\nclass State(Enum):\n READY = 'ready'\n FAILED = 'failed'\n"
        ),
        extra_target_entities=(
            Entity("state", "enum", "sample.core.State", "python", "module", **context),
            Entity(
                "ready", "enum_literal", "sample.core.State.READY", "python", "state", **context
            ),
            Entity(
                "failed", "enum_literal", "sample.core.State.FAILED", "python", "state", **context
            ),
        ),
    )
    api = pytest.importorskip("playwright.sync_api")
    errors = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        _open_module(page, view)
        card = page.locator('.flow-nodes [data-label="State"]')
        assert "2 literals" in card.locator(".meta").text_content()
        page.get_by_role("button", name="Member previews", exact=True).click()
        assert card.locator(".uml-compartment-title").all_text_contents() == ["Literals"]
        assert set(card.locator(".uml-member").all_text_contents()) == {"READY", "FAILED"}
        assert card.locator(".uml-member").evaluate_all(
            "lines => lines.every(line => getComputedStyle(line).textDecorationLine === 'none')"
        )
        card.dblclick()
        for name in ("READY", "FAILED"):
            member = page.locator(f'.flow-nodes [data-label="{name}"]')
            assert member.get_attribute("data-uml-kind") == "enum_literal"
            assert member.locator(".stereotype").text_content() == "«enumeration literal»"
            assert member.locator(".label").evaluate(
                "line => getComputedStyle(line).textDecorationLine === 'none'"
            )
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("view", ["diagram", "target", "diff"])
@pytest.mark.parametrize("source", ["class Unassigned: pass\n", ""])
def test_component_overview_keeps_file_intent_and_unassigned_code_out_of_the_graph(
    tmp_path, view, source
):
    api = pytest.importorskip("playwright.sync_api")
    html, payload = _uml_report(
        tmp_path,
        extra_files={"sample/unassigned.py": source},
        declaration_changes={
            "modules": [{"path": "sample/future.py", "responsibility": "Keep independent intent."}]
        },
    )
    playwright, browser, page = _browser_page(api, html)
    try:
        page.locator(f'[data-flow-view="{view}"]').click()
        assert set(
            page.locator(".flow-nodes .node").evaluate_all(
                "nodes => nodes.map(node => node.dataset.umlKind)"
            )
        ) == {"component"}
        assert page.locator('.flow-nodes [data-uml-kind="file"]').count() == 0
        if view != "target":
            page.locator(".flow-unassigned-code").click()
            details = page.locator(".flow-inspector-content")
            assert "Observed code without a component assignment" in details.inner_text()
            assert "sample/unassigned.py" in details.inner_text()
            details.locator("li").filter(has_text="sample/unassigned.py").get_by_role(
                "button", name="Open", exact=True
            ).click()
            if source:
                assert page.locator('.flow-nodes [data-label="Unassigned"]').count() == 1
            else:
                assert details.locator("h2").inner_text() == "unassigned"
                assert "Source file" in details.inner_text()
                assert "sample/unassigned.py" in details.inner_text()
        else:
            _open_details(page)
            details = page.locator(".flow-inspector-content")
            details.get_by_text("Module inventory · 1 planned file", exact=True).click()
            assert "sample/future.py" in details.inner_text()
        assert json.loads(page.locator("#flow-data").text_content()) == payload
    finally:
        browser.close()
        playwright.stop()
