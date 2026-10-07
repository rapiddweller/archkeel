# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""TypeScript inner facts stay separate from and comparable to declared Target."""

from __future__ import annotations

import json

import pytest
from test_uml_demo import _demo_report

from fixtures.architecture_demo import replay

VARIANTS = (
    ("uml-typescript-match", "PASS", 0),
    ("uml-typescript-mismatch", "FAIL", 2),
    ("uml-typescript-partial", "UNKNOWN", 0),
)


@pytest.mark.parametrize("variant,status,exit_code", VARIANTS)
def test_typescript_target_facts_and_browser_views(tmp_path, capsys, variant, status, exit_code):
    output = tmp_path / f"{variant}.json"
    assert replay(variant, output) == exit_code
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result["declared_rules"] == status

    report = _demo_report(output)
    assert report.comparison is not None and report.comparison.status == status
    assert report.observed.origin == "observed" and report.target.origin == "declared"
    observed_names = {item.qualified_name: item for item in report.observed.entities}
    target_names = {item.qualified_name: item for item in report.target.entities}
    expected_names = {
        "demo.src.core_x2e_ts.Port",
        "demo.src.core_x2e_ts.Base",
        "demo.src.core_x2e_ts.Client",
        "demo.src.core_x2e_ts.Client.run",
        "demo.src.core_x2e_ts.Client._token",
        "demo.src.core_x2e_ts.Client.limit",
        "demo.src.core_x2e_ts.Client.reset",
        "demo.src.core_x2e_ts.State.READY",
        "demo.src.core_x2e_ts.build.item",
        "demo.src.core_x2e_ts.Text",
        "demo.src.core_x2e_ts.VERSION",
        "demo.src.app_x2e_ts.work",
    }
    assert expected_names <= observed_names.keys()
    assert expected_names <= target_names.keys()
    assert not (
        {item.id for item in report.observed.entities}
        & {item.id for item in report.target.entities}
    )
    assert observed_names["demo.src.core_x2e_ts.Client._token"].visibility.kind == "private"
    assert observed_names["demo.src.core_x2e_ts.Client.limit"].modifiers == ("static",)
    assert observed_names["demo.src.core_x2e_ts.Client.reset"].modifiers == ("static",)

    names = {item.id: item.qualified_name for item in report.observed.entities}
    relationships = {
        (item.kind, names[item.source_id], names[item.target_id])
        for item in report.observed.relationships
        if item.target_id is not None
    }
    assert ("inherits", "demo.src.core_x2e_ts.Client", "demo.src.core_x2e_ts.Base") in relationships
    assert ("realizes", "demo.src.core_x2e_ts.Client", "demo.src.core_x2e_ts.Port") in relationships
    assert (
        "calls",
        "demo.src.core_x2e_ts.Client.run",
        "demo.src.core_x2e_ts.helper",
    ) in relationships
    assert ("calls", "demo.src.app_x2e_ts.work", "demo.src.core_x2e_ts.helper") in relationships
    if variant == "uml-typescript-partial":
        assert any(
            item.kind == "creates" and item.target_id is None and item.resolution == "unresolved"
            for item in report.observed.relationships
        )
        assert any(
            item.kind == "instance_of"
            and item.target_id is None
            and item.resolution == "unresolved"
            for item in report.observed.relationships
        )
        assert not any(item.status == "FAIL" for item in report.comparison.assessments)
    else:
        assert (
            "creates",
            "demo.src.core_x2e_ts.build",
            "demo.src.core_x2e_ts.Unit",
        ) in relationships
        assert (
            "instance_of",
            "demo.src.core_x2e_ts.build.item",
            "demo.src.core_x2e_ts.Unit",
        ) in relationships
    if variant == "uml-typescript-match":
        assert report.comparison.status == "PASS"
        expected_matches = {
            "client-base",
            "client-port",
            "run-helper",
            "build-unit-reference",
            "app-import",
            "work-helper",
            "build-unit",
            "item-unit",
            "client-base-reference",
            "client-port-reference",
            "build-unit-call",
        }
        matched = {
            item.subject_id
            for item in report.comparison.assessments
            if item.aspect == "relationship" and item.status == "PASS"
        }
        assert expected_matches <= matched
        assert any(
            item.subject_id == "run-token"
            and item.aspect == "relationship"
            and item.status == "PASS"
            for item in report.comparison.assessments
        )
    if variant == "uml-typescript-mismatch":
        assert any(
            item.status == "FAIL" and item.subject_id == "reset" and item.aspect == "signature"
            for item in report.comparison.assessments
        )

    api = pytest.importorskip("playwright.sync_api")
    from tools.report_browser import _check_inner_uml

    errors = []
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(output.with_suffix(".report.html").as_uri() + "?theme=dark")
            assert page.locator("html").get_attribute("data-theme") == "dark"
            _check_inner_uml(page, variant, tmp_path)
            assert page.locator("html").get_attribute("data-theme") == "dark"
            page.screenshot(path=str(tmp_path / f"{variant}-dark.png"))
            assert not errors
        finally:
            browser.close()


def test_typescript_match_and_changes_keep_one_independent_target(tmp_path, capsys):
    targets = []
    for variant, _, exit_code in VARIANTS:
        output = tmp_path / f"{variant}.json"
        assert replay(variant, output) == exit_code
        capsys.readouterr()
        targets.append(_demo_report(output).target)
    assert targets[0] == targets[1] == targets[2]
