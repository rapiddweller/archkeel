# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #229: exact native payload decisions retain opaque neighboring controls."""

import json
from pathlib import Path

import pytest
from test_analyzer import _observe
from test_boundary_types_nested_dtos import _write_app
from test_contract_model import VALIDATOR

from archkeel.ir.codec import parse_contract
from archkeel.ir.trace import trace_valid_violations

_ALLOWANCE = {
    "qualified_name": "sample.app.impl.Converter.convert",
    "position": "value",
    "field_path": "",
    "annotation": "object",
}


def _native_fixture(root: Path, *, allowed: bool) -> None:
    classes = []
    allowances = []
    for index in range(15):
        name = f"Converter{index}"
        controls = (
            "    def __init__(self, ctx: object) -> None: pass\n"
            "    def mask(self, mask: object) -> object: return mask\n"
            "    def other(self, value: object) -> object: return value\n"
            if index == 0
            else ""
        )
        parameter = "value: object, mask: object" if index == 0 else "value: object"
        classes.append(
            f"class {name}:\n{controls}    def convert(self, {parameter}) -> object: return value\n"
        )
        for position in ("value", "return") if index < 3 else ("value",):
            allowances.append(
                {
                    **_ALLOWANCE,
                    "qualified_name": f"sample.app.impl.{name}.convert",
                    "position": position,
                }
            )
    _write_app(
        root,
        implementation="\n".join(classes),
        declared=tuple(f"sample.app.impl:Converter{index}" for index in range(15)),
        allowed_positions=tuple(allowances) if allowed else (),
    )


def test_eighteen_native_payload_positions_leave_eighteen_neighbors_forbidden(
    tmp_path: Path,
) -> None:
    _native_fixture(tmp_path, allowed=True)

    result = _observe(tmp_path)

    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert len(violations) == 18
    actual = {(item.data.get("qualified_name"), item.data.get("position")) for item in violations}
    assert ("sample.app.impl.Converter0.__init__", "ctx") in actual
    assert ("sample.app.impl.Converter0.convert", "mask") in actual
    assert ("sample.app.impl.Converter0.mask", "mask") in actual
    assert ("sample.app.impl.Converter0.other", "value") in actual
    assert ("sample.app.impl.Converter3.convert", "return") in actual
    facts = [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]
    assert len(facts) == 18
    assert all(item.data.get("accepted_opacity") is True for item in facts)
    assert all("type closure remains unproven" in item.title for item in facts)
    assert all(f"at {item.data.get('position')}" in item.title for item in facts)
    assert all(item.provenance == ("docs/architecture/sample.md",) for item in facts)
    assert all(item.rule_ids == ("APP-TYPES-NOT-DICT",) and item.evidence_ids for item in facts)


def test_native_payloads_remain_broad_without_a_decision(tmp_path: Path) -> None:
    _native_fixture(tmp_path, allowed=False)

    result = _observe(tmp_path)

    assert result.observation is not None
    assert len(trace_valid_violations(result.observation)) == 36


@pytest.mark.parametrize("annotation", ["object | None", "list[object]", "dict[str, object]"])
def test_changed_signature_annotation_is_not_the_exact_native_payload(
    tmp_path: Path, annotation: str
) -> None:
    _write_app(
        tmp_path,
        implementation=(
            f"class Converter:\n    def convert(self, value: {annotation}) -> str: return ''\n"
        ),
        declared=("sample.app.impl:Converter",),
        allowed_positions=(_ALLOWANCE,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation)
    assert not [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]


def test_accepting_opacity_preserves_other_unknown_positions(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "class Converter:\n"
            "    def convert(self, value: object, unknown: Missing) -> object: return value\n"
        ),
        declared=("sample.app.impl:Converter",),
        allowed_positions=(_ALLOWANCE,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.data.get("position") == "return"
    assert any(
        item.data.get("position") == "unknown"
        for item in result.observation.records("unknowns") or ()
    )


@pytest.mark.parametrize(
    "change",
    [
        {"qualified_name": "sample.app.impl.Converter.other"},
        {"qualified_name": "sample.app.impl.Converter.*"},
        {"position": "return"},
        {"position": "*"},
        {"field_path": "payload"},
        {"annotation": "str"},
        {"annotation": "object | None"},
    ],
)
def test_native_payload_selector_changes_leave_the_input_forbidden(
    tmp_path: Path, change: dict[str, str]
) -> None:
    _write_app(
        tmp_path,
        implementation="class Converter:\n    def convert(self, value: object) -> str: return ''\n",
        declared=("sample.app.impl:Converter",),
        allowed_positions=({**_ALLOWANCE, **change},),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.data.get("position") == "value"
    assert not [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]


@pytest.mark.parametrize(
    "source",
    [
        "import types as object\n",
        "def object() -> None: pass\n",
        "object = Missing\n",
    ],
)
def test_native_allowance_does_not_turn_unresolved_object_bindings_into_pass(
    tmp_path: Path, source: str
) -> None:
    _write_app(
        tmp_path,
        implementation=source
        + "class Converter:\n    def convert(self, value: object) -> str: return ''\n",
        declared=("sample.app.impl:Converter",),
        allowed_positions=(_ALLOWANCE,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert any(
        item.kind == "boundary_type_position"
        for item in result.observation.records("unknowns") or ()
    )
    assert not [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]


@pytest.mark.parametrize("field_path", ["", "payload", None, 1, " "])
def test_native_decision_schema_and_parser_keep_path_validation(field_path: object) -> None:
    from test_boundary_type_allowances import _contract

    raw = _contract(allowance={**_ALLOWANCE, "field_path": field_path})
    if field_path in ("", "payload"):
        assert not list(VALIDATOR.iter_errors(raw))
        parse_contract(raw)
    else:
        assert list(VALIDATOR.iter_errors(raw))
        with pytest.raises(ValueError):
            parse_contract(raw)


def test_native_decision_cannot_hide_unknown_fields(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation="class Converter:\n    def convert(self, value: object) -> str: return ''\n",
        declared=("sample.app.impl:Converter",),
        allowed_positions=({**_ALLOWANCE, "approved": "yes"},),
    )
    raw = json.loads((tmp_path / "contract.json").read_text())
    assert list(VALIDATOR.iter_errors(raw))
    with pytest.raises(ValueError, match="fields mismatch"):
        parse_contract(raw)
