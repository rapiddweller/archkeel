# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The onboarding demo prints what the commands actually answer, or it prints nothing."""

from pathlib import Path

import pytest

from fixtures.reproduce_onboarding import Step, run_onboarding_demo


@pytest.fixture(scope="module")
def steps(tmp_path_factory: pytest.TempPathFactory) -> tuple[Step, ...]:
    return run_onboarding_demo(tmp_path_factory.mktemp("onboarding"))


def test_the_loop_runs_agent_gate_architect_gate_agent_gate(steps: tuple[Step, ...]) -> None:
    """Who acts when is the point of the demo, so the order is asserted, not just the counts."""
    assert [step.actor for step in steps] == ["agent", "gate", "architect", "gate", "agent", "gate"]


def test_init_drafts_the_five_components_and_decides_no_pair(steps: tuple[Step, ...]) -> None:
    assert steps[0].outcome == "5 components, 20 open decisions, 0 dependency rules"
    assert "app, cli, model, render, store" in steps[0].detail[0]


def test_validate_refuses_a_drafted_contract(steps: tuple[Step, ...]) -> None:
    assert steps[1].outcome == "exit 2, 20 x decision.open"


def test_the_decided_contract_passes(steps: tuple[Step, ...]) -> None:
    assert steps[2].outcome == "exit 0, no diagnostics"


def test_the_report_names_one_component_larger_than_its_level(steps: tuple[Step, ...]) -> None:
    assert steps[3].outcome == "1 component larger than its own level"


def test_init_drafts_the_inside_the_architect_consolidates(steps: tuple[Step, ...]) -> None:
    assert steps[4].outcome == "4 sub-components, 12 open decisions"
    assert "backend, codec, repository, sqlite" in steps[4].detail[0]
    assert "api, backend, codec, repository" in steps[4].detail[1]


def test_a_crossing_inside_the_level_is_caught_and_named_for_it(steps: tuple[Step, ...]) -> None:
    assert steps[5].outcome == "FAIL, 3 violations: store:STORE-REQUIRES-COMPLETE"


def test_every_step_names_a_real_archkeel_command(steps: tuple[Step, ...]) -> None:
    assert all(step.command.startswith("archkeel ") for step in steps)


def test_the_demo_module_is_runnable_from_the_repository_root() -> None:
    assert (Path(__file__).parents[1] / "fixtures/reproduce_onboarding.py").is_file()
