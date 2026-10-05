# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The onboarding demo prints what the commands actually answer, or it prints nothing."""

import json
from pathlib import Path

import pytest

from archkeel.check.onboarding import run_init
from archkeel.cli.observe import observe
from fixtures.reproduce_onboarding import Step, _repository, run_onboarding_demo
from tools.onboarding_svg import render


@pytest.fixture(scope="module")
def steps(tmp_path_factory: pytest.TempPathFactory) -> tuple[Step, ...]:
    return run_onboarding_demo(tmp_path_factory.mktemp("onboarding"))


def test_the_loop_runs_agent_gate_architect_gate_agent_architect_gate(
    steps: tuple[Step, ...],
) -> None:
    """Who acts when is the point of the demo, so the order is asserted, not just the counts."""
    assert [step.actor for step in steps] == [
        "agent",
        "gate",
        "architect",
        "gate",
        "agent",
        "architect",
        "gate",
    ]


def test_init_drafts_the_five_components_and_decides_no_pair(steps: tuple[Step, ...]) -> None:
    assert steps[0].outcome.startswith("5 components, 20 open decisions, ")
    assert "app, cli, model, render, store" in steps[0].detail[0]
    assert "interview" in " ".join(steps[0].detail).lower()
    assert "--force" in steps[0].command


def test_init_reports_the_dependency_rule_count_from_its_draft(
    steps: tuple[Step, ...], tmp_path: Path
) -> None:
    root = _repository(tmp_path)
    _, files = run_init(root, source="shop", namespace="shop", force=True, analyzer=observe)
    dependency_kinds = {"allowed_dependency", "forbidden_dependency"}
    rule_count = sum(
        rule["kind"] in dependency_kinds
        for rule in json.loads(files["architecture-contract.json"])["rules"]
    )
    assert rule_count == 0
    assert steps[0].outcome.endswith(f"{rule_count} dependency rules")


def test_validate_refuses_a_drafted_contract(steps: tuple[Step, ...]) -> None:
    assert steps[1].outcome == "exit 2, 20 open decisions, 1 decision.open panel"


def test_the_decided_contract_passes(steps: tuple[Step, ...]) -> None:
    assert steps[2].outcome == "exit 0, declared_rules PASS, 6 requires entries"


def test_the_report_names_one_component_larger_than_its_level(steps: tuple[Step, ...]) -> None:
    assert steps[3].outcome == "1 component larger than its own level"


def test_nested_draft_is_separate_from_architect_decision(steps: tuple[Step, ...]) -> None:
    assert steps[4].outcome == "4 sub-components, 12 open decisions"
    assert "backend, codec, repository, sqlite" in steps[4].detail[0]
    assert "api" not in steps[4].detail[0]
    assert "--force" in steps[4].command
    assert steps[5].actor == "architect"
    assert steps[5].outcome == "exit 0, declared_rules PASS, 3 requires entries"
    decision = " ".join(steps[5].detail).lower()
    assert "api" in decision and "shop.store.sqlite" in decision
    assert all(
        pair in decision
        for pair in ("api -> backend", "repository -> backend", "repository -> codec")
    )
    assert "complete_requires" in decision
    assert "architect" in decision
    approved = json.loads(
        (
            Path(__file__).parents[1]
            / "fixtures/F-architecture/shop/store/architecture-contract.json"
        ).read_text()
    )
    assert any(rule["kind"] == "complete_requires" for rule in approved["rules"])
    components = {item["label"]: item for item in approved["components"]}
    assert components["api"]["packages"] == ["shop.store.sqlite"]
    assert {
        label: [entry["component"] for entry in components[label].get("requires", [])]
        for label in ("api", "repository")
    } == {"api": ["backend"], "repository": ["backend", "codec"]}
    assert all(
        item["decided_by"] == "architect" for item in approved["components"] + approved["rules"]
    )


def test_a_crossing_inside_the_level_is_caught_and_named_for_it(steps: tuple[Step, ...]) -> None:
    assert steps[6].outcome == "FAIL, 3 violations: store:STORE-REQUIRES-COMPLETE"


def test_every_step_names_a_real_archkeel_command(steps: tuple[Step, ...]) -> None:
    assert all(step.command.startswith("archkeel ") for step in steps)
    assert all("approve" not in step.command for step in steps)


def test_the_demo_module_is_runnable_from_the_repository_root() -> None:
    assert (Path(__file__).parents[1] / "fixtures/reproduce_onboarding.py").is_file()


def test_the_committed_loop_figure_is_the_one_this_run_draws(steps: tuple[Step, ...]) -> None:
    """A figure nothing regenerates is a drawing of a past release. Run `make loop-figure`."""
    figure = Path(__file__).parents[1] / "docs/assets/archkeel-onboarding-loop.svg"
    assert figure.read_text() == render(steps)
