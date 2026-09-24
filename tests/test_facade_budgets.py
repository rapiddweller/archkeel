# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-99: facade and coupling budgets: a contract target and a baseline ratchet on names."""

import json
from pathlib import Path

import pytest
from test_architecture_demo import CONFIG, _prepare_repo

from archkeel.analyzer import observe
from archkeel.check.validation import run_validate
from archkeel.ir.codec import (
    baseline_bytes,
    contract_bytes,
    decode_json,
    parse_contract,
    parse_validation_baseline,
)
from archkeel.ir.measurements import MeasurementBudget
from archkeel.ir.model import Diagnostic, InterfaceBudgetResult, RunResult
from archkeel.ir.widening import contract_widenings, measurement_budget_widenings
from archkeel.render.summary import report_summary
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


def test_budgets_at_their_measured_values_pass(tmp_path: Path) -> None:
    assert _validate(tmp_path, (("model", 5),), (("app", "model", 3), ("app", "store", 3))) == ()


def test_a_facade_over_its_target_names_every_export_without_a_baseline(tmp_path: Path) -> None:
    result = _run(tmp_path, (("model", 4),))

    assert result.diagnostics == (
        Diagnostic(
            "contract_invalid",
            "model",
            f"The model facade counts 5 names, 1 over max_names 4: {', '.join(_MODEL)}.",
            _EXCEEDED_REMEDY,
            "/declarations/facade_budgets/0",
            "budget.exceeded",
        ),
    )
    assert result.interface_budgets == (
        InterfaceBudgetResult("facade_names", "model", 4, 5, 1, _MODEL, (), None, None),
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


def test_a_baseline_holds_a_known_gap_below_the_target(tmp_path: Path) -> None:
    """Target-first: the contract states 4 and 2, the baseline freezes today's 5 and 3."""
    contract = contract_interface_budgets((("model", 4),), (("app", "model", 2),))
    root = _prepare_repo(tmp_path, {"architecture-contract.json": contract})
    baseline = root / "architecture-baseline.json"

    written, files = run_validate(root, CONFIG, observe, baseline=baseline, write_baseline=True)
    baseline.write_bytes(files[str(baseline)])
    held = run_validate(root, CONFIG, observe, baseline=baseline)[0]

    assert (written.exit_code, written.diagnostics) == (0, ())
    assert parse_validation_baseline(decode_json(baseline.read_bytes())).budgets == (
        MeasurementBudget("coupling_names", 3, "app -> model", _APP_MODEL),
        _model_accepted(*_MODEL),
    )
    assert (held.exit_code, held.diagnostics, held.failures) == (0, (), ())
    assert held.interface_budgets == (
        InterfaceBudgetResult("facade_names", "model", 4, 5, 1, _MODEL, (), (), ()),
        InterfaceBudgetResult("coupling_names", "app -> model", 2, 3, 1, _APP_MODEL, (), (), ()),
    )
    assert report_summary(held).sentence.endswith(
        "Budgets not at their target: model 1 over, app -> model 1 over."
    )


def test_a_new_name_is_a_rise_that_names_it(tmp_path: Path) -> None:
    root = _prepare_repo(
        tmp_path,
        {
            "architecture-contract.json": contract_interface_budgets((("model", 9),)),
            "shop/model/entities.py": entities_with("Discount"),
        },
    )
    baseline = _accepted(root, _model_accepted(*_MODEL))

    risen, refused = run_validate(root, CONFIG, observe, baseline=baseline, write_baseline=True)
    accepted, files = run_validate(
        root, CONFIG, observe, baseline=baseline, write_baseline=True, accept_new=True
    )

    assert risen.exit_code == 1
    assert risen.failures == (
        "measurement budget exceeded in facade_names model: new shop.model.entities:Discount",
    )
    assert risen.interface_budgets is not None
    assert risen.interface_budgets[0].new_names == ("shop.model.entities:Discount",)
    assert refused == {}
    assert accepted.exit_code == 0
    assert parse_validation_baseline(decode_json(files[str(baseline)])).budgets == (
        _model_accepted(*_MODEL, "shop.model.entities:Discount"),
    )


def test_a_removed_name_fails_until_the_baseline_records_it(tmp_path: Path) -> None:
    """Freed room is not silently reusable: the fall must be written back, as AD-89 requires."""
    root = _prepare_repo(
        tmp_path, {"architecture-contract.json": contract_interface_budgets((("model", 9),))}
    )
    baseline = _accepted(root, _model_accepted(*_MODEL, "shop.model.entities:Gone"))

    stale = run_validate(root, CONFIG, observe, baseline=baseline)[0]
    updated, files = run_validate(root, CONFIG, observe, baseline=baseline, write_baseline=True)

    assert stale.exit_code == 1
    assert stale.failures == (
        "measurement budget reduced in facade_names model: removed shop.model.entities:Gone; "
        "rewrite the baseline with --write-baseline",
    )
    assert updated.exit_code == 0
    assert parse_validation_baseline(decode_json(files[str(baseline)])).budgets == (
        _model_accepted(*_MODEL),
    )


def test_a_budget_the_baseline_does_not_hold_is_invalid(tmp_path: Path) -> None:
    root = _prepare_repo(
        tmp_path, {"architecture-contract.json": contract_interface_budgets((("model", 5),))}
    )
    baseline = _accepted(root)

    result = run_validate(root, CONFIG, observe, baseline=baseline)[0]

    assert result.exit_code == 2
    assert [item.code for item in result.diagnostics] == ["baseline.invalid"]


def test_a_facade_without_literal_all_is_unknown_with_or_without_a_baseline(
    tmp_path: Path,
) -> None:
    unknown = Diagnostic(
        "contract_invalid",
        "render",
        "The render facade counts at least 1 name against max_names 1; not enumerated: "
        "shop.render.text.",
        _UNKNOWN_REMEDY,
        "/declarations/facade_budgets/0",
        "budget.unknown",
    )
    root = _prepare_repo(
        tmp_path, {"architecture-contract.json": contract_interface_budgets((("render", 1),))}
    )
    baseline = root / "architecture-baseline.json"

    assert run_validate(root, CONFIG, observe)[0].diagnostics == (unknown,)
    held, files = run_validate(root, CONFIG, observe, baseline=baseline, write_baseline=True)
    assert (held.exit_code, held.diagnostics, files) == (2, (unknown,), {})


_STARRED_ALL = (
    entities_with("Discount")
    .replace('"LinePayload", "Discount"]', '"LinePayload", *_EXTRA]')
    .replace("__all__ = [", '_EXTRA = ["Discount"]\n__all__ = [')
)


@pytest.mark.parametrize(
    ("entities", "counted"),
    [
        (entities_with("Discount", '__all__ += ["Discount"]'), 5),
        (entities_with("Discount", '__all__.append("Discount")'), 5),
        (entities_with("Discount", '__all__.extend(["Discount"])'), 5),
        (entities_with("Discount", '__all__ = [*__all__, "Discount"]'), 6),
        (_STARRED_ALL, 5),
    ],
    ids=["augmented", "append", "extend", "reassigned", "starred"],
)
def test_an_all_that_is_not_one_literal_is_unknown_not_pass(
    tmp_path: Path, entities: str, counted: int
) -> None:
    """QA #1: the literal part lists five names; the sixth, Discount, is added another way."""
    diagnostics = _validate(tmp_path, (("model", 6),), files={"shop/model/entities.py": entities})

    assert [(item.code, item.unknown_claim) for item in diagnostics] == [
        (
            "budget.unknown",
            f"The model facade counts at least {counted} names against max_names 6; not "
            "enumerated: shop.model.entities.",
        )
    ]


def test_an_empty_literal_all_is_an_enumerated_facade_of_no_names(tmp_path: Path) -> None:
    text = (FIXTURE_DIR / "shop/render/text.py").read_text()
    files: dict[str, str | None] = {
        "shop/render/text.py": text.replace(
            "from shop.model.entities import Order\n",
            "from shop.model.entities import Order\n\n__all__: list[str] = []\n",
        )
    }

    result = _run(tmp_path, (("render", 0),), files=files)

    assert (result.exit_code, result.diagnostics) == (0, ())
    assert result.interface_budgets == (
        InterfaceBudgetResult("facade_names", "render", 0, 0, 0, (), (), None, None),
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
            f"The app -> model pair counts at least 3 names, 1 over max_names 2: "
            f"{', '.join(_APP_MODEL)}.",
        )
    ]


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
