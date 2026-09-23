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


def test_component_namespace_round_trips_and_must_name_an_owned_package() -> None:
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    raw["components"][0]["namespace"] = raw["components"][0]["packages"][0]
    contract = parse_contract(raw)
    assert contract.components[0].namespace == "sample.core"
    assert parse_contract(json.loads(contract_bytes(contract))) == contract

    raw["components"][0]["namespace"] = "sample.other"
    with pytest.raises(ValueError, match="must name one of"):
        parse_contract(raw)

    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    raw["components"].append({**raw["components"][0], "id": "COMP-DUP"})
    raw["components"][0]["namespace"] = "sample.core"
    with pytest.raises(ValueError, match="identify one component package"):
        parse_contract(raw)


@pytest.mark.parametrize("allowed_child", ["sample", "sample.core.nested", "other.core"])
def test_root_layout_requires_each_allowed_child_to_be_immediate(allowed_child: str) -> None:
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    raw["rules"] = [
        {
            "id": "ROOT-LAYOUT",
            "kind": "root_layout",
            "root": "sample",
            "allowed_children": [allowed_child],
            "rationale": "Probe.",
            "provenance": ["docs/architecture/sample.md"],
            "decided_by": "architect",
        }
    ]
    with pytest.raises(ValueError, match="exactly one immediate child"):
        parse_contract(raw)


def test_root_layout_accepts_a_nested_package_root() -> None:
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    raw["rules"] = [
        {
            "id": "ROOT-LAYOUT",
            "kind": "root_layout",
            "root": "sample.core",
            "allowed_children": ["sample.core.models"],
            "rationale": "Probe.",
            "provenance": ["docs/architecture/sample.md"],
            "decided_by": "architect",
        }
    ]
    contract = parse_contract(raw)
    assert contract.rules[0].root == "sample.core"


def test_boundary_type_allowance_is_exact_and_round_trips() -> None:
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    raw["rules"] = [
        {
            "id": "BOUNDARY-TYPES",
            "kind": "boundary_types",
            "source": "sample.core",
            "rationale": "Keep declared boundary types narrow.",
            "provenance": ["docs/architecture/sample.md"],
            "decided_by": "architect",
            "allowed_positions": [
                {
                    "qualified_name": "sample.core.api.run",
                    "position": "return",
                    "field_path": "payload",
                    "annotation": "dict[str, JsonValue]",
                }
            ],
        }
    ]

    contract = parse_contract(raw)
    encoded = json.loads(contract_bytes(contract))
    assert not list(VALIDATOR.iter_errors(encoded))
    assert parse_contract(encoded) == contract

    raw["rules"][0]["allowed_positions"][0]["annotation"] = "dict"
    assert list(VALIDATOR.iter_errors(raw))
    with pytest.raises(ValueError, match="annotation cannot allow bare dict"):
        parse_contract(raw)
    raw["rules"][0]["allowed_positions"][0]["annotation"] = "dict[str, JsonValue]"

    raw["rules"][0]["allowed_positions"][0]["field_path"] = ""
    with pytest.raises(ValueError, match="allowed_positions\\[0\\].field_path must not be empty"):
        parse_contract(raw)

    raw["rules"][0]["allowed_positions"][0]["field_path"] = "payload"
    raw["rules"][0]["allowed_positions"][0]["unexpected"] = True
    with pytest.raises(ValueError, match="fields mismatch"):
        parse_contract(raw)
