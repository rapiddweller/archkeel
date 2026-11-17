# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The cards of the showcase page: premises, the self-check and its named work (AD-462)."""

from __future__ import annotations

from tools import report_gallery, report_gallery_page


def _passing(assuming: str | None) -> dict:
    run = {"name": "n", "section": "clean", "intent": "PASS", "about": "a"}
    summary = {"status": "PASS", "counts": {"PASS": 1, "FAIL": 0, "UNKNOWN": 0}, "gaps": {}}
    return {"run": run, "links": [], "summary": {**summary, "refusal": None}, "assuming": assuming}


def test_a_pass_under_a_premise_shows_the_premise_text_and_a_plain_pass_does_not() -> None:
    page = report_gallery_page.index([_passing("outside <code> is fixed")], "sha", "now")
    assert "PASS assuming outside &lt;code&gt; is fixed." in page
    plain = report_gallery_page.index([_passing(None)], "sha", "now")
    assert "assuming" not in plain.split("<tbody>")[1]
    failing = _passing("p")
    failing["summary"]["status"] = "UNKNOWN"
    assert "assuming" not in report_gallery_page.index([failing], "sha", "now").split("<tbody>")[1]


def test_the_matrix_card_of_the_standard_library_demo_expects_a_pass_under_its_premise() -> None:
    runs = {run["name"]: run for run in report_gallery.showcase_runs()}
    stdlib = runs["python-stdlib-demo"]
    assert stdlib["intent"] == "PASS" and stdlib["expect"]["status"] == "PASS"
    assert "standard_library_unchanged" in stdlib["about"]


def test_the_compass_card_is_blocked_by_the_uml_row_only_and_uses_the_workspace_layout() -> None:
    compass = {run["name"]: run for run in report_gallery.showcase_runs()}["J-compass"]
    assert compass["blocked_by"] == [1762] and compass["intent"] == "PASS"
    assert compass["expect"]["counts"] == {"PASS": 6, "FAIL": 0, "UNKNOWN": 1}
    folder = report_gallery.ROOT / "fixtures" / "J-compass"
    assert 'roots = ["compass_app/app/lib"]' in (folder / "archkeel.toml").read_text()
    assert len(list(folder.rglob("pubspec.yaml"))) == 37


def test_the_self_check_card_is_held_by_named_work_in_the_normal_colour() -> None:
    line = report_gallery_page.intent_line(report_gallery_page.ANCHOR, "UNKNOWN")
    assert "expected PASS" in line and "UNKNOWN today" in line
    assert "held by sound gaps of the Rust collector (" in line
    assert f'href="{report_gallery_page.REPOSITORY}/issues/1571">#1571</a>' in line
    assert "the precision work is in progress" in line
    assert "ak-t-fail" not in line and "scenario not met" not in line and "blocked by" not in line


def test_issues_that_one_piece_of_work_closes_together_read_as_one_group() -> None:
    run = {**report_gallery_page.ANCHOR, "blocked_by": [1571, [1515, 1516]]}
    plain = report_gallery_page.intent_line(run, "UNKNOWN")
    assert ">#1571</a>, " in plain
    assert ">#1515</a>/" in plain and ">#1516</a>" in plain
