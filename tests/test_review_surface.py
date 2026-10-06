# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Review navigation and handoff preserve the underlying evidence."""

from dataclasses import replace
from pathlib import Path

from test_html_report import _start_tags
from test_report_159_160 import _flow_data, _linked_audit, _report

from archkeel.ir.model import Diagnostic, RunResult
from archkeel.ir.report_graph import architecture_report
from archkeel.render.html import render_check_html, render_html


def test_explorer_follows_verdicts_and_preserves_finding_links(tmp_path: Path) -> None:
    _, observation, page = _report(tmp_path)
    body = page.split("</style>", 1)[1]
    assert body.index('class="atlas-status"') < body.index('id="flow"')
    assert body.index('id="flow"') < body.index('class="atlas-source"')
    audit = _linked_audit(page, tmp_path)
    assert audit == observation
    data = _flow_data(page)["atlas"]
    routes = {f"?component={item['id']}" for item in data["components"]}
    routes.add(data["unassigned_detail_href"])
    assert all(route.startswith("?component=") for route in routes)
    detail_page = data["detail_page"]
    sidecar = (tmp_path / detail_page).read_text()
    assert "architecture.json" in {link.get("href") for link in _start_tags(sidecar, "a")}
    findings = {item["id"]: item for item in _flow_data(sidecar)["findings"]}
    native = architecture_report(observation)
    assert findings.keys() >= {item.id for item in native.findings if item.graph_subject_ids}
    for item in native.findings:
        if item.id in findings:
            assert findings[item.id]["status"] == item.status
            assert findings[item.id]["evidence_ids"] == list(item.evidence_ids)


def test_handoff_preserves_all_evidence_and_dirty_source_binding(tmp_path: Path) -> None:
    result, observation, _ = _report(tmp_path)
    reference = next(
        item.evidence_ids[0] for item in observation.records("violations") if item.evidence_ids
    )
    evidence = tuple(
        replace(item, excerpt="</textarea><script>untrusted()</script>")
        if item.id == reference
        else item
        for item in observation.evidence
    )
    observation = replace(
        observation,
        source=replace(observation.source, dirty=True),
        evidence=evidence,
    )
    page = render_html(
        result, observation, repository="shop", architecture_href="architecture.json"
    )
    assert page == render_html(
        result, observation, repository="shop", architecture_href="architecture.json"
    )
    text = page.decode()
    assert "Source digest: " + observation.source.source_digest in text
    assert "Dirty: True" in text
    assert "Locations refer to this analyzed snapshot" in text
    assert "Copy for agent" in text
    assert "&lt;/textarea&gt;&lt;script&gt;untrusted()&lt;/script&gt;" in text
    for item in (*observation.records("violations"), *observation.records("unknowns")):
        assert item.id in text
        for evidence_id in item.evidence_ids:
            assert evidence_id in text
    assert 'href="https://github.com/' not in text


def test_check_without_a_delta_does_not_claim_no_changes() -> None:
    result = RunResult(
        "check", 2, diagnostics=(Diagnostic("missing_tool", "git", "No comparison", "Install Git"),)
    )
    page = render_check_html(result, repository="shop", result_href="result.json").decode()
    assert "No semantic changes were observed" not in page
    assert "Comparison unavailable" in page
    assert "Accepted → candidate" in page
    assert 'href="#check-changes"' in page
