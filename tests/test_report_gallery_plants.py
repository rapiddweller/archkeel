# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The violation scenarios of the gallery: a planted change on a clean copy (AD-462)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from test_report_gallery import _section

from tools import fixture_tree, report_gallery, report_gallery_page


def _plant_runs() -> list[dict]:
    return [run for run in report_gallery.showcase_runs() if run.get("plant")]


def test_the_matrix_plants_one_violation_for_each_kind_the_reviewer_named() -> None:
    plants = {run["name"]: run["plant"]["rule"] for run in _plant_runs()}
    # The three that the review verified, then forbidden dependency, layer direction, cycle,
    # interface boundary and a complete requires.
    assert plants["M-plant-cycle"] == "COMPONENT-NO-CYCLES"
    assert plants["G-dart-plant-dart-io"] == "DEP-DOMAIN-NO-DART-IO"
    assert plants["H-uml-plant-signature"] == "UML-TARGET"
    assert plants["H-typescript-plant-domain-data"] == "DOMAIN-NO-DATA"
    assert plants["F-architecture-plant-layer"] == "DEP-MODEL-NO-APP"
    assert plants["M-plant-interface"] == "INTERFACE-BOUNDARY"
    assert plants["M-plant-requires"] == "REQUIRES-COMPLETE"
    for run in _plant_runs():
        assert run["section"] == "violation" and run["intent"] == "FAIL", run["name"]


@pytest.mark.parametrize("run", _plant_runs(), ids=lambda run: run["name"])
def test_each_plant_names_a_rule_of_its_contract_and_its_line_is_in_the_planted_text(
    run: dict,
) -> None:
    source = report_gallery.ROOT / "fixtures" / run["root"]
    contract = json.loads((source / run["contract"][0]).read_text())
    rules = {rule["id"] for rule in contract["rules"]}
    assert run["plant"]["rule"] in rules or run["plant"]["rule"] == "UML-TARGET"
    with fixture_tree.fixture_tree(source, run["plant"]["edits"]) as tree:
        text = (tree / run["plant"]["where"]).read_text()
    assert run["plant"]["line"] in text
    # The fixture itself never holds the planted line.
    assert run["plant"]["line"] not in (source / run["plant"]["where"]).read_text()


def test_a_planted_edit_that_does_not_fit_its_fixture_fails_loudly(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\nx = 1\n")
    with pytest.raises(ValueError, match="must stand once"):
        fixture_tree.apply_edit(tmp_path, {"path": "a.py", "old": "x = 1\n", "new": "y"})
    with pytest.raises(ValueError, match="must stand once"):
        fixture_tree.apply_edit(tmp_path, {"path": "a.py", "old": "z", "new": "y"})
    with pytest.raises(ValueError, match="unknown edit"):
        fixture_tree.apply_edit(tmp_path, {"path": "a.py"})
    fixture_tree.apply_edit(tmp_path, {"path": "b/c.py", "append": "z = 2\n"})
    assert (tmp_path / "b" / "c.py").read_text() == "z = 2\n"


def test_a_plant_run_applies_its_edit_to_a_copy_and_the_fixture_stays_clean(tmp_path: Path) -> None:
    script = tmp_path / "probe.py"
    script.write_text(PLANT_PROBE)
    run = next(run for run in _plant_runs() if run["name"] == "M-plant-cycle")
    row = report_gallery.build_run([sys.executable, str(script)], run, tmp_path)
    seen = json.loads((tmp_path / "M-plant-cycle" / "report.json").read_text())
    assert "error" not in row
    assert run["plant"]["line"] in seen["text"]
    assert seen["root"] == "<repo>/fixtures/M-review-workflow"
    clean = report_gallery.ROOT / "fixtures" / "M-review-workflow" / run["plant"]["where"]
    assert run["plant"]["line"] not in clean.read_text()


PLANT_PROBE = """
import json, os, sys
args = sys.argv[1:]
root = args[args.index("--root") + 1]
text = open(os.path.join(root, "orders", "pricing", "tax.py")).read()
with open(args[args.index("--output") + 1], "w") as handle:
    handle.write(json.dumps({"root": root, "text": text}))
print(json.dumps({"status": "FAIL", "exit_code": 1, "gaps": [], "frame": {"rules": {}}}))
"""

BLOCKS = (
    '<article class="rp-dos" id="x1"><h3 class="h3">a.b imports c.d</h3>'
    "<p>REQUIRES-COMPLETE</p></article>"
    '<article class="rp-dos" id="x2"><h3 class="h3">Cycle of <b>2</b> members</h3>'
    "<p>COMPONENT-NO-CYCLES</p></article></section>"
)


def test_the_violation_block_is_found_by_the_rule_it_lists(tmp_path: Path) -> None:
    page = tmp_path / "report.html"
    page.write_text(BLOCKS)
    assert report_gallery.violation_block(page, "REQUIRES-COMPLETE") == {
        "id": "x1",
        "title": "a.b imports c.d",
    }
    found = report_gallery.violation_block(page, "COMPONENT-NO-CYCLES")
    assert found == {"id": "x2", "title": "Cycle of 2 members"}
    assert report_gallery.violation_block(page, "OTHER") is None
    assert report_gallery.violation_block(tmp_path / "missing.html", "X") is None


def _planted_row(block: dict | None) -> dict:
    plant = {"where": "a/b.py", "line": "import <x>", "rule": "R-1", "edits": []}
    row = {"run": _run_of("p", plant), "links": [("HTML", "p/report.html")]}
    return {**row, "violation": block} if block is not None else row


def _run_of(name: str, plant: dict) -> dict:
    return {"name": name, "section": "violation", "intent": "FAIL", "about": "a", "plant": plant}


def test_a_violation_card_shows_the_planted_line_and_links_the_violation_block() -> None:
    row = _planted_row({"id": "x3", "title": "a imports <b>"})
    page = report_gallery_page.index([{**row, "summary": FAIL_SUMMARY}], "sha", "now")
    card = _section(page, "violation")
    assert "Planted in <code>a/b.py</code>: <code>import &lt;x&gt;</code>" in card
    assert 'href="../p/report.html#x3">a imports &lt;b&gt;</a>' in card
    assert "Caught by <code>R-1</code>" in card
    assert "expected FAIL</span> · FAIL" in card


def test_a_violation_card_without_a_block_says_so_and_gives_no_link() -> None:
    row = {**_planted_row(None), "summary": FAIL_SUMMARY}
    card = _section(report_gallery_page.index([row], "sha", "now"), "violation")
    assert "No violation block of R-1 in the report." in card
    assert "#x" not in card


def test_a_plant_that_does_not_fail_is_a_scenario_not_met() -> None:
    row = {
        **_planted_row({"id": "x1", "title": "t"}),
        "summary": {**FAIL_SUMMARY, "status": "PASS"},
    }
    card = _section(report_gallery_page.index([row], "sha", "now"), "violation")
    assert "PASS today" in card and "scenario not met" in card


FAIL_SUMMARY = {
    "status": "FAIL",
    "counts": {"PASS": 0, "FAIL": 1, "UNKNOWN": 0},
    "gaps": {},
    "refusal": None,
}
