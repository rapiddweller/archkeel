# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Canonical Protocol declaration rule behavior (#616)."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
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
from archkeel.ir.decisions import rule_assessments, unknown_positions_by_rule
from archkeel.ir.model import SCHEMA_VERSION
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]


def _contract() -> dict[str, object]:
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_text())
    raw["schema_version"] = "3.9.0"
    raw["components"] = [_component("all", ["sample"])]
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


def test_protocol_identity_requires_a_qualified_symbol_in_reader_and_schema() -> None:
    raw = _contract()
    raw["rules"][0]["protocol"] = "Reader"
    schema = json.loads((ROOT / "schema/architecture-contract-3.9.schema.json").read_bytes())
    assert list(Draft202012Validator(schema).iter_errors(raw))
    with pytest.raises(ValueError, match="protocol must be a canonical module.symbol"):
        parse_contract(raw)


def test_protocol_selector_identity_duplicates_are_reader_semantics() -> None:
    schema = json.loads((ROOT / "schema/architecture-contract-3.9.schema.json").read_bytes())
    validator = Draft202012Validator(schema)
    selector = {"role": "member", "name": "reader", "visibility": "public"}
    for duplicate in (selector.copy(), {**selector, "visibility": "all", "optional": True}):
        raw = _contract()
        raw["rules"][0]["selectors"] = [selector, duplicate]
        assert not list(validator.iter_errors(raw))
        with pytest.raises(ValueError, match="must not repeat a role and name"):
            parse_contract(raw)


@pytest.mark.parametrize("role", ["parameter", "member"])
@pytest.mark.parametrize(
    "annotation,status", [(None, "UNKNOWN"), ("Reader", "PASS"), ("Concrete", "FAIL")]
)
@pytest.mark.parametrize("columnar", [False, True])
def test_local_definitions_do_not_count_as_api_declarations(
    tmp_path: Path, role: str, annotation: str | None, status: str, columnar: bool
) -> None:
    from archkeel.ir.decisions import unknown_positions_by_rule

    raw = _contract()
    raw["rules"][0]["selectors"] = [
        {"role": role, "name": "client" if role == "parameter" else "reader", "visibility": "all"}
    ]
    (tmp_path / "contract.json").write_text(json.dumps(raw))
    (tmp_path / "sample").mkdir()
    source = (
        "from typing import Protocol\n"
        "class Reader(Protocol): ...\nclass Concrete: pass\n"
        "def outer():\n"
        "    def local(client: Concrete): pass\n"
        "    class Local:\n        reader: Concrete\n"
    )
    if annotation is not None:
        source += (
            f"def consume(client: {annotation}): pass\n"
            if role == "parameter"
            else f"class Holder:\n    reader: {annotation}\n"
        )
    (tmp_path / "sample/core.py").write_text(source)
    result = _observe(tmp_path)
    assert not result.diagnostics and result.observation is not None
    rows = rule_assessments(
        result.observation, undecided_by_rule=unknown_positions_by_rule(result.observation)
    )
    assert rows[0].status.value == status
    payload = observation_payload(result.observation)
    saved = tmp_path / "local.json"
    saved.write_text(json.dumps(encode_canonical_model(payload) if columnar else payload))
    assert run_saved_report(saved).rule_assessments == rows


@pytest.mark.parametrize("annotation,status", [("Reader", "UNKNOWN"), ("Concrete", "FAIL")])
def test_each_selector_requires_its_own_matches(
    tmp_path: Path, annotation: str, status: str
) -> None:
    from archkeel.ir.decisions import unknown_positions_by_rule

    (tmp_path / "contract.json").write_text(json.dumps(_contract()))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(
        "from typing import Protocol\n"
        "class Reader(Protocol):\n    def read(self) -> bytes: ...\n"
        "class Concrete: pass\n"
        f"def consume(client: {annotation}): return None\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    rows = rule_assessments(
        result.observation, undecided_by_rule=unknown_positions_by_rule(result.observation)
    )
    [row] = [item for item in rows if item.id == "APP-READER-DECLARATIONS"]
    assert row.status.value == status
    assert row.undecided > 0
    assert not row.evaluation_proven
    for columnar in (False, True):
        saved = tmp_path / "saved.json"
        payload = observation_payload(result.observation)
        saved.write_text(json.dumps(encode_canonical_model(payload) if columnar else payload))
        assert run_saved_report(saved).rule_assessments == rows


@pytest.mark.parametrize("prefix", ["*", "**"])
@pytest.mark.parametrize("annotation,status", [("Reader", "PASS"), ("Concrete", "FAIL")])
def test_variadic_parameters_match_their_source_identifier(
    tmp_path: Path, prefix: str, annotation: str, status: str
) -> None:
    raw = _contract()
    raw["rules"][0]["selectors"] = [raw["rules"][0]["selectors"][0]]
    (tmp_path / "contract.json").write_text(json.dumps(raw))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(
        "from typing import Protocol\n"
        "class Reader(Protocol):\n    def read(self) -> bytes: ...\n"
        "class Concrete: pass\n"
        f"def consume({prefix}client: {annotation}): return None\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    [row] = [
        item
        for item in rule_assessments(result.observation, undecided_by_rule={})
        if item.id == "APP-READER-DECLARATIONS"
    ]
    assert row.status.value == status


@pytest.mark.parametrize("field_type", ["Payload", "MissingPayload"])
@pytest.mark.parametrize("annotation", ["Reader", "Port"])
def test_protocol_identity_does_not_descend_into_facade_fields(
    tmp_path: Path, field_type: str, annotation: str
) -> None:
    from archkeel.ir.decisions import unknown_positions_by_rule

    raw = _contract()
    raw["components"][0]["public"] = ["sample.core:Reader", "sample.core:Payload"]
    raw["rules"][0]["selectors"] = [raw["rules"][0]["selectors"][0]]
    (tmp_path / "contract.json").write_text(json.dumps(raw))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(
        "from typing import Protocol, TypeAlias\n"
        "class Payload: pass\n"
        f"class Reader(Protocol):\n    payload: {field_type}\n"
        "Port: TypeAlias = Reader\n"
        f"def consume(client: {annotation}): return None\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    rows = rule_assessments(
        result.observation, undecided_by_rule=unknown_positions_by_rule(result.observation)
    )
    [row] = [item for item in rows if item.id == "APP-READER-DECLARATIONS"]
    assert row.status.value == "PASS"
    for columnar in (False, True):
        saved = tmp_path / "saved.json"
        payload = observation_payload(result.observation)
        saved.write_text(json.dumps(encode_canonical_model(payload) if columnar else payload))
        assert run_saved_report(saved).rule_assessments == rows


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "not-a-name"),
        ("name", "client\n"),
        ("source", "sample..core"),
        ("source", "sample.core\n"),
        ("protocol", "sample.Reader-1"),
        ("protocol", "sample.Reader\n"),
    ],
)
def test_protocol_schema_rejects_non_identifier_selectors(field: str, value: str) -> None:
    raw = _contract()
    target = raw["rules"][0]["selectors"][0] if field == "name" else raw["rules"][0]
    target[field] = value
    with pytest.raises(ValueError):
        parse_contract(raw)
    schema = json.loads((ROOT / "schema/architecture-contract-3.9.schema.json").read_bytes())
    assert list(Draft202012Validator(schema).iter_errors(raw))


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
    } == {
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


@pytest.mark.parametrize("section_name", ["declarations", "scope_observations", "violations"])
@pytest.mark.parametrize("boundary", ["read", "write", "schema", "python_schema"])
def test_legacy_reports_reject_all_protocol_vocabulary(
    tmp_path: Path, section_name: str, boundary: str
) -> None:
    raw = _contract()
    raw["rules"][0]["selectors"] = [raw["rules"][0]["selectors"][0]]
    (tmp_path / "contract.json").write_text(json.dumps(raw))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(
        "from typing import Protocol\n"
        "class Reader(Protocol):\n    def read(self) -> bytes: ...\n"
        "def consume(client: object): return None\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    sections = tuple(
        section if section.name == section_name else replace(section, records=())
        for section in result.observation.sections
    )
    observation = replace(result.observation, sections=sections)
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema))
        for path in (ROOT / "schema").glob("*.json")
        if (schema := json.loads(path.read_bytes()))
    )
    for version in ("2.0.0", "2.1.0", "2.2.0"):
        if boundary in {"schema", "python_schema"}:
            profile = "python-decoded" if boundary == "python_schema" else "decoded"
            payload = observation_payload(observation)
            current = Draft202012Validator(
                {"$ref": f"urn:archkeel:architecture-ir:{profile}:{SCHEMA_VERSION}"},
                registry=registry,
            )
            assert not list(current.iter_errors(payload))
            payload["schema_version"] = version
            legacy = Draft202012Validator(
                {"$ref": f"urn:archkeel:architecture-ir:{profile}:{version}"}, registry=registry
            )
            assert list(legacy.iter_errors(payload)), (version, section_name)
            continue
        with pytest.raises(ValueError, match="observation schema 2.3.0"):
            if boundary == "write":
                observation_payload(replace(observation, schema_version=version))
            else:
                payload = observation_payload(observation)
                payload["schema_version"] = version
                parse_observation(payload)


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


@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize(
    ("member_body", "expected"),
    [
        ("reader: Reader\n    reader = Concrete()", "UNKNOWN"),
        ("reader: Concrete\n    reader: Reader", "UNKNOWN"),
        ("reader = Concrete()", "FAIL"),
    ],
)
def test_rebound_member_declarations_cannot_replay_a_stale_protocol_pass(
    tmp_path: Path, columnar: bool, member_body: str, expected: str
) -> None:
    from archkeel.ir.decisions import unknown_positions_by_rule

    raw = _contract()
    raw["components"][0]["packages"] = ["sample"]
    raw["rules"][0]["source"] = "sample"
    raw["rules"][0]["selectors"] = [{"role": "member", "name": "reader", "visibility": "public"}]
    (tmp_path / "contract.json").write_text(json.dumps(raw))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(
        "from typing import Protocol\n"
        "class Reader(Protocol): ...\n"
        "class Concrete: pass\n"
        f"class Holder:\n    {member_body}\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    rows = rule_assessments(
        result.observation,
        undecided_by_rule=unknown_positions_by_rule(result.observation),
    )
    [row] = [item for item in rows if item.id == "APP-READER-DECLARATIONS"]
    assert row.status.value == expected
    payload = observation_payload(result.observation)
    saved = tmp_path / "rebound.json"
    saved.write_text(json.dumps(encode_canonical_model(payload) if columnar else payload))
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


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("annotation,expected", [("Reader", "UNKNOWN"), ("Concrete", "FAIL")])
def test_partial_protocol_source_scope_withholds_receipt_but_keeps_known_failures(
    tmp_path: Path, mounted: bool, annotation: str, expected: str
) -> None:
    rule = {
        "id": "APP-READER-DECLARATIONS",
        "kind": "protocol_declarations",
        "source": "sample.core",
        "protocol": "sample.core.Reader",
        "selectors": [{"role": "parameter", "name": "client", "visibility": "all"}],
        "rationale": "Selected API parameters use the Reader port.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    files = {
        "sample/__init__.py": "",
        "sample/core/__init__.py": (
            "from typing import Protocol\n"
            "class Reader(Protocol): ...\n"
            "class Concrete: ...\n"
            f"def consume(client: {annotation}): pass\n"
        ),
        "sample/other/__init__.py": "value = 1\n",
    }
    if mounted:
        files["inside.json"] = json.dumps(
            {
                "schema_version": "3.9.0",
                "components": [
                    _component("core", ["sample.core"]),
                    _component("other", ["sample.other"]),
                ],
                "rules": [rule],
            }
        )
        root_contract = {
            "schema_version": "3.9.0",
            "components": [_component("all", ["sample"], inside="inside.json")],
            "rules": [],
        }
    else:
        root_contract = {
            "schema_version": "3.9.0",
            "components": [
                _component("core", ["sample.core"]),
                _component("other", ["sample.other"]),
            ],
            "rules": [rule],
        }

    result = _observe_tree(tmp_path, files, root_contract, roots=("sample/core",))
    assert result.observation is not None
    [row] = [
        item
        for item in rule_assessments(
            result.observation,
            undecided_by_rule=unknown_positions_by_rule(result.observation),
        )
        if item.kind == "protocol_declarations"
    ]
    assert row.status.value == expected
    assert row.evaluation_proven is False
    if expected == "FAIL":
        assert any(
            item.kind == "protocol_declaration"
            for item in result.observation.records("violations") or ()
        )
    else:
        assert any(
            item.kind == "protocol_declaration_limit"
            and item.data.get("reason") == "incomplete_scope"
            for item in result.observation.records("unknowns") or ()
        )


@pytest.mark.parametrize(
    "role,selector_name,source",
    [
        (
            "parameter",
            "client",
            "def consume(client: Reader): pass\nif FEATURE:\n    consume = replacement\n",
        ),
        (
            "parameter",
            "client",
            "def consume(client: Reader): pass\ndef consume(client: Reader): pass\n",
        ),
        (
            "member",
            "reader",
            "class Holder:\n    reader: Reader\nif FEATURE:\n    Holder = replacement\n",
        ),
        (
            "member",
            "reader",
            "class Holder:\n    reader: Reader\nclass Holder:\n    reader: Reader\n",
        ),
    ],
)
def test_nonunique_selected_declarations_are_unknown(
    tmp_path: Path, role: str, selector_name: str, source: str
) -> None:
    raw = _contract()
    raw["components"][0]["packages"] = ["sample"]
    raw["rules"][0]["source"] = "sample"
    raw["rules"][0]["selectors"] = [{"role": role, "name": selector_name, "visibility": "all"}]
    (tmp_path / "contract.json").write_text(json.dumps(raw))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(
        "from typing import Protocol\nclass Reader(Protocol): ...\n" + source
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    rows = rule_assessments(
        result.observation,
        undecided_by_rule=unknown_positions_by_rule(result.observation),
    )
    [row] = [item for item in rows if item.id == "APP-READER-DECLARATIONS"]
    assert row.status.value == "UNKNOWN"
    unknowns = [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "protocol_declaration_limit"
    ]
    assert any(item.data.get("reason") == "declaration_binding_ambiguous" for item in unknowns)
    assert not any(item.data.get("reason") == "empty_scope" for item in unknowns)


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


@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize(
    "annotation,source_section,kind",
    [
        ("Concrete", "violations", "protocol_declaration"),
        ("MissingPort", "unknowns", "protocol_declaration_limit"),
    ],
)
def test_protocol_result_cannot_move_out_of_its_semantic_section(
    tmp_path: Path, annotation: str, source_section: str, kind: str, columnar: bool
) -> None:
    raw = _contract()
    raw["rules"][0]["selectors"] = [{"role": "parameter", "name": "client", "visibility": "public"}]
    (tmp_path / "contract.json").write_text(json.dumps(raw))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(
        "from typing import Protocol\nclass Reader(Protocol): ...\n"
        "class Concrete: pass\n"
        f"def consume(client: {annotation}): pass\n"
    )
    result = _observe(tmp_path)
    assert not result.diagnostics and result.observation is not None
    payload = observation_payload(result.observation)
    moved = next(record for record in payload[source_section] if record["kind"] == kind)
    payload[source_section].remove(moved)
    payload["scope_observations"].append(moved)
    saved = tmp_path / "moved-result.json"
    saved.write_text(json.dumps(encode_canonical_model(payload) if columnar else payload))
    replay = run_saved_report(saved)
    [row] = [row for row in replay.rule_assessments or () if row.id == "APP-READER-DECLARATIONS"]
    assert row.status.value == "UNKNOWN"
    assert not row.evaluation_proven


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
    saved = tmp_path / "stale.json"
    if tamper == "schema":
        payload = observation_payload(result.observation)
        payload["schema_version"] = "2.0.0"
        saved.write_text(json.dumps(encode_canonical_model(payload)))
    else:
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
