# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #229: exact native payload decisions retain opaque neighboring controls."""

import json
import sys
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
            "    def __init__(self, ctx: object | None) -> None: pass\n"
            "    def mask(self, mask: object) -> object: return mask\n"
            "    def other(self, value: object) -> object: return value\n"
            if index == 0
            else ""
        )
        parameter = "value: object, mask: object" if index == 0 else "value: object"
        returns = "object | None" if index == 2 else "object"
        classes.append(
            f"class {name}:\n{controls}"
            f"    def convert(self, {parameter}) -> {returns}: return value\n"
        )
        for position in ("value", "return") if index < 3 else ("value",):
            allowances.append(
                {
                    **_ALLOWANCE,
                    "qualified_name": f"sample.app.impl.{name}.convert",
                    "position": position,
                    "annotation": returns if position == "return" else "object",
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


def test_exact_nullable_native_return_keeps_neighboring_controls_forbidden(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "class Converter:\n"
            "    def __init__(self, ctx: object | None) -> None: self.ctx = ctx\n"
            "    def convert(self, value: object, mask: object | None) -> object | None:\n"
            "        return value\n"
            "    def other(self, value: str) -> object | None: return value\n"
        ),
        declared=("sample.app.impl:Converter",),
        allowed_positions=({**_ALLOWANCE, "position": "return", "annotation": "object | None"},),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert {
        (item.data.get("qualified_name"), item.data.get("position")) for item in violations
    } == {
        ("sample.app.impl.Converter.__init__", "ctx"),
        ("sample.app.impl.Converter.convert", "value"),
        ("sample.app.impl.Converter.convert", "mask"),
        ("sample.app.impl.Converter.other", "return"),
    }
    [fact] = [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]
    assert fact.data.get("annotation") == "object | None"
    assert fact.data.get("accepted_opacity") is True
    assert fact.provenance == ("docs/architecture/sample.md",)
    assert "type closure remains unproven" in fact.title


@pytest.mark.parametrize("source", ["object = Missing\n", "class Hidden: pass\n"])
def test_nullable_native_allowance_preserves_unproven_object_bindings(
    tmp_path: Path, source: str
) -> None:
    binding = "    object = Hidden\n" if "class Hidden" in source else ""
    _write_app(
        tmp_path,
        implementation=source
        + "class Converter:\n"
        + binding
        + "    def convert(self, value: str) -> object | None: return value\n",
        declared=("sample.app.impl:Converter",),
        allowed_positions=({**_ALLOWANCE, "position": "return", "annotation": "object | None"},),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert any(
        item.kind == "boundary_type_position"
        for item in result.observation.records("unknowns") or ()
    )
    assert not any(
        item.kind == "boundary_type_allowance"
        for item in result.observation.records("typing_signals") or ()
    )


@pytest.mark.parametrize("annotation", ["object | str", "object | Missing", "list[object]"])
def test_native_allowance_does_not_accept_other_exact_opaque_shapes(
    tmp_path: Path, annotation: str
) -> None:
    _write_app(
        tmp_path,
        implementation=(
            f"class Converter:\n    def convert(self, value: str) -> {annotation}: return value\n"
        ),
        declared=("sample.app.impl:Converter",),
        allowed_positions=({**_ALLOWANCE, "position": "return", "annotation": annotation},),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation)
    assert not any(
        item.kind == "boundary_type_allowance"
        for item in result.observation.records("typing_signals") or ()
    )
    if annotation == "object | Missing":
        assert any(
            item.kind == "boundary_type_position"
            for item in result.observation.records("unknowns") or ()
        )


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


@pytest.mark.parametrize(
    "binding",
    [
        "object = Hidden",
        "object = Missing",
        "class object: pass",
        "from decimal import Decimal as object",
        "def object(self) -> None: pass",
        "if True: object = Hidden",
        "object = Hidden; del object",
    ],
)
@pytest.mark.parametrize("deferred", [False, True])
def test_class_local_object_bindings_cannot_accept_native_opacity(
    tmp_path: Path, binding: str, deferred: bool
) -> None:
    implementation = (
        ("from __future__ import annotations\n" if deferred else "")
        + "class Hidden: pass\nclass Converter:\n    "
        + binding
        + "\n    def convert(self, value: object) -> str: return ''\n"
    )
    _write_app(
        tmp_path,
        implementation=implementation,
        declared=("sample.app.impl:Converter",),
        allowed_positions=(_ALLOWANCE,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [unknown] = [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_position"
    ]
    assert unknown.data.get("position") == "value"
    assert unknown.data.get("annotation_bindings") == ("object",)
    assert unknown.data.get("annotation_scope") == "sample.app.impl.Converter"
    assert not [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]


def test_shadowed_object_in_union_keeps_a_known_broad_mapping_neighbor(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "class Hidden: pass\nclass Converter:\n    object = Hidden\n"
            "    def convert(self, value: object | dict[str, str]) -> str: return ''\n"
        ),
        declared=("sample.app.impl:Converter",),
        allowed_positions=(_ALLOWANCE,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.data.get("nested_annotation") == "dict[str, str]"
    assert any(
        item.kind == "boundary_type_position"
        for item in result.observation.records("unknowns") or ()
    )


@pytest.mark.parametrize("deferred", [False, True])
def test_a_later_class_binding_only_blocks_deferred_annotations(
    tmp_path: Path, deferred: bool
) -> None:
    source = (
        ("from __future__ import annotations\n" if deferred else "")
        + "class Hidden: pass\nclass Converter:\n"
        "    def convert(self, value: object) -> str: return ''\n    object = Hidden\n"
    )
    _write_app(
        tmp_path,
        implementation=source,
        declared=("sample.app.impl:Converter",),
        allowed_positions=(_ALLOWANCE,),
    )
    namespace: dict[str, object] = {}
    exec(source, namespace)
    if not deferred:
        converter = namespace["Converter"]
        assert isinstance(converter, type)
        assert converter.convert.__annotations__["value"] is object

    result = _observe(tmp_path)

    assert result.observation is not None
    facts = [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]
    assert len(facts) == (0 if deferred else 1)
    assert (
        any(
            item.kind == "boundary_type_position"
            for item in result.observation.records("unknowns") or ()
        )
        is deferred
    )


def test_class_field_scope_uncertainty_is_a_source_fact_for_any_name(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "class Hidden: pass\nclass Payload:\n    datetime = Hidden\n    now: datetime\n"
        ),
        declared=("sample.app.impl:Payload",),
    )
    result = _observe(tmp_path)

    assert result.observation is not None
    [payload] = [
        item
        for item in result.observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.impl.Payload"
    ]
    uncertainties = payload.data.get("annotation_binding_uncertainties")
    assert uncertainties is not None
    assert uncertainties.get("now") == ("datetime",)
    assert payload.data.get("annotation_scope") == "sample.app.impl.Payload"


@pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 695 requires Python 3.12")
@pytest.mark.parametrize("generic", ["class", "method"])
def test_generic_object_parameter_cannot_be_a_native_builtin_payload(
    tmp_path: Path, generic: str
) -> None:
    source = (
        "class Converter[object]:\n    def convert(self, value: object) -> str: return ''\n"
        if generic == "class"
        else "class Converter:\n    def convert[object](self, value: object) -> str: return ''\n"
    )
    _write_app(
        tmp_path,
        implementation=source,
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


def test_class_local_module_alias_is_recorded_at_its_annotation_head(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "import datetime as clock\nclass Hidden: datetime = str\nclass Converter:\n"
            "    clock = Hidden\n"
            "    def convert(self, value: clock.datetime) -> str: return ''\n"
        ),
        declared=("sample.app.impl:Converter",),
        allowed_positions=(_ALLOWANCE,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [unknown] = [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_position"
    ]
    assert unknown.data.get("annotation_bindings") == ("clock",)
    assert unknown.data.get("annotation_scope") == "sample.app.impl.Converter"


def test_model_field_shadow_keeps_a_known_broad_neighbor(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "class Hidden: pass\nclass Payload:\n    object = Hidden\n"
            "    value: object\n    rows: dict[str, str]\n"
            "class Converter:\n    def convert(self, value: Payload) -> str: return ''\n"
        ),
        declared=("sample.app.impl:Converter", "sample.app.impl:Payload"),
        allowed_positions=(_ALLOWANCE,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.data.get("path") == "value.rows"
    assert any(
        item.kind == "boundary_type_position" and item.data.get("path") == "value.value"
        for item in result.observation.records("unknowns") or ()
    )


@pytest.mark.parametrize("shadow_in_base", [False, True])
def test_inherited_annotation_uses_its_declaring_base_scope(
    tmp_path: Path, shadow_in_base: bool
) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "from typing import Generic, TypeVar\nT = TypeVar('T')\n"
            "class Payload: pass\nclass Hidden: pass\nclass Base(Generic[T]):\n"
            + ("    object = Hidden\n" if shadow_in_base else "")
            + "    def convert(self, value: object) -> T: return value\n"
            "class Converter(Base[Payload]):\n"
            + ("    pass\n" if shadow_in_base else "    object = Hidden\n")
        ),
        declared=("sample.app.impl:Converter", "sample.app.impl:Payload"),
        allowed_positions=(_ALLOWANCE,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    facts = [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]
    assert len(facts) == (0 if shadow_in_base else 1)
    if shadow_in_base:
        [unknown] = [
            item
            for item in result.observation.records("unknowns") or ()
            if item.kind == "boundary_type_position" and item.data.get("position") == "value"
        ]
        assert unknown.data.get("annotation_scope") == "sample.app.impl.Base"
        assert unknown.data.get("annotation_bindings") == ("object",)


@pytest.mark.parametrize("annotation", ["Payload", "tuple[object, Payload]"])
def test_class_scope_uncertainty_does_not_hide_an_independently_declared_dto_field(
    tmp_path: Path, annotation: str
) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "class Payload:\n    content: object\nclass Hidden: pass\nclass Converter:\n"
            "    object = Hidden\n"
            f"    def convert(self, value: {annotation}) -> str: return ''\n"
        ),
        declared=("sample.app.impl:Converter", "sample.app.impl:Payload"),
        allowed_positions=(_ALLOWANCE,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.data.get("path") == "value.content"
    assert any(
        item.kind == "boundary_type_position"
        for item in result.observation.records("unknowns") or ()
    ) is (annotation != "Payload")


def test_a_reached_dto_applies_its_own_class_scope_uncertainty(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "class Hidden: pass\nclass Payload:\n    object = Hidden\n    content: object\n"
            "class Converter:\n"
            "    def convert(self, value: tuple[object, Payload]) -> str: return ''\n"
        ),
        declared=("sample.app.impl:Converter", "sample.app.impl:Payload"),
        allowed_positions=(_ALLOWANCE,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.data.get("path") is None
    assert any(
        item.kind == "boundary_type_position" and item.data.get("path") == "value.content"
        for item in result.observation.records("unknowns") or ()
    )


def test_class_scope_uncertainty_does_not_hide_a_module_alias_body(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "from typing import TypeAlias\nPayload: TypeAlias = object\n"
            "class Hidden: pass\nclass Converter:\n    object = Hidden\n"
            "    def convert(self, value: tuple[object, Payload]) -> str: return ''\n"
        ),
        declared=("sample.app.impl:Converter",),
        allowed_positions=(_ALLOWANCE,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert len(trace_valid_violations(result.observation)) == 1
    assert any(
        item.kind == "boundary_type_position"
        for item in result.observation.records("unknowns") or ()
    )
