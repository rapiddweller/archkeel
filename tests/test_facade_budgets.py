# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-99: facade and coupling budgets: a contract target and a baseline ratchet on names."""

import json
from pathlib import Path

import pytest
from test_architecture_demo import CONFIG, _prepare_repo

from archkeel.check.validation import run_validate
from archkeel.cli.observe import observe
from archkeel.ir.codec import (
    baseline_bytes,
    contract_bytes,
    parse_contract,
    parse_validation_baseline,
)
from archkeel.ir.measurements import MeasurementBudget
from archkeel.ir.model import Diagnostic, RunResult
from archkeel.ir.widening import contract_widenings, measurement_budget_widenings
from fixtures.demo_catalog_support import (
    FIXTURE_DIR,
    HEADER,
    contract_interface_budgets,
    entities_with,
)

_MODEL = tuple(
    f"shop.model.entities:{name}"
    for name in ("Line", "LinePayload", "Money", "Order", "OrderPayload")
)
_APP_MODEL = ("shop.model.entities:Line", "shop.model.entities:Money", "shop.model.entities:Order")
_EXCEEDED_REMEDY = "Remove names until max_names holds; raising max_names widens the contract."
_UNKNOWN_REMEDY = (
    "Give the facade a literal __all__ or module:Name entries, and import the used names "
    "explicitly."
)
# A whole-module import proves no name: `entities.Money` is used, the import says nothing.
_WHOLE_MODULE_IMPORT = HEADER + (
    '"""Report use case reading the model through its module."""\n\n'
    "from __future__ import annotations\n\n"
    "import shop.model.entities\n\n\n"
    "def zero() -> shop.model.entities.Money:\n"
    "    return shop.model.entities.Money(0)\n"
)


def _run(
    tmp_path: Path,
    facades: tuple[tuple[str, int], ...] = (),
    pairs: tuple[tuple[str, str, int], ...] = (),
    files: dict[str, str | None] | None = None,
) -> RunResult:
    overlay = {
        "architecture-contract.json": contract_interface_budgets(facades, pairs),
        **(files or {}),
    }
    return run_validate(_prepare_repo(tmp_path, overlay), CONFIG, observe)[0]


def _validate(
    tmp_path: Path,
    facades: tuple[tuple[str, int], ...] = (),
    pairs: tuple[tuple[str, str, int], ...] = (),
    files: dict[str, str | None] | None = None,
) -> tuple[Diagnostic, ...]:
    result = _run(tmp_path, facades, pairs, files)
    assert result.exit_code == (2 if result.diagnostics else 0)
    return result.diagnostics


def _accepted(root: Path, *budgets: MeasurementBudget) -> Path:
    path = root / "architecture-baseline.json"
    path.write_bytes(baseline_bytes((), budgets))
    return path


def _model_accepted(*names: str) -> MeasurementBudget:
    return MeasurementBudget("facade_names", len(names), "model", tuple(sorted(names)))


def test_a_budget_the_baseline_does_not_hold_is_invalid(tmp_path: Path) -> None:
    root = _prepare_repo(
        tmp_path, {"architecture-contract.json": contract_interface_budgets((("model", 5),))}
    )
    baseline = _accepted(root)

    result = run_validate(root, CONFIG, observe, baseline=baseline)[0]

    assert result.exit_code == 2
    assert [item.code for item in result.diagnostics] == ["baseline.invalid"]


_STARRED_ALL = (
    entities_with("Discount")
    .replace('"LinePayload", "Discount"]', '"LinePayload", *_EXTRA]')
    .replace("__all__ = [", '_EXTRA = ["Discount"]\n__all__ = [')
)


def _without_interface_boundary() -> dict[str, object]:
    contract = json.loads(contract_interface_budgets(pairs=(("app", "model", 3),)))
    contract["rules"] = [rule for rule in contract["rules"] if rule["kind"] != "interface_boundary"]
    return contract


def _type_checking_excluded() -> dict[str, object]:
    contract = json.loads(contract_interface_budgets(pairs=(("app", "model", 3),)))
    for rule in contract["rules"]:
        if rule["kind"] == "interface_boundary":
            rule["include_type_checking"] = False
    return contract


@pytest.mark.parametrize(
    ("contract", "message"),
    [
        (
            json.loads(contract_interface_budgets((("orders", 1),))),
            "facade_budgets[0].component names no component: 'orders'",
        ),
        (
            json.loads(contract_interface_budgets((("cli", 1),))),
            "facade_budgets[0].component 'cli' declares no public facade",
        ),
        (
            json.loads(contract_interface_budgets(pairs=(("web", "model", 1),))),
            "coupling_budgets[0].source names no component: 'web'",
        ),
        (
            json.loads(contract_interface_budgets(pairs=(("app", "cli", 1),))),
            "coupling_budgets[0].target 'cli' declares no public facade",
        ),
        (
            json.loads(contract_interface_budgets(pairs=(("app", "app", 1),))),
            "coupling_budgets[0] names one component twice",
        ),
        (
            json.loads(contract_interface_budgets((("model", 1), ("model", 2)))),
            "facade_budgets repeats 'model'",
        ),
        (
            json.loads(
                contract_interface_budgets(pairs=(("app", "model", 1), ("app", "model", 2)))
            ),
            "coupling_budgets repeats 'app -> model'",
        ),
        (
            json.loads(contract_interface_budgets((("model", -1),))),
            "facade_budgets[0].max_names must be a non-negative integer",
        ),
        (
            _without_interface_boundary(),
            "coupling_budgets need an interface_boundary rule that includes TYPE_CHECKING",
        ),
        (
            _type_checking_excluded(),
            "coupling_budgets need an interface_boundary rule that includes TYPE_CHECKING",
        ),
    ],
)
def test_a_budget_must_name_a_facade_something_holds(
    contract: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message.replace("[", r"\[").replace("]", r"\]")):
        parse_contract(contract)


def test_an_unknown_key_is_contract_invalid_not_a_pass(tmp_path: Path) -> None:
    assert [item.code for item in _validate(tmp_path, (("orders", 9),))] == ["contract.invalid"]


def test_a_budget_cites_an_existing_provenance_file(tmp_path: Path) -> None:
    contract = json.loads(contract_interface_budgets(pairs=(("app", "model", 3),)))
    contract["declarations"]["coupling_budgets"][0]["provenance"] = ["docs/missing.md"]
    root = _prepare_repo(tmp_path, {"architecture-contract.json": json.dumps(contract)})

    result, _ = run_validate(root, CONFIG, observe)

    assert [(item.code, item.pointer) for item in result.diagnostics] == [
        ("reference.provenance", "/declarations/coupling_budgets/0/provenance/0")
    ]


def test_raising_or_removing_a_target_widens_and_the_reverse_narrows() -> None:
    def contract(facade: int | None, pair: int | None) -> str:
        return contract_interface_budgets(
            (("model", facade),) if facade is not None else (),
            (("app", "model", pair),) if pair is not None else (),
        )

    before = parse_contract(json.loads(contract(5, 3)))

    assert contract_widenings(before, parse_contract(json.loads(contract(6, 4)))) == (
        "coupling budget app -> model raised from 3 to 4",
        "facade budget model raised from 5 to 6",
    )
    assert contract_widenings(before, parse_contract(json.loads(contract(None, None)))) == (
        "coupling budget app -> model removed",
        "facade budget model removed",
    )
    assert contract_widenings(before, parse_contract(json.loads(contract(4, 2)))) == ()
    assert contract_widenings(parse_contract(json.loads(contract(None, None))), before) == ()


def test_a_first_accepted_set_over_the_old_target_widens() -> None:
    """Round 2: a budget the old baseline did not hold was held by its old target alone."""
    after = (MeasurementBudget("facade_names", 6, "model", tuple(f"m:{n}" for n in "ABCDEF")),)
    targets = {"facade_names model": 5}

    assert measurement_budget_widenings((), after, targets) == (
        "measurement budget widened: facade_names model (6 accepted, target 5 before)",
    )
    assert measurement_budget_widenings((), after, {"facade_names model": 6}) == ()
    assert measurement_budget_widenings((), after) == ()


def test_a_grown_accepted_name_set_widens_the_baseline() -> None:
    before = (MeasurementBudget("facade_names", 2, "model", ("m:A", "m:B")),)

    assert measurement_budget_widenings(
        before, (MeasurementBudget("facade_names", 2, "model", ("m:A", "m:C")),)
    ) == ("measurement budget widened: facade_names model (gained m:C)",)
    assert (
        measurement_budget_widenings(
            before, (MeasurementBudget("facade_names", 1, "model", ("m:A",)),)
        )
        == ()
    )
    assert measurement_budget_widenings(before, ()) == (
        "measurement budget baseline lost facade_names model",
    )


def test_the_baseline_writes_accepted_names_and_still_reads_schema_1_2() -> None:
    budgets = (
        MeasurementBudget("coupling_names", 1, "app -> model", ("m:A",)),
        MeasurementBudget("cycle_edges", 0),
    )
    written = json.loads(baseline_bytes((), budgets))
    legacy = {"schema_version": "1.2.0", "budgets": {"cycle_edges": 0}, "violations": []}

    assert written["schema_version"] == "1.3.0"
    assert written["budgets"] == {"coupling_names": {"app -> model": ["m:A"]}, "cycle_edges": 0}
    assert parse_validation_baseline(written).budgets == budgets
    assert parse_validation_baseline(legacy).budgets == (MeasurementBudget("cycle_edges", 0),)
    with pytest.raises(ValueError, match="not a supported measurement budget"):
        parse_validation_baseline({**legacy, "budgets": written["budgets"]})


def test_a_contract_without_budgets_keeps_its_canonical_bytes() -> None:
    """F: absent lists stay absent, so no existing contract digest or amendment moves."""
    clean = parse_contract(json.loads((FIXTURE_DIR / "architecture-contract.json").read_text()))
    declared = json.loads(contract_bytes(clean))["declarations"]

    assert "facade_budgets" not in declared
    assert "coupling_budgets" not in declared
