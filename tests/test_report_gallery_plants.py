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


def _failing_plants() -> list[dict]:
    """A plant that breaks a rule names the rule, the source and the target of its finding."""
    return [run for run in _plant_runs() if run["intent"] == "FAIL"]


def test_the_matrix_plants_one_violation_for_each_kind_the_reviewer_named() -> None:
    plants = {run["name"]: run["plant"]["rule"] for run in _failing_plants()}
    # The three that the review verified, then forbidden dependency, layer direction, cycle,
    # interface boundary and a complete requires.
    assert plants["M-plant-cycle"] == "COMPONENT-NO-CYCLES"
    assert plants["G-dart-plant-dart-io"] == "DEP-DOMAIN-NO-DART-IO"
    assert plants["H-uml-plant-signature"].startswith("UML-TARGET-")
    assert plants["H-uml-plant-closed-scope"].startswith("UML-TARGET-")
    assert plants["H-typescript-plant-domain-data"] == "DOMAIN-NO-DATA"
    assert plants["F-architecture-plant-layer"] == "DEP-MODEL-NO-APP"
    assert plants["M-plant-interface"] == "INTERFACE-BOUNDARY"
    assert plants["M-plant-requires"] == "REQUIRES-COMPLETE"
    for run in _failing_plants():
        assert run["section"] == "violation", run["name"]
    # A plant that makes a rule UNKNOWN names no finding and sits under what UNKNOWN means.
    partial = next(run for run in _plant_runs() if run["name"] == "H-uml-plant-partial")
    assert partial["section"] == "unknown" and partial["intent"] == "UNKNOWN"
    assert "rule" not in partial["plant"]


@pytest.mark.parametrize("run", _failing_plants(), ids=lambda run: run["name"])
def test_each_plant_names_a_rule_of_its_contract_and_its_line_is_in_the_planted_text(
    run: dict,
) -> None:
    source = report_gallery.ROOT / "fixtures" / run["root"]
    contract = json.loads((source / run["contract"][0]).read_text())
    rules = {rule["id"] for rule in contract["rules"]}
    assert run["plant"]["rule"] in rules or run["plant"]["rule"].startswith("UML-TARGET-")
    assert run["plant"]["source"] and run["plant"]["target"]
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
    seen = json.loads((tmp_path / "M-plant-cycle" / "report.html").read_text())
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


def _block(number: int, title: str, rules: list[str], *names: str) -> str:
    """A block like the core writes it: a title, the places it names and each rule it violates."""
    said = "".join(f"<li>{name}</li>" for name in names)
    broken = "".join(f"<p>Violates {rule} \u00b7 cause</p>" for rule in rules)
    return (
        f'<article class="rp-dos" id="x{number}"><h3 class="h3">{title}</h3>'
        f"<ul>{said}</ul>{broken}</article>"
    )


def _plant(rule: str, source: str, target: str) -> dict:
    return {"rule": rule, "source": source, "target": target}


def _page(tmp_path: Path, *blocks: str) -> Path:
    page = tmp_path / "report.html"
    page.write_text("".join(blocks) + "</section>")
    return page


def test_the_violation_block_is_found_by_its_rule_its_source_and_its_target(
    tmp_path: Path,
) -> None:
    page = _page(
        tmp_path,
        _block(1, "a.b imports c.d", ["REQUIRES-COMPLETE"], "a.b", "c.d"),
        _block(2, "Cycle of <b>2</b> members", ["COMPONENT-NO-CYCLES"], "pricing", "checkout"),
    )
    found = report_gallery.violation_block(page, _plant("REQUIRES-COMPLETE", "a.b", "c.d"))
    assert found == {"id": "x1", "title": "a.b imports c.d"}
    cycle = report_gallery.violation_block(
        page, _plant("COMPONENT-NO-CYCLES", "pricing", "checkout")
    )
    assert cycle == {"id": "x2", "title": "Cycle of 2 members"}
    assert report_gallery.violation_block(page, _plant("OTHER", "a.b", "c.d")) is None
    assert report_gallery.violation_block(tmp_path / "none.html", _plant("X", "a", "b")) is None


def test_two_plants_that_break_the_same_rule_each_link_their_own_block(tmp_path: Path) -> None:
    """The three findings of one rule share a rule id: only the source and the target tell them."""
    page = _page(
        tmp_path,
        _block(1, "core imports calls a", ["UML-TARGET-1"], "core", "calls a"),
        _block(2, "core imports inherits b", ["UML-TARGET-1"], "core", "ref:typing.Protocol"),
        _block(3, "core imports inherits c", ["UML-TARGET-1"], "core", "ref:enum.Enum"),
    )
    for number, target in ((2, "ref:typing.Protocol"), (3, "ref:enum.Enum"), (1, "calls a")):
        found = report_gallery.violation_block(page, _plant("UML-TARGET-1", "core", target))
        assert found is not None and found["id"] == f"x{number}", target


def test_overlapping_rules_on_one_import_do_not_swap_the_blocks_of_two_plants(
    tmp_path: Path,
) -> None:
    """One import can break two rules; the core writes two blocks for it. This is the shape of
    M-plant-interface: x1 holds REQUIRES-COMPLETE, x2 holds INTERFACE-BOUNDARY, both from api."""
    page = _page(
        tmp_path,
        _block(
            1,
            "orders.api imports orders.pricing.tax",
            ["REQUIRES-COMPLETE"],
            "orders.api",
            "orders.pricing.tax",
        ),
        _block(
            2,
            "orders.api imports orders.pricing.tax:Vat",
            ["INTERFACE-BOUNDARY"],
            "orders.api",
            "orders.pricing.tax:Vat",
        ),
    )
    requires = _plant("REQUIRES-COMPLETE", "orders.api", "orders.pricing.tax")
    boundary = _plant("INTERFACE-BOUNDARY", "orders.api", "orders.pricing.tax:Vat")
    assert report_gallery.violation_block(page, requires)["id"] == "x1"  # type: ignore[index]
    assert report_gallery.violation_block(page, boundary)["id"] == "x2"  # type: ignore[index]
    # A block that holds the right rule but another edge is not the finding.
    other = _plant("REQUIRES-COMPLETE", "orders.api", "orders.storage")
    assert report_gallery.violation_block(page, other) is None


def test_a_rule_id_that_only_starts_like_another_is_not_that_rule(tmp_path: Path) -> None:
    page = _page(tmp_path, _block(1, "a imports b", ["R-10", "R-1-X"], "a", "b"))
    assert report_gallery.violation_block(page, _plant("R-1", "a", "b")) is None
    assert report_gallery.violation_block(page, _plant("R-10", "a", "b")) is not None
    # A name inside a longer name is not the name: `a` is not `a.b`.
    longer = _page(tmp_path, _block(1, "a.b imports c.d", ["R-1"], "a.b", "c.d"))
    assert report_gallery.violation_block(longer, _plant("R-1", "a", "c.d")) is None


def _planted_row(block: dict | None) -> dict:
    plant = {"where": "a/b.py", "line": "import <x>", "rule": "R-1", "source": "a", "target": "b"}
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


def test_a_plant_that_makes_a_rule_unknown_shows_the_planted_line_and_no_link() -> None:
    plant = {"where": "demo/core.py", "line": "READY = auto()", "edits": []}
    run = {"name": "p", "section": "unknown", "intent": "UNKNOWN", "about": "a", "plant": plant}
    summary = {**FAIL_SUMMARY, "status": "UNKNOWN"}
    row = {"run": run, "links": [("HTML", "p/report.html")], "summary": summary}
    card = _section(report_gallery_page.index([row], "sha", "now"), "unknown")
    assert "Planted in <code>demo/core.py</code>: <code>READY = auto()</code>." in card
    assert "Caught by" not in card and "No violation block" not in card and "#x" not in card
    assert "UNKNOWN on purpose</span> · UNKNOWN" in card
