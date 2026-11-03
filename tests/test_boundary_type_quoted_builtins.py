# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Quoted builtin types need complete provider proof before policy evaluation."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_analyzer import _observe
from test_boundary_types_nested_dtos import _write_app

from archkeel.ir.decisions import rule_assessments
from archkeel.ir.trace import trace_valid_violations


def _signature(
    root: Path, annotation: str, *, facade: bool = False, prefix: str = "", body: str = ""
):
    owner = "sample.app" if facade else "sample.app.impl"
    _write_app(
        root,
        implementation=prefix
        + f"class Session:\n    def dispatch(self, value: {annotation}) -> None: pass\n"
        + body,
        declared=(f"{owner}:Session",),
    )
    if facade:
        (root / "sample/app/__init__.py").write_text(
            "from .impl import Session\n__all__ = ['Session']\n"
        )
    result = _observe(root)
    assert result.observation is not None and result.diagnostics == ()
    return result.observation


def _assert_verdict(
    observation, annotation: str, expected: str, *, reason: str = "forward_reference"
) -> None:
    positions = [
        item
        for item in observation.records("unknowns") or ()
        if item.kind == "boundary_type_position"
    ]
    target_positions = [item for item in positions if item.data.get("position") == "value"]
    violations = list(trace_valid_violations(observation))
    if expected == "UNKNOWN":
        assert len(target_positions) == 1
        assert target_positions[0].data.get("annotation") == annotation
        assert target_positions[0].data.get("reason") == reason
    else:
        assert positions == []
    assert len(violations) == (1 if expected == "FAIL" else 0)
    if violations:
        assert violations[0].data.get("annotation") == annotation
    [assessment] = rule_assessments(
        observation, undecided_by_rule={"APP-TYPES-NOT-DICT": len(positions)}
    )
    assert assessment.status == expected
    assert assessment.evaluation_proven


@pytest.mark.parametrize("facade", [False, True], ids=["direct", "facade"])
@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        ("str | None", "PASS"),
        ("int", "PASS"),
        ('"None"', "PASS"),
        ('"int"', "UNKNOWN"),
        ('"str | None"', "PASS"),
        ("object", "FAIL"),
        ('"object"', "FAIL"),
        ('"Missing"', "UNKNOWN"),
    ],
)
def test_quoted_builtin_decision_preserves_original_position(
    tmp_path: Path, annotation: str, expected: str, facade: bool
) -> None:
    observation = _signature(tmp_path, annotation, facade=facade)
    # Python's collector canonicalizes quotes with ast.unparse, while retaining their layer.
    canonical = "'" + annotation[1:-1] + "'" if annotation.startswith('"') else annotation
    _assert_verdict(observation, canonical, expected)


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        ("'str | None'", "PASS"),
        ('"""str | None"""', "PASS"),
        ('"  str | None  "', "PASS"),
        ('"object | None"', "FAIL"),
        ('"str | object"', "FAIL"),
        ('"str | Missing"', "UNKNOWN"),
        ('"object | Missing"', "UNKNOWN"),
        ('"len"', "UNKNOWN"),
        ('"str | len"', "UNKNOWN"),
        ('"str | int"', "UNKNOWN"),
        ('"object | int"', "UNKNOWN"),
        ('"str |"', "UNKNOWN"),
        ('"str()"', "UNKNOWN"),
        ('"list[str]"', "UNKNOWN"),
        ('"builtins.str"', "UNKNOWN"),
        ('"\\"str\\""', "UNKNOWN"),
    ],
)
def test_only_one_complete_builtin_type_tree_is_decided(
    tmp_path: Path, annotation: str, expected: str
) -> None:
    import ast

    observation = _signature(tmp_path, annotation)
    _assert_verdict(observation, ast.unparse(ast.parse(annotation, mode="eval").body), expected)


@pytest.mark.parametrize("facade", [False, True])
@pytest.mark.parametrize(
    ("prefix", "body"),
    [
        ("str = object\n", ""),
        ("class str: pass\n", ""),
        ("", "    str = object\n"),
        ("from builtins import str\nstr = object\n", ""),
        ("if condition:\n    from builtins import str\n", ""),
        ("from .provider import *\n", ""),
        ("from .provider import str\n", ""),
    ],
)
def test_quoted_names_keep_module_class_and_import_uncertainty(
    tmp_path: Path, facade: bool, prefix: str, body: str
) -> None:
    # A later class binding must remain deferred even without future annotations.
    observation = _signature(tmp_path, '"str | None"', facade=facade, prefix=prefix, body=body)
    _assert_verdict(
        observation,
        "'str | None'",
        "UNKNOWN",
        reason="ambiguous_facade"
        if facade and prefix == "from .provider import *\n"
        else "forward_reference",
    )


@pytest.mark.parametrize("annotation", ["str | None", '"str | None"'])
def test_quoted_builtin_import_preserves_existing_external_type_policy(
    tmp_path: Path, annotation: str
) -> None:
    observation = _signature(tmp_path, annotation, prefix="from builtins import str\n")
    canonical = "'str | None'" if annotation.startswith('"') else annotation
    _assert_verdict(observation, canonical, "UNKNOWN", reason="external_type")


def test_quoted_call_never_executes_source(tmp_path: Path) -> None:
    sentinel = tmp_path / "executed"
    expression = f"__import__('pathlib').Path({str(sentinel)!r}).touch()"
    observation = _signature(tmp_path, repr(expression))
    _assert_verdict(observation, repr(expression), "UNKNOWN")
    assert not sentinel.exists()


@pytest.mark.parametrize("collection_first", [False, True])
@pytest.mark.parametrize("type_annotation", ['"str"', 'list["str"]'])
def test_literal_argument_keeps_its_meaning_next_to_quoted_type(
    tmp_path: Path, collection_first: bool, type_annotation: str
) -> None:
    parameters = [f"value: {type_annotation}", 'label: Literal["str"]']
    if collection_first:
        parameters.reverse()
    _write_app(
        tmp_path,
        implementation="from typing import Literal\nclass Session:\n"
        + f"    def dispatch(self, {', '.join(parameters)}) -> None: pass\n",
        declared=("sample.app.impl:Session",),
    )
    result = _observe(tmp_path)
    assert result.observation is not None and result.diagnostics == ()
    _assert_verdict(result.observation, "", "PASS")


def test_literal_string_does_not_invent_class_binding_uncertainty(tmp_path: Path) -> None:
    observation = _signature(
        tmp_path, 'Literal["str"]', prefix="from typing import Literal\n", body="    str = object\n"
    )
    _assert_verdict(observation, "", "PASS")


@pytest.mark.requires_python(12)
def test_quoted_builtin_generic_parameter_stays_uncertain(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation='class Session[str]:\n    def dispatch(self, value: "str") -> None: pass\n',
        declared=("sample.app.impl:Session",),
    )
    result = _observe(tmp_path)
    assert result.observation is not None and result.diagnostics == ()
    _assert_verdict(result.observation, "'str'", "UNKNOWN")


@pytest.mark.parametrize("schema_version", ["2.1.0", "3.0.0"])
def test_decoding_cannot_widen_an_exact_native_map_allowance(
    tmp_path: Path, schema_version: str
) -> None:
    import json

    from test_boundary_type_opaque_map_values import _app

    _app(
        tmp_path,
        source='def validate_raw(values: dict[str, "object"]) -> None: pass\n',
        allowances=tuple(
            {
                "qualified_name": "sample.app.impl.validate_raw",
                "position": "values",
                "annotation": "dict[str, object]",
                **({"container_depth": 1} if nested else {}),
            }
            for nested in (False, True)
        ),
    )
    contract_path = tmp_path / "contract.json"
    contract = json.loads(contract_path.read_text())
    contract["schema_version"] = schema_version
    contract_path.write_text(json.dumps(contract))
    result = _observe(tmp_path)
    assert result.observation is not None and result.diagnostics == ()
    violations = list(trace_valid_violations(result.observation))
    assert violations
    assert all(item.data.get("annotation") == "dict[str, 'object']" for item in violations)
    assert not any(
        item.kind == "boundary_type_allowance"
        for item in result.observation.records("typing_signals") or ()
    )


def test_decoding_keeps_unrelated_canonical_findings_identical(tmp_path: Path) -> None:
    body = (
        "    def unrelated(self, counts: dict[str, int]) -> None: pass\n"
        "    def undecided(self, item: Missing) -> None: pass\n"
    )
    ordinary = _signature(tmp_path, "str | None", body=body)
    quoted = _signature(tmp_path, '"str | None"', body=body)

    def unrelated(observation):
        return tuple(
            item
            for item in (
                *trace_valid_violations(observation),
                *(observation.records("unknowns") or ()),
            )
            if str(item.data.get("qualified_name", "")).endswith((".unrelated", ".undecided"))
        )

    assert len(unrelated(ordinary)) == 2
    assert unrelated(ordinary) == unrelated(quoted)


@pytest.mark.parametrize("future", ["", "from __future__ import annotations\n"])
def test_class_binding_before_method_stays_uncertain(tmp_path: Path, future: str) -> None:
    _write_app(
        tmp_path,
        implementation=future
        + 'class Session:\n    str = object\n    def dispatch(self, value: "str") -> None: pass\n',
        declared=("sample.app.impl:Session",),
    )
    result = _observe(tmp_path)
    assert result.observation is not None and result.diagnostics == ()
    _assert_verdict(result.observation, "'str'", "UNKNOWN")


@pytest.mark.parametrize(
    ("prefix", "annotation"),
    [
        ("from typing import Mapping\n", '"Mapping"'),
        ("from datetime import datetime\n", '"datetime"'),
    ],
)
def test_existing_nonbuiltin_leaf_policies_cannot_bypass_quoted_proof(
    tmp_path: Path, prefix: str, annotation: str
) -> None:
    observation = _signature(tmp_path, annotation, prefix=prefix)
    _assert_verdict(observation, "'" + annotation[1:-1] + "'", "UNKNOWN")


@pytest.mark.parametrize(
    ("prefix", "annotation"),
    [
        ("from typing import Literal as L\n", 'L["str"]'),
        ("import typing as t\n", 't.Literal["str"]'),
    ],
)
def test_literal_provider_alias_does_not_turn_a_string_into_a_shadowed_type(
    tmp_path: Path, prefix: str, annotation: str
) -> None:
    observation = _signature(tmp_path, annotation, prefix=prefix, body="    str = object\n")
    _assert_verdict(observation, "", "PASS")
    [method] = [
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.impl.Session.dispatch"
    ]
    assert method.data.get("annotation_binding_uncertainties", {}).get("value") is None


@pytest.mark.parametrize("alias", [False, True])
@pytest.mark.parametrize("later", [False, True])
@pytest.mark.parametrize("values", ["READY", '"str", READY'])
def test_literal_value_names_keep_deferred_class_binding_uncertainty(
    tmp_path: Path, alias: bool, later: bool, values: str
) -> None:
    head = "L" if alias else "Literal"
    annotation = f"{head}[{values}]"
    method = f"    def dispatch(self, value: {annotation}) -> None: pass\n"
    binding = "    READY = object()\n"
    _write_app(
        tmp_path,
        implementation="from __future__ import annotations\nfrom typing import Literal"
        + (" as L" if alias else "")
        + '\nREADY = "ready"\nclass Session:\n'
        + (method + binding if later else binding + method)
        + ("    str = object\n" if values != "READY" else ""),
        declared=("sample.app.impl:Session",),
    )
    result = _observe(tmp_path)
    assert result.observation is not None and result.diagnostics == ()
    _assert_verdict(
        result.observation, annotation.replace('"', "'"), "UNKNOWN", reason="ambiguous_binding"
    )
    [method_symbol] = [
        item
        for item in result.observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.impl.Session.dispatch"
    ]
    uncertainties = method_symbol.data.get("annotation_binding_uncertainties", {})
    assert uncertainties.get("value") == ("READY",)


@pytest.mark.parametrize(
    "prefix",
    [
        "class L: pass\n",
        "from typing import Literal as L\nL = list\n",
        "from .provider import L\n",
    ],
)
def test_unproven_literal_head_keeps_an_unknown_boundary(tmp_path: Path, prefix: str) -> None:
    observation = _signature(tmp_path, 'L["str"]', prefix=prefix, body="    str = object\n")
    [position] = [
        item
        for item in observation.records("unknowns") or ()
        if item.kind == "boundary_type_position" and item.data.get("position") == "value"
    ]
    assert position.data.get("annotation") == "L['str']"
    assert list(trace_valid_violations(observation)) == []


@pytest.mark.parametrize("facade", [False, True])
@pytest.mark.parametrize(
    ("prefix", "body"),
    [
        ("object = str\n", ""),
        ("class object: pass\n", ""),
        ("from builtins import object\nobject = str\n", ""),
        ("", "    object = str\n"),
    ],
)
def test_shadowed_object_cannot_gain_a_spelling_only_policy_failure(
    tmp_path: Path, facade: bool, prefix: str, body: str
) -> None:
    observation = _signature(tmp_path, '"object"', facade=facade, prefix=prefix, body=body)
    _assert_verdict(observation, "'object'", "UNKNOWN")
