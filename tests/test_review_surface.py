# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Review navigation and handoff preserve the underlying evidence."""

from dataclasses import replace
from pathlib import Path

from test_html_report import _start_tags
from test_report_159_160 import _report

from archkeel.ir.model import Diagnostic, RunResult
from archkeel.render.html import render_check_html, render_html


def test_explorer_follows_verdicts_and_preserves_finding_links(tmp_path: Path) -> None:
    _, observation, page = _report(tmp_path)
    body = page.split("</style>", 1)[1]
    assert body.index('id="verdicts-heading"') < body.index('id="flow"')
    assert body.index('id="flow"') < body.index('id="violations-heading"')
    assert body.index('id="flow"') < body.index('id="known-unknowns"')
    records = (*observation.records("violations"), *observation.records("unknowns"))
    rows = {
        row["data-finding-id"]: row for row in _start_tags(page, "tr") if "data-finding-id" in row
    }
    assert rows.keys() >= {item.id for item in records}
    assert len({rows[item.id]["id"] for item in records}) == len(records)
    hrefs = {link.get("href") for link in _start_tags(page, "a")}
    assert all(f"#{rows[item.id]['id']}" in hrefs for item in records)


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
