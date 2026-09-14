# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Verify the typed Contract 2.0 structure parser."""

import json
from pathlib import Path

import pytest

from archkeel.ir.codec import parse_contract

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize("path", sorted((ROOT / "tests/contracts").glob("*/*.json")))
def test_contract_parser_matches_structure_corpus(path: Path) -> None:
    raw = json.loads(path.read_bytes())
    should_pass = path.parent.name == "valid"
    if should_pass:
        parse_contract(raw)
    else:
        with pytest.raises(ValueError):
            parse_contract(raw)


def test_contract_parser_rejects_distinct_records_with_duplicate_ids() -> None:
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    raw["rules"][0]["id"] = raw["components"][0]["id"]
    with pytest.raises(ValueError, match="duplicate contract ID"):
        parse_contract(raw)
