# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Canonical Protocol declaration rule behavior (#616)."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_analyzer import _observe
from test_exact_module_ownership import _component, _observe_tree

from archkeel.check.report import run_saved_report
from archkeel.ir.codec import (
    canonical_report_bytes,
    contract_bytes,
    encode_canonical_model,
    observation_payload,
    parse_contract,
    parse_observation,
)
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]


def _contract() -> dict[str, object]:
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_text())
    raw["schema_version"] = "3.9.0"
    raw["rules"] = [
        {
            "id": "APP-READER-DECLARATIONS",
            "kind": "protocol_declarations",
            "source": "sample.core",
            "protocol": "sample.core.Reader",
            "selectors": [
                {
                    "role": "parameter",
                    "name": "client",
                    "visibility": "public",
                    "optional": False,
                },
                {
                    "role": "member",
                    "name": "reader",
                    "visibility": "public",
                    "optional": True,
                },
            ],
            "rationale": "Public consumer declarations use the Reader port.",
            "provenance": ["docs/architecture/sample.md"],
            "decided_by": "architect",
        }
    ]
    return raw


def test_protocol_declaration_rule_has_typed_round_trip() -> None:
    contract = parse_contract(_contract())
    rule = contract.rules[0]
    assert rule.kind.value == "protocol_declarations"
    assert rule.protocol == "sample.core.Reader"
    assert [selector.role for selector in rule.selectors] == ["parameter", "member"]
    assert parse_contract(json.loads(contract_bytes(contract))) == contract


def test_selected_public_positions_require_the_canonical_protocol(tmp_path: Path) -> None:
    raw = _contract()
    raw["rules"][0]["selectors"] = [
        {"role": "parameter", "name": "client", "visibility": "public"},
        {
            "role": "member",
            "name": "reader",
            "visibility": "public",
            "optional": True,
        },
    ]
    (tmp_path / "contract.json").write_text(json.dumps(raw))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(
        "from typing import Any, Protocol\n"
        "class Reader(Protocol):\n    def read(self) -> bytes: ...\n"
        "class Concrete:\n    def read(self) -> bytes: return b''\n"
        "class Fake: pass\n"
        "typing = Fake\n"
        "def good(client: Reader): return client.read()\n"
        "def broad(client: object): return None\n"
        "def any_type(client: Any): return None\n"
        "def shadowed_any(client: typing.Any): return None\n"
        "def concrete(client: Concrete): return client.read()\n"
        "def missing(client): return None\n"
        "def optional(client: Reader | None): return None\n"
        "def future_bad(client: Concrete): return None\n"
        "def _private(client: Concrete): return None\n"
        "class Holder:\n    reader: Reader | None\n"
        "class WrongHolder:\n    reader: Concrete\n"
        "class MissingHolder:\n    reader = None\n"
    )

    result = _observe(tmp_path)
    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert {item.data.get("qualified_name") for item in violations} == {
        "sample.core.broad",
        "sample.core.any_type",
        "sample.core.concrete",
        "sample.core.missing",
        "sample.core.optional",
        "sample.core.future_bad",
        "sample.core.WrongHolder",
        "sample.core.MissingHolder",
    }
    assert "sample.core._private" not in {item.data.get("qualified_name") for item in violations}
    unknowns = result.observation.records("unknowns") or ()
    assert any(
        item.kind == "protocol_declaration_limit"
        and item.data.get("qualified_name") == "sample.core.shadowed_any"
        for item in unknowns
    )


def test_imported_and_quoted_aliases_resolve_but_unresolved_names_stay_unknown(
    tmp_path: Path,
) -> None:
    raw = _contract()
    raw["components"][0]["packages"] = ["sample"]
    raw["rules"][0]["source"] = "sample"
    raw["rules"][0]["protocol"] = "sample.ports.Reader"
    raw["rules"][0]["selectors"] = [{"role": "parameter", "name": "client", "visibility": "public"}]
    (tmp_path / "contract.json").write_text(json.dumps(raw))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/__init__.py").write_text("")
    (tmp_path / "sample/ports.py").write_text(
        "from typing import Protocol\nclass Reader(Protocol):\n    def read(self) -> bytes: ...\n"
    )
    (tmp_path / "sample/facade.py").write_text("from .ports import Reader as ExportedReader\n")
    (tmp_path / "sample/app.py").write_text(
        "from typing import TypeAlias\n"
        "from .facade import ExportedReader as Port\n"
        "CanonicalPort: TypeAlias = Port\n"
        "class Concrete:\n    def read(self) -> bytes: return b''\n"
        "def imported(client: Port): return client.read()\n"
        "def quoted(client: 'Port'): return client.read()\n"
        "def type_alias(client: CanonicalPort): return client.read()\n"
        "def wrong(client: Concrete): return client.read()\n"
        "ConcretePort: TypeAlias = Concrete | Port\n"
        "def unsupported_alias(client: ConcretePort): return None\n"
        "def unresolved(client: 'MissingPort'): return None\n"
    )
    (tmp_path / "sample/shadow.py").write_text(
        "from .ports import Reader as Port\n"
        "class Port: ...\n"
        "def shadowed(client: Port): return None\n"
    )

    result = _observe(tmp_path)
    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert [item.data.get("qualified_name") for item in violations] == ["sample.app.wrong"]
    unknowns = result.observation.records("unknowns") or ()
    assert any(
        item.kind == "protocol_declaration_limit"
        and item.data.get("qualified_name")
        in {
            "sample.app.unresolved",
            "sample.app.unsupported_alias",
            "sample.shadow.shadowed",
        }
        for item in unknowns
    )
    assert {
        item.data.get("qualified_name")
        for item in unknowns
        if item.kind == "protocol_declaration_limit"
    } >= {
        "sample.app.unresolved",
        "sample.app.unsupported_alias",
        "sample.shadow.shadowed",
    }
    saved = tmp_path / "saved-report.json"
    saved.write_bytes(canonical_report_bytes(result.observation))
    replay = run_saved_report(saved)
    assert (
        next(
            item for item in replay.rule_assessments if item.id == "APP-READER-DECLARATIONS"
        ).status.value
        == "FAIL"
    )
    sections = tuple(
        replace(
            section,
            records=tuple(
                replace(
                    item,
                    data=type(item.data)(
                        tuple(
                            (key, "tampered" if key == "reason" else value)
                            for key, value in item.data.entries
                        )
                    ),
                )
                if item.kind == "protocol_declaration"
                else item
                for item in section.records
            ),
        )
        if section.name == "violations"
        else section
        for section in result.observation.sections
    )
    saved.write_bytes(canonical_report_bytes(replace(result.observation, sections=sections)))
    tampered = run_saved_report(saved)
    tampered_rule = next(
        item for item in tampered.rule_assessments if item.id == "APP-READER-DECLARATIONS"
    )
    assert tampered_rule.status.value == "FAIL"
    assert tampered_rule.evaluation_proven is False
    without_receipt = tuple(
        replace(
            section,
            records=tuple(
                item
                for item in section.records
                if not (
                    item.kind == "rule_evaluation" and item.rule_ids == ("APP-READER-DECLARATIONS",)
                )
            ),
        )
        if section.name == "scope_observations"
        else section
        for section in result.observation.sections
    )
    saved.write_bytes(canonical_report_bytes(replace(result.observation, sections=without_receipt)))
    missing_receipt = run_saved_report(saved)
    missing_receipt_rule = next(
        item for item in missing_receipt.rule_assessments if item.id == "APP-READER-DECLARATIONS"
    )
    assert missing_receipt_rule.status.value == "FAIL"
    assert missing_receipt_rule.evaluation_proven is False


def test_empty_selector_scope_is_unknown(tmp_path: Path) -> None:
    raw = _contract()
    raw["rules"][0]["selectors"] = [{"role": "parameter", "name": "client", "visibility": "public"}]
    (tmp_path / "contract.json").write_text(json.dumps(raw))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(
        "from typing import Protocol\n"
        "class Reader(Protocol):\n    def read(self) -> bytes: ...\n"
        "def other(value: Reader): return value.read()\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    unknowns = result.observation.records("unknowns") or ()
    assert any(
        item.kind == "protocol_declaration_limit"
        and item.rule_ids == ("APP-READER-DECLARATIONS",)
        and item.data.get("reason") == "empty_scope"
        for item in unknowns
    )


def test_explicit_optional_parameter_accepts_only_protocol_or_none(tmp_path: Path) -> None:
    raw = _contract()
    raw["rules"][0]["selectors"] = [
        {"role": "parameter", "name": "client", "visibility": "public", "optional": True}
    ]
    (tmp_path / "contract.json").write_text(json.dumps(raw))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(
        "from typing import Optional, Protocol\n"
        "class Reader(Protocol): ...\n"
        "class Concrete: ...\n"
        "def exact(client: Reader): pass\n"
        "def pep604(client: Reader | None): pass\n"
        "def optional(client: Optional[Reader]): pass\n"
        "def extra_arm(client: Reader | Concrete | None): pass\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    assert {
        item.data.get("qualified_name") for item in trace_valid_violations(result.observation)
    } == {"sample.core.extra_arm"}


def test_older_contract_versions_reject_protocol_declaration_rule() -> None:
    raw = _contract()
    raw["schema_version"] = "3.8.0"
    with pytest.raises(ValueError, match="3.9.0"):
        parse_contract(raw)
    schema_root = Path(__file__).parents[1] / "schema"
    prior_schema = json.loads((schema_root / "architecture-contract-3.8.schema.json").read_bytes())
    current_schema = json.loads(
        (schema_root / "architecture-contract-3.9.schema.json").read_bytes()
    )
    assert list(Draft202012Validator(prior_schema).iter_errors(raw))
    assert not list(Draft202012Validator(current_schema).iter_errors(_contract()))


@pytest.mark.parametrize("columnar", [False, True])
def test_valid_parameter_and_member_declarations_are_proven_on_saved_replay(
    tmp_path: Path, columnar: bool
) -> None:
    raw = _contract()
    raw["components"][0]["packages"] = ["sample"]
    raw["rules"][0]["source"] = "sample"
    raw["rules"][0]["selectors"] = [
        {"role": "parameter", "name": "client", "visibility": "public", "optional": True},
        {"role": "member", "name": "reader", "visibility": "public", "optional": True},
    ]
    (tmp_path / "contract.json").write_text(json.dumps(raw))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(
        "from typing import Protocol\n"
        "class Reader(Protocol):\n    def read(self) -> bytes: ...\n"
        "def good(client: Reader | None): return None\n"
        "class Holder:\n    reader: Reader | None\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    [row] = [
        item
        for item in rule_assessments(result.observation, undecided_by_rule={})
        if item.id == "APP-READER-DECLARATIONS"
    ]
    assert row.status.value == "PASS"
    assert row.evaluation_proven is True
    report = observation_payload(result.observation)
    legacy = dict(report)
    legacy["schema_version"] = "2.1.0"
    with pytest.raises(ValueError, match="observation schema 2.3.0"):
        parse_observation(legacy)
    saved = tmp_path / "saved-report.json"
    saved.write_text(json.dumps(encode_canonical_model(report) if columnar else report))
    [replayed] = [
        item
        for item in (run_saved_report(saved).rule_assessments or ())
        if item.id == "APP-READER-DECLARATIONS"
    ]
    assert replayed == row


def test_mounted_rule_is_limited_to_its_actual_source_modules(tmp_path: Path) -> None:
    rule = {
        "id": "APP-READER-DECLARATIONS",
        "kind": "protocol_declarations",
        "source": "sample.caller",
        "protocol": "sample.ports.Reader",
        "selectors": [{"role": "parameter", "name": "client", "visibility": "public"}],
        "rationale": "The caller API exposes the Reader port.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    files = {
        "sample/__init__.py": "",
        "sample/caller/__init__.py": (
            "from ..ports import Reader\ndef consume(client: Reader): return None\n"
        ),
        "sample/ports.py": "from typing import Protocol\nclass Reader(Protocol): ...\n",
        "sample/other.py": "class Concrete: ...\ndef foreign(client: Concrete): return None\n",
        "inside.json": json.dumps(
            {
                "schema_version": "3.9.0",
                "components": [_component("caller", ["sample.caller"])],
                "rules": [rule],
            }
        ),
    }
    root_contract = {
        "schema_version": "3.9.0",
        "components": [
            _component("caller-owner", ["sample.caller"], inside="inside.json"),
            _component("providers", ["sample.ports", "sample.other"]),
        ],
        "rules": [],
    }
    result = _observe_tree(tmp_path, files, root_contract)
    assert result.observation is not None
    [row] = [
        item
        for item in rule_assessments(result.observation, undecided_by_rule={})
        if item.kind == "protocol_declarations"
    ]
    assert row.status.value == "PASS"
    assert row.evaluation_proven is True
    assert not any(
        item.data.get("qualified_name") == "sample.other.foreign"
        for item in trace_valid_violations(result.observation)
    )


def test_missing_protocol_port_is_unknown(tmp_path: Path) -> None:
    raw = _contract()
    raw["rules"][0]["selectors"] = [{"role": "parameter", "name": "client", "visibility": "public"}]
    raw["rules"][0]["protocol"] = "sample.core.MissingReader"
    (tmp_path / "contract.json").write_text(json.dumps(raw))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text("def consume(client: object): return None\n")
    result = _observe(tmp_path)
    assert result.observation is not None
    assert any(
        item.kind == "protocol_declaration_limit"
        and item.data.get("reason") == "protocol_missing_or_ambiguous"
        for item in result.observation.records("unknowns") or ()
    )


@pytest.mark.parametrize("tamper", ["source_digest", "contract_digest", "schema"])
def test_stale_protocol_scope_proofs_cannot_prove_pass(tmp_path: Path, tamper: str) -> None:
    raw = _contract()
    raw["components"][0]["packages"] = ["sample"]
    raw["rules"][0]["source"] = "sample"
    raw["rules"][0]["selectors"] = [{"role": "parameter", "name": "client", "visibility": "public"}]
    (tmp_path / "contract.json").write_text(json.dumps(raw))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(
        "from typing import Protocol\nclass Reader(Protocol): ...\n"
        "def consume(client: Reader): return None\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    sections = result.observation.sections
    if tamper != "schema":
        sections = tuple(
            replace(
                section,
                records=tuple(
                    replace(
                        record,
                        data=type(record.data)(
                            tuple(
                                (
                                    key,
                                    type(value)(
                                        tuple(
                                            (
                                                proof_key,
                                                "stale" if proof_key == tamper else proof_value,
                                            )
                                            for proof_key, proof_value in value.entries
                                        )
                                    )
                                    if key == "protocol_scope_proof"
                                    else value,
                                )
                                for key, value in record.data.entries
                            )
                        ),
                    )
                    if record.kind == "rule_evaluation"
                    and record.rule_ids == ("APP-READER-DECLARATIONS",)
                    else record
                    for record in section.records
                ),
            )
            if section.name == "scope_observations"
            else section
            for section in sections
        )
        observation = replace(result.observation, sections=sections)
    else:
        observation = replace(result.observation, schema_version="2.0.0")
    saved = tmp_path / "stale.json"
    saved.write_bytes(canonical_report_bytes(observation))
    replay = run_saved_report(saved)
    if tamper == "schema":
        assert replay.exit_code == 2
        assert replay.declared_rules == "UNKNOWN"
        return
    assert replay.rule_assessments is not None
    [row] = [item for item in replay.rule_assessments if item.id == "APP-READER-DECLARATIONS"]
    assert row.status.value == "UNKNOWN"
    assert row.evaluation_proven is False


def test_protocol_proof_transplanted_from_another_source_cannot_prove_pass(tmp_path: Path) -> None:
    def observe(root: Path, body: str):
        raw = _contract()
        raw["components"][0]["packages"] = ["sample"]
        raw["rules"][0]["source"] = "sample"
        raw["rules"][0]["selectors"] = [
            {"role": "parameter", "name": "client", "visibility": "public"}
        ]
        root.mkdir()
        (root / "contract.json").write_text(json.dumps(raw))
        (root / "sample").mkdir()
        (root / "sample/core.py").write_text(body)
        result = _observe(root)
        assert result.observation is not None
        return result.observation

    first = observe(
        tmp_path / "first",
        "from typing import Protocol\nclass Reader(Protocol): ...\n"
        "def consume(client: Reader): return None\n",
    )
    second = observe(
        tmp_path / "second",
        "from typing import Protocol\nclass Reader(Protocol): ...\n"
        "def consume(client: Reader): return None\n# distinct source bytes\n",
    )
    second_receipt = next(
        record
        for record in second.records("scope_observations") or ()
        if record.kind == "rule_evaluation" and record.rule_ids == ("APP-READER-DECLARATIONS",)
    )
    sections = tuple(
        replace(
            section,
            records=tuple(
                replace(
                    record,
                    data=type(record.data)(
                        tuple(
                            (key, second_receipt.data.get("protocol_scope_proof"))
                            if key == "protocol_scope_proof"
                            else (key, value)
                            for key, value in record.data.entries
                        )
                    ),
                )
                if record.kind == "rule_evaluation"
                and record.rule_ids == ("APP-READER-DECLARATIONS",)
                else record
                for record in section.records
            ),
        )
        if section.name == "scope_observations"
        else section
        for section in first.sections
    )
    saved = tmp_path / "transplanted.json"
    saved.write_bytes(canonical_report_bytes(replace(first, sections=sections)))
    replay = run_saved_report(saved)
    [row] = [item for item in replay.rule_assessments or () if item.id == "APP-READER-DECLARATIONS"]
    assert row.status.value == "UNKNOWN"
    assert row.evaluation_proven is False


def test_protocol_reference_inventory_preserves_full_symbol_on_rename():
    from archkeel.ir.model import module_references
    from archkeel.ir.renames import renamed_contract

    contract = parse_contract(_contract())
    reference = next(
        item for item in module_references(contract) if item.pointer == "/rules/0/protocol"
    )
    assert reference.value == "sample.core.Reader" and reference.held
    changed = renamed_contract(contract, {"sample.core": "sample.engine"})
    rule = json.loads(contract_bytes(changed))["rules"][0]
    assert rule["source"] == "sample.engine"
    assert rule["protocol"] == "sample.engine.Reader"
