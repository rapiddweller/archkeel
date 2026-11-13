# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-89: contract-selected measurements share the validation baseline ratchet."""

import json
import subprocess
from pathlib import Path

from test_architecture_demo import CONFIG, _prepare_repo

from archkeel.check.validation import run_validate
from archkeel.cli.observe import observe
from archkeel.ir.codec import (
    baseline_bytes,
    parse_contract,
)
from archkeel.ir.measurements import MeasurementBudget, compare_budgets
from archkeel.ir.model import ArchitectureContract
from archkeel.ir.widening import contract_widenings, measurement_budget_widenings


def _contract_with_budgets(*names: str) -> str:
    contract = json.loads(
        (
            Path(__file__).parents[1] / "fixtures/F-architecture/architecture-contract.json"
        ).read_text()
    )
    contract["declarations"]["measurement_budgets"] = [
        {"name": name, "provenance": ["docs/architecture/shop.md"]} for name in names
    ]
    return json.dumps(contract, indent=2) + "\n"


def _repo(tmp_path: Path, *names: str) -> Path:
    return _prepare_repo(
        tmp_path / "repo", {"architecture-contract.json": _contract_with_budgets(*names)}
    )


def _baseline(root: Path, *budgets: MeasurementBudget) -> Path:
    path = root / "architecture-baseline.json"
    path.write_bytes(baseline_bytes((), budgets))
    return path


def test_a_refused_write_advises_no_rewrite_of_a_budget() -> None:
    """AD-106: the refused run's own last line names the way on; no budget line repeats it."""
    accepted = (MeasurementBudget("cycle_edges", 2), MeasurementBudget("typing_positions", 1))
    observed = (MeasurementBudget("cycle_edges", 0), MeasurementBudget("typing_positions", 3))

    assert compare_budgets(accepted, observed, against=False, refused=True) == (
        "measurement budget reduced in cycle_edges: 2->0",
        "measurement budget exceeded in typing_positions: 1->3",
    )


def test_declared_budget_requires_a_baseline(tmp_path: Path) -> None:
    result, _ = run_validate(_repo(tmp_path, "cycle_edges"), CONFIG, observe)

    assert result.exit_code == 2
    assert [item.code for item in result.diagnostics] == ["baseline.invalid"]


def test_declared_budget_requires_an_accepted_value(tmp_path: Path) -> None:
    root = _repo(tmp_path, "cycle_edges")
    baseline = _baseline(root)

    result, _ = run_validate(root, CONFIG, observe, baseline=baseline)

    assert result.exit_code == 2
    assert [item.code for item in result.diagnostics] == ["baseline.invalid"]


def test_against_requires_prior_budget_evidence(tmp_path: Path) -> None:
    root = _repo(tmp_path, "cycle_edges")
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    baseline = _baseline(root, MeasurementBudget("cycle_edges", 0))

    result, _ = run_validate(root, CONFIG, observe, baseline=baseline, against=base)

    assert result.exit_code == 2
    assert [item.code for item in result.diagnostics] == ["against.invalid"]


def test_unsupported_budget_is_contract_invalid(tmp_path: Path) -> None:
    result, _ = run_validate(_repo(tmp_path, "component_size"), CONFIG, observe)

    assert result.exit_code == 2
    assert [item.code for item in result.diagnostics] == ["contract.invalid"]


def test_raising_or_dropping_an_accepted_budget_is_a_widening() -> None:
    before = (MeasurementBudget("cycle_edges", 2),)

    assert measurement_budget_widenings(before, (MeasurementBudget("cycle_edges", 3),)) == (
        "measurement budget widened: cycle_edges (3 now, 2 before)",
    )
    assert measurement_budget_widenings(before, ()) == (
        "measurement budget baseline lost cycle_edges",
    )


def test_removing_a_budget_declaration_widens_but_adding_one_does_not() -> None:
    plain = parse_contract(json.loads(_contract_with_budgets()))
    budgeted = parse_contract(json.loads(_contract_with_budgets("cycle_edges")))

    assert contract_widenings(plain, budgeted) == ()
    assert contract_widenings(budgeted, plain) == (
        "contract.declarations.measurement_budgets lost 'cycle_edges'",
    )


def test_unrelated_declaration_presence_still_fails_closed() -> None:
    absent = parse_contract(json.loads(_contract_with_budgets()))
    present = parse_contract(json.loads(_contract_with_budgets()))
    absent = ArchitectureContract(
        absent.schema_version,
        absent.components,
        absent.rules,
        absent.schema,
    )

    assert contract_widenings(absent, present) == (
        "contract.declarations changed in a way this comparison does not enumerate",
    )


def test_only_a_raised_scalar_widens_the_measurement_budget() -> None:
    def scalar(value: int) -> tuple[MeasurementBudget, ...]:
        return (MeasurementBudget("cycle_edges", value),)

    assert measurement_budget_widenings(scalar(2), scalar(3)) == (
        "measurement budget widened: cycle_edges (3 now, 2 before)",
    )
    assert measurement_budget_widenings(scalar(2), scalar(2)) == ()
    assert measurement_budget_widenings(scalar(2), scalar(1)) == ()
    assert measurement_budget_widenings((), scalar(2), {"cycle_edges": 2}) == ()
    assert measurement_budget_widenings((), scalar(3), {"cycle_edges": 2}) == (
        "measurement budget widened: cycle_edges (3 accepted, target 2 before)",
    )
