# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-99: facade and coupling budgets are contract ceilings on AD-88's one measurement."""

import json
from pathlib import Path

import pytest
from test_architecture_demo import CONFIG, _prepare_repo

from archkeel.analyzer import observe
from archkeel.check.validation import run_validate
from archkeel.ir.codec import parse_contract
from archkeel.ir.model import Diagnostic
from archkeel.ir.widening import contract_widenings
from fixtures.demo_catalog_support import FIXTURE_DIR, HEADER, contract_interface_budgets

_ENTITIES = (
    "shop.model.entities:Line, shop.model.entities:LinePayload, shop.model.entities:Money, "
    "shop.model.entities:Order, shop.model.entities:OrderPayload"
)
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


def _validate(
    tmp_path: Path,
    facades: tuple[tuple[str, int], ...] = (),
    pairs: tuple[tuple[str, str, int], ...] = (),
    files: dict[str, str | None] | None = None,
) -> tuple[Diagnostic, ...]:
    overlay = {
        "architecture-contract.json": contract_interface_budgets(facades, pairs),
        **(files or {}),
    }
    result, _ = run_validate(_prepare_repo(tmp_path, overlay), CONFIG, observe)
    assert result.exit_code == (2 if result.diagnostics else 0)
    return result.diagnostics


def test_budgets_at_their_measured_values_pass(tmp_path: Path) -> None:
    assert _validate(tmp_path, (("model", 5),), (("app", "model", 3), ("app", "store", 3))) == ()


def test_a_facade_over_budget_names_every_export(tmp_path: Path) -> None:
    assert _validate(tmp_path, (("model", 4),)) == (
        Diagnostic(
            "contract_invalid",
            "model",
            f"The model facade counts 5 names, 1 over max_names 4: {_ENTITIES}.",
            _EXCEEDED_REMEDY,
            "/declarations/facade_budgets/0",
            "budget.exceeded",
        ),
    )


def test_a_pair_counts_the_facade_name_a_reexport_reaches(tmp_path: Path) -> None:
    """`from shop.store import OrderRepository` reaches the declared repository entry."""
    assert _validate(tmp_path, pairs=(("app", "store", 2),)) == (
        Diagnostic(
            "contract_invalid",
            "app -> store",
            "The app -> store pair counts 3 names, 1 over max_names 2: "
            "shop.store.repository:OrderRepository, shop.store.sqlite:Connection, "
            "shop.store.sqlite:vacuum.",
            _EXCEEDED_REMEDY,
            "/declarations/coupling_budgets/0",
            "budget.exceeded",
        ),
    )


def test_a_baseline_cannot_hide_an_exceeded_budget(tmp_path: Path) -> None:
    root = _prepare_repo(
        tmp_path, {"architecture-contract.json": contract_interface_budgets((("model", 4),))}
    )
    baseline = root / "known-violations.json"

    result, files = run_validate(root, CONFIG, observe, baseline=baseline, write_baseline=True)

    assert result.exit_code == 2
    assert [item.code for item in result.diagnostics] == ["budget.exceeded"]
    assert files == {}


def test_a_facade_without_literal_all_is_unknown_not_pass(tmp_path: Path) -> None:
    assert _validate(tmp_path, (("render", 1),)) == (
        Diagnostic(
            "contract_invalid",
            "render",
            "The render facade counts at least 1 name against max_names 1; not enumerated: "
            "shop.render.text.",
            _UNKNOWN_REMEDY,
            "/declarations/facade_budgets/0",
            "budget.unknown",
        ),
    )


def test_a_whole_module_import_makes_a_pair_unknown_until_it_is_over(tmp_path: Path) -> None:
    files: dict[str, str | None] = {"shop/app/report.py": _WHOLE_MODULE_IMPORT}

    assert _validate(tmp_path / "at", pairs=(("app", "model", 3),), files=files) == (
        Diagnostic(
            "contract_invalid",
            "app -> model",
            "The app -> model pair counts at least 3 names against max_names 3; not "
            "enumerated: shop.model.entities.",
            _UNKNOWN_REMEDY,
            "/declarations/coupling_budgets/0",
            "budget.unknown",
        ),
    )
    over = _validate(tmp_path / "over", pairs=(("app", "model", 2),), files=files)
    assert [(item.code, item.unknown_claim) for item in over] == [
        (
            "budget.exceeded",
            "The app -> model pair counts at least 3 names, 1 over max_names 2: "
            "shop.model.entities:Line, shop.model.entities:Money, shop.model.entities:Order.",
        )
    ]


@pytest.mark.parametrize(
    ("facades", "pairs", "message"),
    [
        ((("orders", 1),), (), "facade_budgets[0].component names no component: 'orders'"),
        ((("cli", 1),), (), "facade_budgets[0].component 'cli' declares no public facade"),
        ((), (("web", "model", 1),), "coupling_budgets[0].source names no component: 'web'"),
        ((), (("app", "cli", 1),), "coupling_budgets[0].target 'cli' declares no public facade"),
        ((), (("app", "app", 1),), "coupling_budgets[0] names one component twice"),
        ((("model", 1), ("model", 2)), (), "facade_budgets repeats 'model'"),
        ((), (("app", "model", 1), ("app", "model", 2)), "coupling_budgets repeats 'app -> model'"),
        ((("model", -1),), (), "facade_budgets[0].max_names must be a non-negative integer"),
    ],
)
def test_a_budget_must_name_a_declared_facade(
    facades: tuple[tuple[str, int], ...], pairs: tuple[tuple[str, str, int], ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message.replace("[", r"\[").replace("]", r"\]")):
        parse_contract(json.loads(contract_interface_budgets(facades, pairs)))


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


def test_raising_or_removing_a_ceiling_widens_and_the_reverse_narrows() -> None:
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


def test_an_inside_contract_cannot_hold_a_budget_nobody_measures(tmp_path: Path) -> None:
    inside = json.loads((FIXTURE_DIR / "shop/store/architecture-contract.json").read_text())
    inside["declarations"] = {
        "facade_budgets": [
            {"component": "api", "max_names": 9, "provenance": ["docs/architecture/shop.md"]}
        ]
    }
    diagnostics = _validate(
        tmp_path, files={"shop/store/architecture-contract.json": json.dumps(inside, indent=2)}
    )

    assert [(item.code, item.pointer) for item in diagnostics] == [
        ("contract.invalid", "/components/1/inside")
    ]
