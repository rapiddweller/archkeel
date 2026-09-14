# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Verify the typed Contract 2.0 structure parser."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from archkeel.ir.codec import contract_bytes, parse_contract

ROOT = Path(__file__).parents[1]
SCHEMA = json.loads((ROOT / "schema/architecture-contract.schema.json").read_bytes())
VALIDATOR = Draft202012Validator(SCHEMA)


@pytest.mark.parametrize("path", sorted((ROOT / "tests/contracts").glob("*/*.json")))
def test_contract_parser_matches_structure_corpus(path: Path) -> None:
    raw = json.loads(path.read_bytes())
    should_pass = path.parent.name == "valid"
    try:
        parse_contract(raw)
        parser_accepts = True
    except ValueError:
        parser_accepts = False
    schema_accepts = not list(VALIDATOR.iter_errors(raw))
    assert parser_accepts == schema_accepts == should_pass


@pytest.mark.parametrize(
    "path",
    [*sorted((ROOT / "tests/contracts/valid").glob("*.json")), ROOT / "architecture-contract.json"],
)
def test_contract_encoding_round_trips_and_matches_the_schema(path: Path) -> None:
    contract = parse_contract(json.loads(path.read_bytes()))
    encoded = json.loads(contract_bytes(contract))
    assert not list(VALIDATOR.iter_errors(encoded))
    assert parse_contract(encoded) == contract


def test_contract_schema_is_draft_2020_12() -> None:
    Draft202012Validator.check_schema(SCHEMA)


def test_contract_parser_rejects_distinct_records_with_duplicate_ids() -> None:
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    raw["rules"][0]["id"] = raw["components"][0]["id"]
    with pytest.raises(ValueError, match="duplicate contract ID"):
        parse_contract(raw)
