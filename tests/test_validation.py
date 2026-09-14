# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
from pathlib import Path
from unittest.mock import Mock

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.validation import reference_diagnostics, run_validate
from archkeel.cli.config import load_config
from archkeel.ir.codec import decode_canonical_model, parse_contract, parse_observation

ROOT = Path(__file__).parents[1]
CONFIG = ScanConfig(("sample",), "sample", "contract.json", "0" * 64)


def test_validate_accepts_archkeel_self_contract() -> None:
    result = run_validate(ROOT, load_config(ROOT), observe)
    assert result.exit_code == 0
    assert result.observation_complete == result.declared_rules == "PASS"
    assert result.expectation_fulfilled == "n/a"


def test_validate_rejects_contract_1_1_with_exact_pointer(tmp_path: Path) -> None:
    (tmp_path / "contract.json").write_text('{"schema_version":"1.1.0","components":[],"rules":[]}')
    analyzer = Mock()
    result = run_validate(tmp_path, CONFIG, analyzer)
    analyzer.assert_not_called()
    assert result.exit_code == 2
    assert result.diagnostics[0].pointer == "/schema_version"
    assert result.diagnostics[0].unknown_claim == (
        "Contract schema 1.1.0 cannot be validated as 2.0.0."
    )


def test_validate_sorts_namespace_and_provenance_diagnostics(tmp_path: Path) -> None:
    contract = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    contract["components"][0]["packages"] = ["outside.x"]
    contract["components"][0]["provenance"] = ["missing.md"]
    contract["components"] = contract["components"][:1]
    contract["rules"] = []
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    result = run_validate(tmp_path, CONFIG, Mock())
    assert [item.pointer for item in result.diagnostics] == [
        "/components/0/packages/0",
        "/components/0/provenance/0",
    ]


def test_reference_check_rejects_a_component_without_scanned_modules() -> None:
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    contract = parse_contract(raw)
    observation = parse_observation(
        decode_canonical_model(
            json.loads((ROOT / "fixtures/D-self/architecture.json").read_bytes())
        )
    )
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract, observation)
    assert any(item.pointer == "/components/0/packages/0" for item in diagnostics)
