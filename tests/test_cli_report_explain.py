# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-484: the frame names the shape of each rule, the path of each cycle and the gaps that hold
each rule, so that a page needs no rule text. Each test runs the default CLI on a real project."""

import json
import tomllib
from pathlib import Path
from typing import Any

import pytest
from core_support import ROOT, run
from frozen_native import frozen_root as frozen_root

from archkeel.cli import core_only

FIXTURES = ROOT / "fixtures"


def frame_of(
    core: Path, monkeypatch: pytest.MonkeyPatch, root: Path, config: str
) -> tuple[int, dict[str, Any]]:
    monkeypatch.setattr(core_only, "locate_core", lambda: core)
    code, found = run("report", "--root", str(root), "--config", config)
    frame: dict[str, Any] = found["frame"]
    return code, frame


def test_the_self_run_gives_one_closed_path_for_each_of_its_seven_cycles(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, frozen_root: Path
) -> None:
    code, frame = frame_of(release_core, monkeypatch, frozen_root, "native/archkeel.toml")
    assert code == 1 and frame["rules"]["NATIVE-NO-MODULE-CYCLES"][1] == "FAIL"
    cycles = frame["explain"]["cycles"]["NATIVE-NO-MODULE-CYCLES"]
    details = frame["details"]["NATIVE-NO-MODULE-CYCLES"]
    assert (cycles["total"], cycles["truncated"], len(cycles["items"])) == (7, False, 7)
    for item in cycles["items"]:
        path = item["path"]
        assert not item["truncated"] and item["steps_total"] == len(path) >= 2
        # The steps follow each other and close at the first member.
        assert [step["to"] for step in path[:-1]] == [step["from"] for step in path[1:]]
        assert path[-1]["to"] == path[0]["from"]
        assert {step["from"] for step in path} <= set(item["members"])
        # The row of `details` is the same cycle, and each step cites its imports.
        row = details[item["index"]]
        assert row["source"] == " -> ".join(item["members"])
        for step in path:
            assert step["imports"] >= 1 and step["evidence"]
            assert step["evidence_total"] >= len(step["evidence"])
            assert set(step["evidence"]) <= set(frame["locations"])
            assert set(step["evidence"]) <= set(row["evidence"])
    assert [item["index"] for item in cycles["items"]] == list(range(7))


def test_the_shell_run_gives_the_sides_of_each_of_its_rules(
    release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scan = tomllib.loads((ROOT / "docs/architecture/shell.toml").read_text())["scan"]
    contract = json.loads((ROOT / scan["contract"]).read_text())
    ids = {component["id"] for component in contract["components"]}
    _, frame = frame_of(release_core, monkeypatch, ROOT, "docs/architecture/shell.toml")
    shapes = frame["explain"]["rules"]
    assert len(frame["rules"]) == 22 and set(shapes) == set(frame["rules"])
    for rule, shape in shapes.items():
        assert shape["kind"] == frame["rules"][rule][0]
        assert set(shape["source"]) | set(shape["target"]) <= ids, rule
    forbids = {rule: shape for rule, shape in shapes.items() if shape["direction"] == "forbids"}
    assert forbids and all(shape["source"] and shape["target"] for shape in forbids.values())
    assert {shape["direction"] for shape in shapes.values()} >= {"forbids", "acyclic", "none"}


def test_an_unknown_run_names_the_gaps_of_each_rule_and_the_rules_of_each_gap(
    release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = FIXTURES / "L-nest-realworld"
    code, frame = frame_of(release_core, monkeypatch, root, "archkeel.toml")
    assert code == 2 and frame["status"] == "UNKNOWN"
    unknown = sorted(rule for rule, row in frame["rules"].items() if row[1] == "UNKNOWN")
    holds = frame["explain"]["holds"]
    # The five requires rules wait for the gaps. The UML target row has another cause.
    uml = [rule for rule in unknown if rule.startswith("UML-TARGET")]
    gapped = [rule for rule in unknown if rule not in uml]
    assert sorted(holds["rules"]) == unknown and (len(gapped), len(uml)) == (5, 1)
    other = holds["rules"][uml[0]]
    assert (other["kind"], other["total"], other["gaps"]) == ("other", 0, [])
    by_gap = {gap["id"]: gap for gap in holds["gaps"]}
    assert holds["gaps_total"] == 68 and holds["gaps_holding"] == len(by_gap) == 68
    for rule in gapped:
        held = holds["rules"][rule]
        assert (held["kind"], held["total"], held["truncated"]) == ("coverage_gaps", 68, True)
        assert len(held["gaps"]) == 20 and held["cause"] == frame["unknown_kinds"][rule]
        # Both directions agree: a gap that a rule lists lists that rule.
        assert all(rule in by_gap[gap]["rules"] for gap in held["gaps"])
    assert all(sorted(gap["rules"]) == gapped for gap in by_gap.values())
    assert all(gap["rules_total"] == 5 and not gap["truncated"] for gap in by_gap.values())
    assert frame["scope"].endswith("68 coverage gaps")


def test_a_pair_gap_holds_only_the_rules_that_it_can_change(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, frozen_root: Path
) -> None:
    _, frame = frame_of(release_core, monkeypatch, frozen_root, "native/archkeel.toml")
    holds = frame["explain"]["holds"]
    pair_rules = {r: h for r, h in holds["rules"].items() if h["kind"] == "pair_gaps"}
    assert pair_rules
    by_gap = {gap["id"]: gap for gap in holds["gaps"]}
    for rule, held in pair_rules.items():
        assert held["pairs"] and held["total"] >= len(held["pairs"])
        assert held["gaps"], rule
        assert all(rule in by_gap[gap]["rules"] for gap in held["gaps"])
    # A rule that no kept gap can change has no hold of this kind.
    passing = {r for r, row in frame["rules"].items() if row[1] == "PASS"}
    assert not passing & set(holds["rules"])
