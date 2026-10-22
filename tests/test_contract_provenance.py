# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#629/#630: provenance and rationale checks cover every contract location and mount."""

import json
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.check.ports import ScanConfig
from archkeel.check.validation import run_validate
from archkeel.check.validation.references import reference_diagnostics
from archkeel.cli.observe import observe
from archkeel.ir.codec import (
    contract_provenance_locations,
    contract_provenance_paths,
    parse_contract,
)

UML_FIXTURE = Path(__file__).parents[1] / "fixtures/H-uml"
UML_CONFIG = ScanConfig(("demo",), "demo", "architecture-contract.json", "0" * 64)
REVIEW_FIXTURE = Path(__file__).parents[1] / "fixtures/M-review-workflow"
REVIEW_CONFIG = ScanConfig(("orders",), "orders", "architecture-contract.json", "0" * 64)


def _missing(document: dict, location: str) -> None:
    declarations = document["declarations"]
    if location == "measurement_budgets":
        declarations["measurement_budgets"] = [
            {"name": "cycle_edges", "provenance": ["docs/missing.md"]}
        ]
    else:
        declarations["uml"][location][0]["provenance"] = ["docs/missing.md"]


@pytest.mark.parametrize(
    ("location", "pointer"),
    [
        ("entities", "/declarations/uml/entities/0/provenance/0"),
        ("relationships", "/declarations/uml/relationships/0/provenance/0"),
    ],
)
def test_a_missing_uml_provenance_file_names_its_location(
    tmp_path: Path, location: str, pointer: str
) -> None:
    document = json.loads((UML_FIXTURE / "architecture-contract.json").read_text())
    _missing(document, location)
    root = _prepare_repo(
        tmp_path, {"architecture-contract.json": json.dumps(document)}, fixture=UML_FIXTURE
    )

    result, _ = run_validate(root, UML_CONFIG, observe)

    missing = [
        (item.code, item.pointer)
        for item in result.diagnostics
        if item.subject == "docs/missing.md"
    ]
    assert missing == [("reference.provenance", pointer)]


def test_a_missing_measurement_budget_provenance_file_names_its_location() -> None:
    # A budget needs --baseline before a full run reaches references, so check them directly.
    document = json.loads((UML_FIXTURE / "architecture-contract.json").read_text())
    _missing(document, "measurement_budgets")

    diagnostics = reference_diagnostics(UML_FIXTURE, UML_CONFIG, parse_contract(document))

    assert [
        (item.code, item.pointer) for item in diagnostics if item.subject == "docs/missing.md"
    ] == [("reference.provenance", "/declarations/measurement_budgets/0/provenance/0")]


def test_provenance_paths_are_the_locations_paths() -> None:
    contract = parse_contract(json.loads((UML_FIXTURE / "architecture-contract.json").read_text()))
    assert contract_provenance_paths(contract) == tuple(
        sorted({path for _, paths in contract_provenance_locations(contract) for path in paths})
    )


@pytest.mark.parametrize("contract_file", ["architecture-contract.json", "contracts/checkout.json"])
def test_a_placeholder_rationale_fails_in_root_and_mounted_contracts(
    tmp_path: Path, contract_file: str
) -> None:
    # #630: a mounted contract is decided the way the top level is.
    document = json.loads((REVIEW_FIXTURE / contract_file).read_text())
    document["rules"][0]["rationale"] = "TODO: explain."
    root = _prepare_repo(tmp_path, {contract_file: json.dumps(document)}, fixture=REVIEW_FIXTURE)

    result, _ = run_validate(root, REVIEW_CONFIG, observe)

    assert [item.code for item in result.diagnostics] == ["rationale.placeholder"]
