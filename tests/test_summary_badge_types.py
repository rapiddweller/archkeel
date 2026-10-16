# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Display states are nominal while valid legacy inputs keep their wire spelling."""

import json
from dataclasses import FrozenInstanceError, asdict
from enum import StrEnum

import pytest

from archkeel.ir.architecture_graph import AssessmentStatus
from archkeel.ir.model import Verdict
from archkeel.render import summary


@pytest.mark.parametrize("state", ["pass", "fail", "info", "unknown"])
def test_legacy_badge_constructor_normalizes_a_known_display_state(state):
    value = summary.Badge(state, "symbol", "label")
    assert isinstance(value.state, StrEnum), value
    assert value.state == state
    assert json.dumps(asdict(value)) == json.dumps(
        {"state": state, "symbol": "symbol", "label": "label"}
    )
    with pytest.raises(FrozenInstanceError):
        value.label = "changed"


@pytest.mark.parametrize(
    ("value", "state", "symbol", "label"),
    [
        ("PASS", "pass", "✓", "PASS"),
        ("FAIL", "fail", "×", "FAIL"),
        ("UNKNOWN", "unknown", "?", "UNKNOWN"),
        ("n/a", "info", "i", "NOT APPLICABLE"),
        ("unrecognized status", "unknown", "?", "NOT CHECKED"),
        ("", "unknown", "?", "NOT CHECKED"),
    ],
)
def test_real_badge_projection_preserves_display_bytes_with_a_nominal_state(
    value, state, symbol, label
):
    result = summary.badge(value)
    assert isinstance(result.state, StrEnum), result
    assert asdict(result) == {"state": state, "symbol": symbol, "label": label}
    assert f"{result.state}" == state


def test_badge_projection_accepts_distinct_existing_verdict_domains():
    assert type(AssessmentStatus.PASS) is not type(Verdict.PASS)
    assert summary.badge(AssessmentStatus.PASS) == summary.badge(Verdict.PASS)
    assert isinstance(summary.badge(AssessmentStatus.UNKNOWN).state, StrEnum)


def test_badge_rejects_an_invalid_display_state_at_its_constructor_boundary():
    with pytest.raises(ValueError):
        summary.Badge("not a display state", "?", "INVALID")


def test_legacy_summary_exports_are_the_same_owned_objects():
    from archkeel.render import summary_badges

    assert summary.Badge is summary_badges.Badge
    assert summary.badge is summary_badges.badge
    assert summary.State is summary_badges.BadgeState
    assert summary.BadgeState is summary_badges.BadgeState
    assert {state.value for state in summary_badges.BadgeState} == {"pass", "fail", "info", "unknown"}
    assert summary.Badge(summary_badges.BadgeState.INFO, "i", "DRAFT").state is (
        summary_badges.BadgeState.INFO
    )


def test_badge_html_states_and_declaration_style_in_chromium():
    api = pytest.importorskip("playwright.sync_api")
    from browser_report_support import _browser_page

    from archkeel.ir.architecture_graph import RuleAssessment, RuleAssessmentStatus
    from archkeel.render.html import _document, _rule_assessment_row, _verdict_card

    values = ("PASS", "FAIL", "UNKNOWN", "n/a", "other")
    cards = "".join(
        _verdict_card(summary.VerdictRow("Verdict", "", value, "Evidence")) for value in values
    )
    rows = "".join(
        _rule_assessment_row(
            RuleAssessment("rule", "permission", status, True, 0, 0, "", "", (), "", "", ())
        )
        for status in RuleAssessmentStatus
    )
    document = _document(
        repository="sample",
        kind="report",
        title="Badges",
        content=cards + "<table>" + rows + "</table>",
    )
    playwright, browser, page = _browser_page(api, document.decode())
    try:
        assert page.locator(".verdict-card").evaluate_all(
            "nodes => nodes.map(node => node.dataset.verdict)"
        ) == ["pass", "fail", "unknown", "info", "unknown"]
        assert page.locator(".verdict-state").all_text_contents() == [
            "✓PASS",
            "×FAIL",
            "?UNKNOWN",
            "iNOT APPLICABLE",
            "?NOT CHECKED",
        ]
        assert page.locator("strong[data-status]").evaluate_all(
            "nodes => nodes.map(node => [node.dataset.status, node.textContent])"
        ) == [["pass", "PASS"], ["fail", "FAIL"], ["unknown", "UNKNOWN"], ["info", "DECLARATION"]]
    finally:
        browser.close()
        playwright.stop()
