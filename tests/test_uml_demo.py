# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Runnable demos must prove independent intent through the production report."""

import json
import re
from dataclasses import replace
from typing import get_args

import pytest

from archkeel.ir.architecture_graph import EntityKind
from archkeel.ir.graph_codec import parse_report
from fixtures.architecture_demo import CATALOG, replay


def test_complete_uml_demo_rejects_an_unlisted_definition(tmp_path, capsys, monkeypatch):
    from fixtures import architecture_demo

    variant = next(row for row in CATALOG if row.id == "uml-complete")
    changed = replace(
        variant,
        files={
            **variant.files,
            "demo/core.py": variant.files["demo/core.py"] + "\n\ndef extra() -> None:\n    pass\n",
        },
    )
    monkeypatch.setattr(architecture_demo, "CATALOG", (changed,))
    output = tmp_path / "architecture.json"
    assert replay("uml-complete", output) == 2
    capsys.readouterr()
    payload = re.search(
        r'<script[^>]*id="flow-data"[^>]*>(.*?)</script>',
        output.with_suffix(".report.html").read_text(),
        re.S,
    )
    report = parse_report(json.loads(payload.group(1)))
    extra = next(e for e in report.observed.entities if e.qualified_name == "demo.core.extra")
    assert any(
        a.status == "FAIL" and a.aspect == "completeness" and extra.id in a.observed_ids
        for a in report.comparison.assessments
    )
    assert not any(e.qualified_name == "demo.core.extra" for e in report.target.entities)


def test_complete_uml_demo_declares_closed_intent_without_claiming_full_observation(
    tmp_path, capsys
):
    output = tmp_path / "architecture.json"
    assert replay("uml-complete", output) == 0
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result["declared_rules"] == "UNKNOWN"
    html = output.with_suffix(".report.html").read_text()
    payload = re.search(r'<script[^>]*id="flow-data"[^>]*>(.*?)</script>', html, re.S)
    report = parse_report(json.loads(payload.group(1)))
    assert {e.kind for e in report.target.entities} == set(get_args(EntityKind))
    assert report.target.target_scopes and all(
        s.mode == "closed" for s in report.target.target_scopes
    )
    assert {s.scope_id for s in report.target.target_scopes} >= {
        "demo-component",
        "core-module",
        "app-module",
        "init-module",
    }
    assert report.comparison and not any(a.status == "FAIL" for a in report.comparison.assessments)
    assert any(
        a.status == "UNKNOWN" and a.aspect == "completeness" for a in report.comparison.assessments
    )
    names = {e.id: e.qualified_name for e in report.observed.entities}
    uses = {
        names[r.target_id]
        for r in report.observed.relationships
        if r.kind == "references" and names[r.source_id] == "demo.core.describe" and r.target_id
    }
    assert {"demo.core.State", "demo.core.VERSION"} <= uses
    wanted_uses = {
        r.target_id
        for r in report.target.relationships
        if r.kind == "references" and r.source_id == "describe"
    }
    assert wanted_uses == {"state", "version"}


@pytest.mark.parametrize(
    "variant,status,exit_code",
    [("uml-match", "PASS", 0), ("uml-mismatch", "FAIL", 2), ("uml-partial", "UNKNOWN", 0)],
)
def test_uml_demo_uses_independent_target_and_recorded_core_comparison(
    tmp_path, capsys, variant, status, exit_code
):
    assert variant in {row.id for row in CATALOG}
    output = tmp_path / "architecture.json"
    assert replay(variant, output) == exit_code
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result["declared_rules"] == status
    html = output.with_suffix(".report.html").read_text()
    payload = re.search(r'<script[^>]*id="flow-data"[^>]*>(.*?)</script>', html, re.S)
    assert payload
    report = parse_report(json.loads(payload.group(1)))
    assert report.observed.origin == "observed" and report.target.origin == "declared"
    assert report.observed.schema_version == report.target.schema_version == "1.1.0"
    assert report.comparison and report.comparison.assessments
    assert {item.kind for item in report.target.entities} >= {
        "component",
        "module",
        "class",
        "interface",
        "enum",
        "enum_literal",
        "attribute",
        "method",
        "function",
        "binding",
    }
    assert {item.kind for item in report.target.relationships} >= {
        "imports",
        "calls",
        "references",
        "inherits",
        "realizes",
        "creates",
        "instance_of",
    }
    assert all(item.provenance and not item.evidence_ids for item in report.target.entities)
    assert not (
        {item.id for item in report.observed.entities}
        & {item.id for item in report.target.entities if item.kind != "component"}
    )
    field = next(item for item in report.target.entities if item.id == "private-token")
    assert field.visibility.kind == "private"
    static = next(item for item in report.target.entities if item.id == "reset")
    assert static.modifiers == ("static",)
    if status == "PASS":
        assert {item.kind for item in (*report.observed.entities, *report.target.entities)} == set(
            get_args(EntityKind)
        )
        assert {item.status for item in report.comparison.assessments} == {"PASS"}
    elif status == "FAIL":
        assert any(
            item.status == "FAIL" and item.subject_id == "run" and item.aspect == "signature"
            for item in report.comparison.assessments
        )
    else:
        assert any(
            item.status == "UNKNOWN" and item.subject_id == "ready"
            for item in report.comparison.assessments
        )
        assert not any(item.status == "FAIL" for item in report.comparison.assessments)


@pytest.mark.parametrize(
    "variant,language", [("uml-dart", "dart"), ("uml-typescript", "typescript")]
)
def test_language_uml_demo_keeps_unsupported_inner_observation_unknown(
    tmp_path, capsys, variant, language
):
    output = tmp_path / "architecture.json"
    assert replay(variant, output) == 0
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result["declared_rules"] == "UNKNOWN"
    html = output.with_suffix(".report.html").read_text()
    payload = re.search(r'<script[^>]*id="flow-data"[^>]*>(.*?)</script>', html, re.S)
    assert payload
    report = parse_report(json.loads(payload.group(1)))
    assert {e.language for e in report.target.entities if e.kind != "component"} == {language}
    assert {e.kind for e in report.target.entities} >= {
        "module",
        "class",
        "interface",
        "enum",
        "enum_literal",
        "attribute",
        "method",
        "function",
        "binding",
        "type_alias",
        "constant",
    }
    assert not any(e.kind in {"class", "method", "function"} for e in report.observed.entities)
    assert report.comparison and any(
        a.status == "UNKNOWN" and a.subject_id == "run" for a in report.comparison.assessments
    )
    assert not any(a.status == "FAIL" for a in report.comparison.assessments)
    assert all(
        any(
            a.subject_id == identity and a.aspect == "existence" and a.status == "PASS"
            for a in report.comparison.assessments
        )
        for identity in ("core-module", "app-module")
    )
    assert any(r.kind == "imports" for r in report.observed.relationships)


@pytest.mark.parametrize("variant", ["uml-match", "uml-complete", "uml-dart", "uml-typescript"])
def test_language_uml_demo_uses_shared_browser_acceptance(tmp_path, capsys, variant):
    api = pytest.importorskip("playwright.sync_api")
    from tools.report_browser import _check_inner_uml

    output = tmp_path / "architecture.json"
    assert replay(variant, output) == 0
    capsys.readouterr()
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(output.with_suffix(".report.html").as_uri())
            _check_inner_uml(page, variant, tmp_path)
            assert not errors
        finally:
            browser.close()
