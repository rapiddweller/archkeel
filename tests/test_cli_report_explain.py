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
from planted_cycle import cycle_root as cycle_root
from rust_repository import CRATE_RULES, component, report, repository
from rust_repository import rule as crate_rule

from archkeel.cli import core_only

FIXTURES = ROOT / "fixtures"


def frame_of(
    core: Path, monkeypatch: pytest.MonkeyPatch, root: Path, config: str
) -> tuple[int, dict[str, Any]]:
    monkeypatch.setattr(core_only, "locate_core", lambda: core)
    code, found = run("report", "--root", str(root), "--config", config)
    frame: dict[str, Any] = found["frame"]
    return code, frame


def test_a_planted_cycle_gives_one_closed_path(
    release_core: Path, monkeypatch: pytest.MonkeyPatch, cycle_root: Path
) -> None:
    code, frame = frame_of(release_core, monkeypatch, cycle_root, "archkeel.toml")
    assert code == 1 and frame["rules"]["APP-NO-MODULE-CYCLES"][1] == "FAIL"
    cycles = frame["explain"]["cycles"]["APP-NO-MODULE-CYCLES"]
    details = frame["details"]["APP-NO-MODULE-CYCLES"]
    assert (cycles["total"], cycles["truncated"], len(cycles["items"])) == (1, False, 1)
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
    assert [item["index"] for item in cycles["items"]] == list(range(1))


def test_the_shell_run_gives_the_sides_of_each_of_its_rules(
    release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scan = tomllib.loads((ROOT / "docs/architecture/shell.toml").read_text())["scan"]
    contract = json.loads((ROOT / scan["contract"]).read_text())
    ids = {component["id"] for component in contract["components"]}
    _, frame = frame_of(release_core, monkeypatch, ROOT, "docs/architecture/shell.toml")
    shapes = frame["explain"]["rules"]
    assert frame["rules"] and set(shapes) == set(frame["rules"])
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
    # The five requires rules wait for the imports. The UML target row has another cause.
    uml = [rule for rule in unknown if rule.startswith("UML-TARGET")]
    gapped = [rule for rule in unknown if rule not in uml]
    assert sorted(holds["rules"]) == unknown and (len(gapped), len(uml)) == (5, 1)
    other = holds["rules"][uml[0]]
    assert (other["kind"], other["total"], other["gaps"]) == ("other", 0, [])
    # AD-1510: the 82 gaps are resolution gaps. Each leaves the code of every module unknown, and no
    # gap names the unresolved imports by their evidence, so the imports are the first cause.
    total = holds["gaps_total"]
    assert total > 20 and holds["gaps_holding"] == 0 and holds["gaps"] == []
    for rule in gapped:
        held = holds["rules"][rule]
        assert (held["kind"], held["total"], held["gaps"]) == ("unknown_imports", 0, [])
        assert held["unnamed_imports"] > 100 and held["cause"] == frame["unknown_kinds"][rule]
    assert frame["scope"].startswith("incomplete scope: ")
    assert "imports are not resolved and no gap names them" in frame["scope"]


LIB = "mod a;\nmod b;\nmod c;\n"


def test_a_known_return_edge_fails_the_component_cycle_rule(
    tmp_path: Path, release_core: Path
) -> None:
    app = component("app", "app", ("base",))
    app["packages"] = []
    app["exact_modules"] = ["native.app", "native.app.cargo_toml"]
    prefix = "crates/app/src/"
    rule = "NO-CYCLES"
    for closed in (False, True):
        root = repository(
            tmp_path / str(closed),
            release_core,
            {
                prefix + "lib.rs": "mod a;\nmod b;\n",
                prefix + "a.rs": "pub fn value() -> u8 { 1 }\n"
                + ("pub fn run() -> u8 { crate::b::read() }\n" if closed else ""),
                prefix + "b.rs": "pub fn read() -> u8 { crate::a::value() }\n",
            },
            components=(
                component("base", "base_crate"),
                app,
                component("a", "app.a", ("b",) if closed else ()),
                component("b", "app.b", ("a",)),
            ),
        )
        frame = report(root)["frame"]
        assert frame["rules"][rule][1] == ("FAIL" if closed else "PASS"), frame
        if closed:
            [cycle] = frame["explain"]["cycles"][rule]["items"]
            assert {(step["from"], step["to"]) for step in cycle["path"]} == {
                ("a", "b"),
                ("b", "a"),
            }
            assert all(step["evidence"] and not step.get("possible") for step in cycle["path"])


def _calls(name: str, impl: str) -> str:
    """A module that calls `s.name(1)` on a receiver that the scan cannot prove (`let s = s;`),
    and holds `impl crate::c::S { pub fn impl(&self, x) }`: the pair gap of the call."""
    return (
        f"pub fn call_{name}(s: &crate::c::S) {{\n    let s = s;\n    s.{name}(1);\n}}\n"
        f"impl crate::c::S {{\n    pub fn {impl}(&self, x: u8) {{}}\n}}\n"
    )


def test_a_pair_gap_holds_only_the_rules_that_it_can_change(
    tmp_path: Path, core_binary: Path
) -> None:
    # The self run has no pair gap any more, so this project holds two: `a -> b` and `b -> a`,
    # each through a method that the scan cannot tie to its type. The cycle rule and the
    # requires rule can change with them; a rule that already holds cannot.
    files = {
        "lib.rs": LIB,
        "c.rs": "pub struct S;\n",
        "a.rs": _calls("m", "n"),
        "b.rs": _calls("n", "m"),
    }
    cycles = crate_rule("MODULE-CYCLES", "no_component_cycles", level="module")
    root = repository(
        tmp_path,
        core_binary,
        {f"crates/app/src/{name}": text for name, text in files.items()},
        rules=(*CRATE_RULES, cycles),
    )
    frame = report(root)["frame"]
    holds = frame["explain"]["holds"]
    pair_rules = {r: h for r, h in holds["rules"].items() if h["kind"] == "pair_gaps"}
    unknown = {r for r, row in frame["rules"].items() if row[1] == "UNKNOWN"}
    assert "MODULE-CYCLES" in pair_rules and set(pair_rules) <= unknown
    by_gap = {gap["id"]: gap for gap in holds["gaps"]}
    for rule_id, held in pair_rules.items():
        assert held["pairs"] and held["total"] >= len(held["pairs"])
        assert held["gaps"], rule_id
        assert all(rule_id in by_gap[gap]["rules"] for gap in held["gaps"])
    # A rule that no kept gap can change has no hold of this kind.
    passing = {r for r, row in frame["rules"].items() if row[1] == "PASS"}
    assert passing and not passing & set(holds["rules"])
