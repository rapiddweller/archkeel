# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-89: contract-selected measurements share the validation baseline ratchet."""

import json
import subprocess
from pathlib import Path

from test_architecture_demo import CONFIG, _prepare_repo

from archkeel.analyzer import observe
from archkeel.check.validation import run_validate
from archkeel.ir.codec import (
    baseline_bytes,
    decode_json,
    parse_contract,
    parse_validation_baseline,
)
from archkeel.ir.measurements import MeasurementBudget
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


def test_cycle_edge_budget_passes_then_blocks_a_rise(tmp_path: Path) -> None:
    root = _repo(tmp_path, "cycle_edges")
    baseline = _baseline(root, MeasurementBudget("cycle_edges", 0))

    assert run_validate(root, CONFIG, observe, baseline=baseline)[0].exit_code == 0

    (root / "shop/model/alpha.py").write_text("from shop.model import beta\nVALUE = beta.VALUE\n")
    (root / "shop/model/beta.py").write_text("from shop.model import alpha\nVALUE = 1\n")
    result, files = run_validate(root, CONFIG, observe, baseline=baseline, write_baseline=True)

    assert result.exit_code == 1
    assert result.failures == ("measurement budget exceeded in cycle_edges: 0->2",)
    assert files == {}

    accepted, files = run_validate(
        root,
        CONFIG,
        observe,
        baseline=baseline,
        write_baseline=True,
        accept_new=True,
    )
    assert accepted.exit_code == 0
    written = parse_validation_baseline(decode_json(files[str(baseline)]))
    assert written.budgets == (MeasurementBudget("cycle_edges", 2),)


def test_unknown_position_budget_blocks_a_new_undecided_promise(tmp_path: Path) -> None:
    """AD-92: `check` already failed a new `unknowns` record; `validate --baseline` kept exit 0
    until the count became a budget. A `public_api` name the sample never defines, in a module
    without `__all__`, is one position the scan cannot decide (AD-72). Recursive DTO inspection
    resolves the sample's former `nested_type` limit, leaving the initial unknown count at zero."""
    root = _repo(tmp_path, "unknown_positions")
    baseline = _baseline(root, MeasurementBudget("unknown_positions", 0))

    assert run_validate(root, CONFIG, observe, baseline=baseline)[0].exit_code == 0

    contract_path = root / "architecture-contract.json"
    contract = json.loads(contract_path.read_text())
    contract["declarations"]["public_api"].append("shop.app.orders:TypoThatIsNotReal")
    contract_path.write_text(json.dumps(contract, indent=2) + "\n")
    result, files = run_validate(root, CONFIG, observe, baseline=baseline, write_baseline=True)

    assert result.exit_code == 1
    assert result.failures == ("measurement budget exceeded in unknown_positions: 0->1",)
    assert files == {}

    accepted, files = run_validate(
        root, CONFIG, observe, baseline=baseline, write_baseline=True, accept_new=True
    )
    assert accepted.exit_code == 0
    written = parse_validation_baseline(decode_json(files[str(baseline)]))
    assert written.budgets == (MeasurementBudget("unknown_positions", 1),)


def test_reduced_budget_must_be_written_back(tmp_path: Path) -> None:
    root = _repo(tmp_path, "cycle_edges")
    baseline = _baseline(root, MeasurementBudget("cycle_edges", 2))

    stale, _ = run_validate(root, CONFIG, observe, baseline=baseline)
    updated, files = run_validate(root, CONFIG, observe, baseline=baseline, write_baseline=True)

    assert stale.failures == (
        "measurement budget reduced in cycle_edges: 2->0; rewrite the baseline with "
        "--write-baseline",
    )
    assert updated.exit_code == 0
    written = parse_validation_baseline(decode_json(files[str(baseline)]))
    assert written.budgets == (MeasurementBudget("cycle_edges", 0),)


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


def test_against_rejects_a_raised_budget(tmp_path: Path) -> None:
    root = _repo(tmp_path, "cycle_edges")
    baseline = _baseline(root, MeasurementBudget("cycle_edges", 0))
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "add", "architecture-baseline.json"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "budget"],
        cwd=root,
        check=True,
    )
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    baseline.write_bytes(baseline_bytes((), (MeasurementBudget("cycle_edges", 1),)))

    result, _ = run_validate(root, CONFIG, observe, baseline=baseline, against=base)

    assert "measurement budget widened: cycle_edges (1 now, 0 before)" in result.failures


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
