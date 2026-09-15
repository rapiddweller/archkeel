# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
from pathlib import Path
from unittest.mock import Mock

from test_analyzer import _component
from test_delta import _model, _record

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.validation import interface_diagnostics, reference_diagnostics, run_validate
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
        "Contract schema 1.1.0 cannot be validated as 2.1.0."
    )


def test_validate_gives_every_contract_invalid_diagnostic_a_code(tmp_path: Path) -> None:
    broken = (ROOT / "tests/contracts/invalid/wrong-type.json").read_bytes()
    (tmp_path / "contract.json").write_bytes(broken)
    result = run_validate(tmp_path, CONFIG, Mock())
    assert result.diagnostics
    assert all(item.code == "contract.invalid" for item in result.diagnostics)


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


def test_public_entry_outside_namespace_is_a_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", public=["other.module"])],
            "rules": [],
        }
    )
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract)
    assert any(
        item.pointer == "/components/0/public/0" and "outside namespace" in item.unknown_claim
        for item in diagnostics
    )


def test_public_entry_owned_by_another_component_is_a_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", public=["sample.cli"]),
                _component("cli"),
            ],
            "rules": [],
        }
    )
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract)
    assert any(
        item.pointer == "/components/0/public/0"
        and "not owned by this component" in item.unknown_claim
        for item in diagnostics
    )


def test_public_entry_with_underscore_name_is_a_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", public=["sample.core:_Hidden"])],
            "rules": [],
        }
    )
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract)
    assert any(
        item.pointer == "/components/0/public/0" and "Underscore" in item.unknown_claim
        for item in diagnostics
    )


_INTERFACE_RULE = {
    "id": "INTERFACE",
    "kind": "interface_boundary",
    "rationale": "Probe.",
    "provenance": ["docs/architecture/sample.md"],
}


def _cross_import(target_module: str, **data: object) -> dict[str, object]:
    return _record(
        "IMPORT-1",
        kind="import",
        data={"source_module": "sample.cli", "target_module": target_module, **data},
    )


def test_undeclared_interface_is_a_diagnostic_when_a_rule_is_present() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core"), _component("cli")],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(
        _model(git_head="a" * 40, imports=[_cross_import("sample.core")])
    )
    diagnostics = interface_diagnostics(contract, observation)
    assert [item.pointer for item in diagnostics] == ["/components/0"]


def test_declared_public_interface_has_no_undeclared_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", public=["sample.core"]), _component("cli")],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(
        _model(git_head="a" * 40, imports=[_cross_import("sample.core")])
    )
    assert interface_diagnostics(contract, observation) == ()


def test_unused_public_entry_is_a_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", public=["sample.core:Widget"]), _component("cli")],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(_model(git_head="a" * 40, imports=[]))
    diagnostics = interface_diagnostics(contract, observation)
    assert [item.pointer for item in diagnostics] == ["/components/0/public/0"]


def test_public_entry_used_through_a_reexport_chain_has_no_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", public=["sample.core.impl:Widget"]),
                _component("cli"),
            ],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(
        _model(
            git_head="a" * 40,
            imports=[
                _cross_import(
                    "sample.core",
                    reexport_chain=["sample.core.Widget", "sample.core.impl.Widget"],
                )
            ],
        )
    )
    assert interface_diagnostics(contract, observation) == ()


def test_no_interface_rule_means_neither_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core"), _component("cli")],
            "rules": [],
        }
    )
    observation = parse_observation(
        _model(git_head="a" * 40, imports=[_cross_import("sample.core")])
    )
    assert interface_diagnostics(contract, observation) == ()
