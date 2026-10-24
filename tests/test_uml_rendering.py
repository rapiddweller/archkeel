# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The report draws independent source and Target graphs through one UML boundary."""

import json
from dataclasses import asdict
from unittest.mock import Mock

import pytest
from browser_report_support import _browser_page
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
from archkeel.render.html import _asset, render_html


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


def test_standard_uml_inlines_pinned_elk_before_flow_under_offline_csp(tmp_path):
    html, _ = _uml_report(tmp_path)

    assert _asset("explorer.runtime.js").decode() in html
    vendor = '<script data-elkjs-version="0.12.0">'
    explorer = '<script data-report-asset="explorer">'
    assert html.count(vendor) == html.count(explorer) == 1
    assert html.index(vendor) < html.index(explorer)
    csp = html.split('http-equiv="Content-Security-Policy"', 1)[1].split(">", 1)[0]

    assert "worker-src" not in csp
    assert "<script src=" not in html


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
    _wait_for_layout(page)
    if view == "As-Is":
        page.locator('.flow-nodes [data-label="core"]').dblclick()
        _wait_for_layout(page)
        page.locator('.flow-nodes [data-uml-kind="module"][data-label="core"]').dblclick()
        _wait_for_layout(page)
    else:
        page.locator('.flow-nodes [data-uml-id="core"]').dblclick()
        _wait_for_layout(page)
        page.locator('.flow-nodes [data-uml-id="module"]').dblclick()
        _wait_for_layout(page)


def _wait_for_layout(page):
    try:
        page.wait_for_function(
            "() => ['ready', 'error'].includes("
            "document.querySelector('#flow')?.dataset.layoutState)"
        )
        assert page.locator("#flow").get_attribute("data-layout-state") == "ready"
    except Exception as error:
        try:
            snapshot = page.wait_for_function(
                """() => JSON.stringify({
                  state: document.querySelector('#flow')?.dataset.layoutState?.slice(0, 32),
                  breadcrumb: document.querySelector('.flow-breadcrumb')
                    ?.textContent?.slice(0, 512),
                  scope: window.ArchkeelFlow?.state()?.scope?.slice(0, 256),
                  nodes: document.querySelectorAll('.flow-nodes > g').length,
                  edges: document.querySelectorAll('.flow-edges .edge').length
                })""",
                timeout=1000,
            ).json_value()
            error.add_note(f"Layout failure snapshot: {snapshot}")
        except Exception:
            # A closed or stalled browser must not replace the original test failure.
            pass
        raise


def test_layout_diagnostics_preserve_failure_when_browser_is_unavailable():
    original = TimeoutError("original layout deadline")
    page = Mock()
    page.wait_for_function.side_effect = [original, RuntimeError("browser closed")]
    with pytest.raises(TimeoutError) as caught:
        _wait_for_layout(page)
    assert caught.value is original


@pytest.mark.browser
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
