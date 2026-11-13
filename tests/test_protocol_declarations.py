# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Canonical Protocol declaration rule behavior (#616)."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_exact_module_ownership import _component, _observe_tree

from archkeel.check.report import run_saved_report
from archkeel.ir.codec import (
    canonical_report_bytes,
    contract_bytes,
    encode_canonical_model,
    observation_payload,
    parse_contract,
)
from archkeel.ir.decisions import rule_assessments, unknown_positions_by_rule
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


@pytest.mark.parametrize(
    ("field", "value", "diagnostic"),
    [
        ("source", "sample..api", "source must be a dotted source identity"),
        ("protocol", "sample..Port", "protocol must be a canonical module.symbol"),
        ("protocol", "sample.Port-1", "protocol must be a canonical module.symbol"),
        ("selector", "client.name", "name must be one exact source identifier"),
        ("selector", "2client", "name must be one exact source identifier"),
    ],
)
def test_contract_310_protocol_schema_and_reader_reject_noncanonical_names(
    field: str, value: str, diagnostic: str
) -> None:
    raw = _contract()
    raw["schema_version"] = "3.10.0"
    if field == "selector":
        raw["rules"][0]["selectors"][0]["name"] = value
    else:
        raw["rules"][0][field] = value
    schema = json.loads((ROOT / "schema/architecture-contract-3.10.schema.json").read_bytes())
    assert list(Draft202012Validator(schema).iter_errors(raw))
    with pytest.raises(ValueError, match=diagnostic):
        parse_contract(raw)


def test_contract_310_protocol_schema_and_reader_accept_canonical_names() -> None:
    raw = _contract()
    raw["schema_version"] = "3.10.0"
    schema = json.loads((ROOT / "schema/architecture-contract-3.10.schema.json").read_bytes())
    assert not list(Draft202012Validator(schema).iter_errors(raw))
    assert parse_contract(raw).rules[0].protocol == "sample.core.Reader"


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


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize(
    ("annotation", "method_prefix", "method_tail", "expected"),
    [
        ("Reader", "", "", "PASS"),
        ("Concrete", "", "", "FAIL"),
        (None, "", "", "FAIL"),
        ("Reader", "    @opaque\n", "", "UNKNOWN"),
        ("Reader", "", "\n    consume = replacement", "UNKNOWN"),
    ],
)
def test_method_parameter_uses_final_method_binding_proof(
    tmp_path: Path,
    mounted: bool,
    columnar: bool,
    annotation: str | None,
    method_prefix: str,
    method_tail: str,
    expected: str,
) -> None:
    rule = {
        "id": "APP-READER-DECLARATIONS",
        "kind": "protocol_declarations",
        "source": "sample.core",
        "protocol": "sample.core.Reader",
        "selectors": [{"role": "parameter", "name": "client", "visibility": "public"}],
        "rationale": "Selected methods expose the Reader port.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    annotation_source = f": {annotation}" if annotation else ""
    method = f"{method_prefix}    def consume(self, client{annotation_source}): pass"
    files = {
        "sample/__init__.py": "",
        "sample/core/__init__.py": (
            "from typing import Protocol\n"
            "class Reader(Protocol):\n    def read(self) -> bytes: ...\n"
            "class Concrete: pass\n"
            "def replacement(*args): pass\n"
            f"class Service:\n{method}{method_tail}\n"
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
        contract = {
            "schema_version": "3.9.0",
            "components": [_component("all", ["sample"], inside="inside.json")],
            "rules": [],
        }
    else:
        contract = {
            "schema_version": "3.9.0",
            "components": [
                _component("core", ["sample.core"]),
                _component("other", ["sample.other"]),
            ],
            "rules": [rule],
        }
    result = _observe_tree(tmp_path, files, contract)
    assert result.observation is not None, result.diagnostics
    rows = rule_assessments(
        result.observation,
        undecided_by_rule=unknown_positions_by_rule(result.observation),
    )
    [row] = [item for item in rows if item.kind == "protocol_declarations"]
    assert row.status.value == expected
    payload = observation_payload(result.observation)
    saved = tmp_path / "method-parameter.json"
    saved.write_text(json.dumps(encode_canonical_model(payload) if columnar else payload))
    [replayed] = [
        item
        for item in (run_saved_report(saved).rule_assessments or ())
        if item.kind == "protocol_declarations"
    ]
    assert replayed == row


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_decorated_method_replaced_by_nested_class_is_unknown(
    tmp_path: Path, mounted: bool, columnar: bool
) -> None:
    rule = {
        "id": "APP-READER-DECLARATIONS",
        "kind": "protocol_declarations",
        "source": "sample.core",
        "protocol": "sample.core.Reader",
        "selectors": [{"role": "parameter", "name": "client", "visibility": "all"}],
        "rationale": "Selected method parameters use the canonical Reader port.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    files = {
        "sample/__init__.py": "",
        "sample/core.py": (
            "from typing import Protocol\n"
            "class Reader(Protocol): ...\n"
            "class Service:\n"
            "    @staticmethod\n"
            "    def consume(client: Reader): pass\n"
            "    class consume: pass\n"
        ),
        "sample/other.py": "value = 1\n",
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
        contract = {
            "schema_version": "3.9.0",
            "components": [_component("all", ["sample"], inside="inside.json")],
            "rules": [],
        }
    else:
        contract = {
            "schema_version": "3.9.0",
            "components": [
                _component("core", ["sample.core"]),
                _component("other", ["sample.other"]),
            ],
            "rules": [rule],
        }
    result = _observe_tree(tmp_path, files, contract)
    assert result.observation is not None, result.diagnostics
    [row] = [
        item
        for item in rule_assessments(
            result.observation,
            undecided_by_rule=unknown_positions_by_rule(result.observation),
        )
        if item.kind == "protocol_declarations"
    ]
    assert row.status.value == "UNKNOWN"
    payload = observation_payload(result.observation)
    saved = tmp_path / "nested-class-replacement.json"
    saved.write_text(json.dumps(encode_canonical_model(payload) if columnar else payload))
    [replayed] = [
        item
        for item in (run_saved_report(saved).rule_assessments or ())
        if item.kind == "protocol_declarations"
    ]
    assert replayed == row


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize(
    ("target_source", "annotation"),
    [
        ("if FEATURE:\\n    class Reader(Protocol): ...\\n", "Concrete"),
        ("if FEATURE:\\n    class Reader(Protocol): ...\\n", None),
        ("@opaque\\nclass Reader(Protocol): ...\\n", "Concrete"),
        ("@opaque\\nclass Reader(Protocol): ...\\n", None),
    ],
)
def test_unproven_required_protocol_target_keeps_positions_unknown(
    tmp_path: Path,
    mounted: bool,
    columnar: bool,
    target_source: str,
    annotation: str | None,
) -> None:
    rule = {
        "id": "APP-READER-DECLARATIONS",
        "kind": "protocol_declarations",
        "source": "sample.core",
        "protocol": "sample.core.Reader",
        "selectors": [{"role": "parameter", "name": "client", "visibility": "all"}],
        "rationale": "Selected parameters use the statically bound canonical Reader.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    annotation_text = f": {annotation}" if annotation is not None else ""
    files = {
        "sample/__init__.py": "",
        "sample/core.py": (
            "from typing import Protocol\\n"
            "class Concrete: pass\\n"
            "def opaque(value): return value\\n"
            + target_source.replace("\\n", "\n")
            + f"def consume(client{annotation_text}): pass\\n"
        ).replace("\\n", "\n"),
        "sample/other.py": "value = 1\n",
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
        contract = {
            "schema_version": "3.9.0",
            "components": [_component("all", ["sample"], inside="inside.json")],
            "rules": [],
        }
    else:
        contract = {
            "schema_version": "3.9.0",
            "components": [
                _component("core", ["sample.core"]),
                _component("other", ["sample.other"]),
            ],
            "rules": [rule],
        }
    result = _observe_tree(tmp_path, files, contract)
    assert result.observation is not None, result.diagnostics
    [row] = [
        item
        for item in rule_assessments(
            result.observation,
            undecided_by_rule=unknown_positions_by_rule(result.observation),
        )
        if item.kind == "protocol_declarations"
    ]
    assert row.status.value == "UNKNOWN"
    payload = observation_payload(result.observation)
    saved = tmp_path / "unproven-protocol-target.json"
    saved.write_text(json.dumps(encode_canonical_model(payload) if columnar else payload))
    [replayed] = [
        item
        for item in (run_saved_report(saved).rule_assessments or ())
        if item.kind == "protocol_declarations"
    ]
    assert replayed == row


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_function_parameters_require_proven_decorator_binding(
    tmp_path: Path, mounted: bool, columnar: bool
) -> None:
    rule_specs = (
        ("READER", "reader", "Reader", "", "PASS"),
        ("CONCRETE", "concrete", "Concrete", "", "FAIL"),
        ("MISSING", "missing", None, "", "FAIL"),
        ("OPAQUE", "opaque", "Reader", "@opaque\n", "UNKNOWN"),
    )
    rules = [
        {
            "id": f"APP-{rule_id}-DECLARATIONS",
            "kind": "protocol_declarations",
            "source": "sample.core",
            "protocol": "sample.core.Reader",
            "selectors": [{"role": "parameter", "name": name, "visibility": "public"}],
            "rationale": "Selected functions expose the Reader port.",
            "provenance": ["docs/architecture/sample.md"],
            "decided_by": "architect",
        }
        for rule_id, name, _, _, _ in rule_specs
    ]
    function_sources = []
    for _, name, annotation, decorator, _ in rule_specs:
        annotation_source = f": {annotation}" if annotation else ""
        function_sources.append(
            f"{decorator}def {name}_function({name}{annotation_source}): pass\n"
        )
    core_source = (
        "from typing import Protocol\n"
        "class Reader(Protocol):\n    def read(self) -> bytes: ...\n"
        "class Concrete: pass\n"
        "def opaque(function): return function\n" + "".join(function_sources)
    )
    files = {
        "sample/__init__.py": "",
        "sample/core.py": core_source,
        "sample/other.py": "value = 1\n",
    }
    if mounted:
        files["inside.json"] = json.dumps(
            {
                "schema_version": "3.9.0",
                "components": [
                    _component("core", ["sample.core"]),
                    _component("other", ["sample.other"]),
                ],
                "rules": rules,
            }
        )
        contract = {
            "schema_version": "3.9.0",
            "components": [_component("all", ["sample"], inside="inside.json")],
            "rules": [],
        }
    else:
        contract = {
            "schema_version": "3.9.0",
            "components": [
                _component("core", ["sample.core"]),
                _component("other", ["sample.other"]),
            ],
            "rules": rules,
        }
    result = _observe_tree(tmp_path, files, contract)
    assert result.observation is not None, result.diagnostics
    assessments = rule_assessments(
        result.observation,
        undecided_by_rule=unknown_positions_by_rule(result.observation),
    )
    observed = {row.id.rsplit(":", 1)[-1]: row.status.value for row in assessments}
    assert observed == {
        f"APP-{rule_id}-DECLARATIONS": status for rule_id, _, _, _, status in rule_specs
    }
    payload = observation_payload(result.observation)
    saved = tmp_path / "function-parameters.json"
    saved.write_bytes(canonical_report_bytes(payload) if columnar else json.dumps(payload).encode())
    replay = run_saved_report(saved)
    assert not replay.diagnostics
    assert replay.rule_assessments == assessments


def _protocol_binding_cases() -> dict[str, str]:
    return {
        "trusted_parameter": "PASS",
        "decorated_parameter": "UNKNOWN",
        "based_parameter": "UNKNOWN",
        "decorated_base_parameter": "UNKNOWN",
        "metaclass_parameter": "UNKNOWN",
        "rebound_parameter": "UNKNOWN",
        "conditional_parameter": "UNKNOWN",
        "missing_parameter": "FAIL",
        "concrete_parameter": "FAIL",
        "trusted_member": "PASS",
        "default_member": "PASS",
        "method_member": "UNKNOWN",
        "import_member": "UNKNOWN",
        "deleted_member": "UNKNOWN",
        "reassigned_member": "UNKNOWN",
        "missing_member": "FAIL",
        "concrete_member": "FAIL",
    }


def _protocol_binding_rules(cases: dict[str, str]) -> list[dict[str, object]]:
    return [
        {
            "id": f"APP-{name.upper()}-DECLARATIONS",
            "kind": "protocol_declarations",
            "source": "sample.core",
            "protocol": "sample.core.Reader",
            "selectors": [
                {
                    "role": "member" if name.endswith("member") else "parameter",
                    "name": name,
                    "visibility": "public" if name in _PUBLIC_PARAMETER_CASES else "all",
                }
            ],
            "rationale": "Selected positions use the canonical Reader port.",
            "provenance": ["docs/architecture/sample.md"],
            "decided_by": "architect",
        }
        for name in cases
    ]


_PROTOCOL_BINDING_SOURCE = (
    "from typing import Protocol\n"
    "class Reader(Protocol): ...\n"
    "class Concrete: ...\n"
    "def factory(): return object\n"
    "def opaque(function): return function\n"
    "class Trusted:\n"
    "    def receive(self, trusted_parameter: Reader, missing_parameter, "
    "concrete_parameter: Concrete): pass\n"
    "@opaque\nclass Decorated:\n"
    "    def receive(self, decorated_parameter: Reader): pass\n"
    "class Based(factory()):\n"
    "    def receive(self, based_parameter: Reader): pass\n"
    "@opaque\nclass OpaqueBase: pass\n"
    "class DecoratedBaseChild(OpaqueBase):\n"
    "    def receive(self, decorated_base_parameter: Reader): pass\n"
    "class Metaclassed(metaclass=factory()):\n"
    "    def receive(self, metaclass_parameter: Reader): pass\n"
    "class Rebound:\n"
    "    def receive(self, rebound_parameter: Reader): pass\n"
    "Rebound = factory()\n"
    "if FEATURE:\n    class Conditional:\n"
    "        def receive(self, conditional_parameter: Reader): pass\n"
    "class TrustedMember:\n    trusted_member: Reader\n"
    "class DefaultMember:\n    default_member: Reader = None\n"
    "class MethodMember:\n"
    "    method_member: Reader\n    def method_member(self): pass\n"
    "class ImportMember:\n"
    "    from .ports import Reader as import_member\n    import_member: Reader\n"
    "class DeletedMember:\n"
    "    deleted_member: Reader\n    del deleted_member\n"
    "class ReassignedMember:\n"
    "    reassigned_member: Reader\n    reassigned_member = Reader()\n"
    "class MissingMember:\n    missing_member = None\n"
    "class ConcreteMember:\n    concrete_member: Concrete\n"
)

_PUBLIC_PARAMETER_CASES: set[str] = set()


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_protocol_positions_require_static_class_and_member_bindings(
    tmp_path: Path, mounted: bool, columnar: bool
) -> None:
    cases = _protocol_binding_cases()
    rules = _protocol_binding_rules(cases)
    raw = _contract()
    raw["rules"] = rules
    files = {
        "sample/__init__.py": "",
        "sample/core.py": _PROTOCOL_BINDING_SOURCE,
        "sample/ports.py": "",
    }
    if mounted:
        files["inside.json"] = json.dumps(
            {
                "schema_version": "3.9.0",
                "components": [_component("all", ["sample"])],
                "rules": rules,
            }
        )
        raw["components"] = [_component("outer", ["sample"], inside="inside.json")]
        raw["rules"] = []
    result = _observe_tree(tmp_path, files, raw)
    assert not result.diagnostics and result.observation is not None
    assessments = rule_assessments(
        result.observation, undecided_by_rule=unknown_positions_by_rule(result.observation)
    )
    observed = {row.id.rsplit(":", 1)[-1]: row.status.value for row in assessments}
    assert observed == {
        f"APP-{name.upper()}-DECLARATIONS": status for name, status in cases.items()
    }
    payload = observation_payload(result.observation)
    saved = tmp_path / "class-bindings.json"
    saved.write_bytes(canonical_report_bytes(payload) if columnar else json.dumps(payload).encode())
    replay = run_saved_report(saved)
    assert not replay.diagnostics
    assert replay.rule_assessments == assessments


_METHOD_VISIBILITY_CASES = {
    "static_parameter": "PASS",
    "class_parameter": "PASS",
    "abstract_parameter": "PASS",
    "alias_static_parameter": "PASS",
    "alias_abstract_parameter": "PASS",
    "opaque_method_parameter": "UNKNOWN",
    "rebound_method_parameter": "UNKNOWN",
    "deleted_method_parameter": "UNKNOWN",
    "imported_method_parameter": "UNKNOWN",
    "nested_deleted_method_parameter": "UNKNOWN",
    "nested_imported_method_parameter": "UNKNOWN",
}
_PUBLIC_CLASS_CASES = {
    "private_parameter": "PASS",
    "private_nested_parameter": "UNKNOWN",
    "hidden_inner_parameter": "UNKNOWN",
    "public_nested_parameter": "UNKNOWN",
}
_PUBLIC_PARAMETER_CASES = {
    "private_parameter",
    "private_nested_parameter",
    "hidden_inner_parameter",
    "public_nested_parameter",
}
_METHOD_VISIBILITY_SOURCE = (
    "from abc import abstractmethod\n"
    "from abc import abstractmethod as abstract\n"
    "from builtins import staticmethod as stable\n"
    "from typing import Protocol\n"
    "class Reader(Protocol): ...\n"
    "class Concrete: ...\n"
    "def opaque(function): return function\n"
    "class StaticMethods:\n"
    "    @staticmethod\n    def consume(static_parameter: Reader): pass\n"
    "    @classmethod\n    def classed(cls, class_parameter: Reader): pass\n"
    "    @abstractmethod\n    def abstracted(self, abstract_parameter: Reader): pass\n"
    "    @stable\n    def aliased_static(self, alias_static_parameter: Reader): pass\n"
    "    @abstract\n    def aliased_abstract(self, alias_abstract_parameter: Reader): pass\n"
    "    @opaque\n    def opaque(self, opaque_method_parameter: Reader): pass\n"
    "class ReboundMethod:\n"
    "    @staticmethod\n    def consume(rebound_method_parameter: Reader): pass\n"
    "    consume = opaque(consume)\n"
    "class DeletedMethod:\n"
    "    @staticmethod\n"
    "    def consume(deleted_method_parameter: Reader): pass\n"
    "    del consume\n"
    "class ImportedMethod:\n"
    "    @staticmethod\n"
    "    def consume(imported_method_parameter: Reader): pass\n"
    "    from .ports import replacement as consume\n"
    "class NestedDeleteOwner:\n"
    "    class Nested:\n"
    "        def consume(self, nested_deleted_method_parameter: Reader): pass\n"
    "        del consume\n"
    "class NestedImportOwner:\n"
    "    class Nested:\n"
    "        def consume(self, nested_imported_method_parameter: Reader): pass\n"
    "        from .ports import replacement as consume\n"
)
_PUBLIC_CLASS_SOURCE = (
    "from typing import Protocol\n"
    "class Reader(Protocol): ...\n"
    "class Concrete: ...\n"
    "def public_control(private_parameter: Reader): pass\n"
    "class _Internal:\n    def consume(self, private_parameter: Concrete): pass\n"
    "class _Outer:\n"
    "    class PublicInner:\n"
    "        def consume(self, private_nested_parameter: Concrete): pass\n"
    "class Outer:\n"
    "    class _Inner:\n"
    "        def consume(self, hidden_inner_parameter: Concrete): pass\n"
    "    class Inner:\n"
    "        def consume(self, public_nested_parameter: Reader): pass\n"
)


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_decorated_methods_and_private_class_visibility(
    tmp_path: Path, mounted: bool, columnar: bool
) -> None:
    rules = _protocol_binding_rules(_METHOD_VISIBILITY_CASES)
    raw = _contract()
    raw["rules"] = rules
    files = {
        "sample/__init__.py": "",
        "sample/core.py": _METHOD_VISIBILITY_SOURCE,
        "sample/ports.py": "def replacement(*args): pass\n",
    }
    if mounted:
        files["inside.json"] = json.dumps(
            {
                "schema_version": "3.9.0",
                "components": [_component("all", ["sample"])],
                "rules": rules,
            }
        )
        raw["components"] = [_component("outer", ["sample"], inside="inside.json")]
        raw["rules"] = []
    result = _observe_tree(tmp_path, files, raw)
    assert not result.diagnostics and result.observation is not None
    assessments = rule_assessments(
        result.observation, undecided_by_rule=unknown_positions_by_rule(result.observation)
    )
    observed = {row.id.rsplit(":", 1)[-1]: row.status.value for row in assessments}
    assert observed == {
        f"APP-{name.upper()}-DECLARATIONS": status
        for name, status in _METHOD_VISIBILITY_CASES.items()
    }
    payload = observation_payload(result.observation)
    saved = tmp_path / "method-visibility.json"
    saved.write_bytes(canonical_report_bytes(payload) if columnar else json.dumps(payload).encode())
    replay = run_saved_report(saved)
    assert not replay.diagnostics
    assert replay.rule_assessments == assessments


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_public_parameter_selectors_follow_all_enclosing_class_visibility(
    tmp_path: Path, mounted: bool, columnar: bool
) -> None:
    rules = _protocol_binding_rules(_PUBLIC_CLASS_CASES)
    raw = _contract()
    raw["rules"] = rules
    files = {
        "sample/__init__.py": "",
        "sample/core.py": _PUBLIC_CLASS_SOURCE,
        "sample/ports.py": "",
    }
    if mounted:
        files["inside.json"] = json.dumps(
            {
                "schema_version": "3.9.0",
                "components": [_component("all", ["sample"])],
                "rules": rules,
            }
        )
        raw["components"] = [_component("outer", ["sample"], inside="inside.json")]
        raw["rules"] = []
    result = _observe_tree(tmp_path, files, raw)
    assert not result.diagnostics and result.observation is not None
    assessments = rule_assessments(
        result.observation, undecided_by_rule=unknown_positions_by_rule(result.observation)
    )
    observed = {row.id.rsplit(":", 1)[-1]: row.status.value for row in assessments}
    assert observed == {
        f"APP-{name.upper()}-DECLARATIONS": status for name, status in _PUBLIC_CLASS_CASES.items()
    }
    payload = observation_payload(result.observation)
    saved = tmp_path / "public-class-visibility.json"
    saved.write_bytes(canonical_report_bytes(payload) if columnar else json.dumps(payload).encode())
    replay = run_saved_report(saved)
    assert not replay.diagnostics
    assert replay.rule_assessments == assessments


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_public_member_selectors_follow_enclosing_class_visibility(
    tmp_path: Path, mounted: bool, columnar: bool
) -> None:
    selectors = (
        ("public_member", "reader", "public", "PASS"),
        ("nested_private_owner", "nested_reader", "public", "PASS"),
        ("private_only", "hidden", "public", "UNKNOWN"),
        ("all_private", "hidden", "all", "FAIL"),
    )
    rules = [
        {
            "id": f"APP-{rule_id.upper()}-DECLARATIONS",
            "kind": "protocol_declarations",
            "source": "sample.core",
            "protocol": "sample.core.Reader",
            "selectors": [{"role": "member", "name": name, "visibility": visibility}],
            "rationale": "Selected members use the canonical Reader port.",
            "provenance": ["docs/architecture/sample.md"],
            "decided_by": "architect",
        }
        for rule_id, name, visibility, _ in selectors
    ]
    raw = _contract()
    raw["rules"] = rules
    files = {
        "sample/__init__.py": "",
        "sample/core.py": (
            "from typing import Protocol\n"
            "class Reader(Protocol): ...\nclass Concrete: ...\n"
            "class _Internal:\n    reader: Concrete\n    hidden: Concrete\n"
            "class Outer:\n    class _Inner:\n        nested_reader: Concrete\n"
            "class Public:\n    reader: Reader\n    nested_reader: Reader\n"
        ),
    }
    if mounted:
        files["inside.json"] = json.dumps(
            {
                "schema_version": "3.9.0",
                "components": [_component("all", ["sample"])],
                "rules": rules,
            }
        )
        raw["components"] = [_component("outer", ["sample"], inside="inside.json")]
        raw["rules"] = []
    result = _observe_tree(tmp_path, files, raw)
    assert not result.diagnostics and result.observation is not None
    assessments = rule_assessments(
        result.observation, undecided_by_rule=unknown_positions_by_rule(result.observation)
    )
    observed = {row.id.rsplit(":", 1)[-1]: row.status.value for row in assessments}
    assert observed == {
        f"APP-{rule_id.upper()}-DECLARATIONS": status for rule_id, _, _, status in selectors
    }
    payload = observation_payload(result.observation)
    saved = tmp_path / "public-member-visibility.json"
    saved.write_bytes(canonical_report_bytes(payload) if columnar else json.dumps(payload).encode())
    replay = run_saved_report(saved)
    assert not replay.diagnostics
    assert replay.rule_assessments == assessments


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_private_parameter_selector_still_includes_private_class_declarations(
    tmp_path: Path, mounted: bool, columnar: bool
) -> None:
    rules = _protocol_binding_rules({"private_parameter": "FAIL"})
    rules[0]["selectors"] = [
        {"role": "parameter", "name": "private_parameter", "visibility": "all"}
    ]
    raw = _contract()
    raw["rules"] = rules
    files = {
        "sample/__init__.py": "",
        "sample/core.py": _PUBLIC_CLASS_SOURCE,
        "sample/ports.py": "",
    }
    if mounted:
        files["inside.json"] = json.dumps(
            {
                "schema_version": "3.9.0",
                "components": [_component("all", ["sample"])],
                "rules": rules,
            }
        )
        raw["components"] = [_component("outer", ["sample"], inside="inside.json")]
        raw["rules"] = []
    result = _observe_tree(tmp_path, files, raw)
    assert not result.diagnostics and result.observation is not None
    assessments = rule_assessments(
        result.observation, undecided_by_rule=unknown_positions_by_rule(result.observation)
    )
    assert [row.status.value for row in assessments] == ["FAIL"]
    payload = observation_payload(result.observation)
    saved = tmp_path / "private-selector.json"
    saved.write_bytes(canonical_report_bytes(payload) if columnar else json.dumps(payload).encode())
    replay = run_saved_report(saved)
    assert not replay.diagnostics
    assert replay.rule_assessments == assessments


_ORDERED_CLASS_BINDING_CASES = {
    "variadic_shadow": "UNKNOWN",
    "keyword_variadic_shadow": "UNKNOWN",
    "stale_member": "UNKNOWN",
    "replaced_method": "UNKNOWN",
    "good_parameter": "PASS",
    "good_member": "PASS",
    "concrete_member": "FAIL",
}


def _ordered_class_binding_rules() -> list[dict[str, object]]:
    rules = [
        {
            "id": f"APP-{name.upper()}-DECLARATIONS",
            "kind": "protocol_declarations",
            "source": "sample.core",
            "protocol": "sample.core.Reader",
            "selectors": [
                {
                    "role": (
                        "member"
                        if name in {"stale_member", "good_member", "concrete_member"}
                        else "parameter"
                    ),
                    "name": {
                        "variadic_shadow": "client",
                        "keyword_variadic_shadow": "kwargs",
                        "stale_member": "reader",
                        "replaced_method": "client",
                        "good_parameter": "trusted",
                        "good_member": "good_reader",
                        "concrete_member": "bad_reader",
                    }[name],
                    "visibility": "all",
                }
            ],
            "rationale": "Selected positions use the canonical Reader port.",
            "provenance": ["docs/architecture/sample.md"],
            "decided_by": "architect",
        }
        for name in _ORDERED_CLASS_BINDING_CASES
    ]
    return rules


def _ordered_class_binding_fixture(
    tmp_path: Path, rules: list[dict[str, object]], mounted: bool
) -> tuple[dict[str, object], dict[str, str]]:
    raw = _contract()
    raw["rules"] = rules
    files = {
        "sample/__init__.py": "",
        "sample/core.py": (
            "from typing import Protocol\n"
            "class Reader(Protocol): ...\n"
            "class Concrete: ...\n"
            "class VariadicService:\n"
            "    Reader = Concrete\n"
            "    def consume(self, *client: Reader, **kwargs: Reader): pass\n"
            "class MemberService:\n"
            "    reader: Reader\n"
            "    class reader: ...\n"
            "class ReplacedMethodService:\n"
            "    def consume(self, client: Reader): pass\n"
            "    class consume: ...\n"
            "class GoodService:\n"
            "    good_reader: Reader\n"
            "    def consume(self, trusted: Reader): pass\n"
            "class ConcreteService:\n"
            "    bad_reader: Concrete\n"
        ),
    }
    if mounted:
        files["inside.json"] = json.dumps(
            {
                "schema_version": "3.9.0",
                "components": [_component("all", ["sample"])],
                "rules": rules,
            }
        )
        raw["components"] = [_component("outer", ["sample"], inside="inside.json")]
        raw["rules"] = []
    return raw, files


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_protocol_selector_binding_checks_variadic_and_nested_class_bindings(
    tmp_path: Path, mounted: bool, columnar: bool
) -> None:
    rules = _ordered_class_binding_rules()
    raw, files = _ordered_class_binding_fixture(tmp_path, rules, mounted)
    result = _observe_tree(tmp_path, files, raw)
    assert not result.diagnostics and result.observation is not None
    assessments = rule_assessments(
        result.observation, undecided_by_rule=unknown_positions_by_rule(result.observation)
    )
    observed = {row.id.rsplit(":", 1)[-1]: row.status.value for row in assessments}
    expected = {
        f"APP-{name.upper()}-DECLARATIONS": status
        for name, status in _ORDERED_CLASS_BINDING_CASES.items()
    }
    assert observed == expected
    [variadic_method] = [
        symbol
        for symbol in result.observation.records("symbols") or ()
        if symbol.kind == "method"
        and symbol.data.get("qualified_name") == "sample.core.VariadicService.consume"
    ]
    uncertainty_keys = {
        key for key, _ in variadic_method.data.get("annotation_binding_uncertainties", ()).entries
    }
    assert {"*client", "**kwargs"} <= uncertainty_keys
    payload = observation_payload(result.observation)
    saved = tmp_path / "ordered-class-bindings.json"
    saved.write_bytes(canonical_report_bytes(payload) if columnar else json.dumps(payload).encode())
    replay = run_saved_report(saved)
    assert not replay.diagnostics
    assert replay.rule_assessments == assessments


def test_function_declaration_binding_requires_signature_decorator_proof() -> None:
    from archkeel.check.evaluation.protocol_declarations import _declaration_binding_proven

    function = {
        "kind": "function",
        "data": {"source_binding_unique": True, "signature_decorators_proven": False},
    }
    assert not _declaration_binding_proven(function)


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


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize(
    ("role", "body", "expected"),
    [
        (
            "parameter",
            "class Holder:\n    Reader = Concrete\n    def consume(self, client: Reader): pass\n",
            "UNKNOWN",
        ),
        (
            "member",
            "class Holder:\n    Reader = Concrete\n    reader: Reader\n",
            "UNKNOWN",
        ),
        (
            "member",
            "class Holder:\n    reader: Reader\n    if ENABLED:\n        reader = Concrete()\n",
            "UNKNOWN",
        ),
        ("parameter", "def consume(client: Reader): pass\n", "PASS"),
        ("member", "class Holder:\n    reader: Reader\n", "PASS"),
    ],
)
def test_uncertain_class_annotation_bindings_are_not_proven_on_saved_replay(
    tmp_path: Path,
    mounted: bool,
    columnar: bool,
    role: str,
    body: str,
    expected: str,
) -> None:
    selector_name = "client" if role == "parameter" else "reader"
    rule = {
        "id": "APP-READER-DECLARATIONS",
        "kind": "protocol_declarations",
        "source": "sample.core",
        "protocol": "sample.core.Reader",
        "selectors": [{"role": role, "name": selector_name, "visibility": "all"}],
        "rationale": "Selected declarations use the Reader port.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    source = (
        f"from typing import Protocol\nclass Reader(Protocol): ...\nclass Concrete: ...\n{body}"
    )
    files = {
        "sample/__init__.py": "",
        "sample/core/__init__.py": source,
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

    result = _observe_tree(tmp_path, files, root_contract)
    assert result.observation is not None
    rows = rule_assessments(
        result.observation,
        undecided_by_rule=unknown_positions_by_rule(result.observation),
    )
    [row] = [item for item in rows if item.kind == "protocol_declarations"]
    assert row.status.value == expected
    payload = observation_payload(result.observation)
    saved = tmp_path / "class-binding.json"
    saved.write_text(json.dumps(encode_canonical_model(payload) if columnar else payload))
    [replayed] = [
        item
        for item in (run_saved_report(saved).rule_assessments or ())
        if item.kind == "protocol_declarations"
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
