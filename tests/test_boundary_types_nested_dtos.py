# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #132: decide nested DTO fields and preserve full paths for unresolved fields."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_analyzer import _component, _observe

from archkeel.ir.model import ObservationResult, RecordData
from archkeel.ir.trace import trace_valid_violations


def _write_app(
    root: Path,
    *,
    implementation: str,
    declared: tuple[str, ...],
    allowed_positions: tuple[dict[str, str], ...] = (),
) -> None:
    rule: dict[str, object] = {
        "id": "APP-TYPES-NOT-DICT",
        "kind": "boundary_types",
        "source": "sample.app",
        "rationale": "Keep the declared application boundary typed.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    if allowed_positions:
        rule["allowed_positions"] = list(allowed_positions)
    (root / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [_component("app", public=list(declared))],
                "rules": [rule],
            }
        )
    )
    (root / "sample/app").mkdir(parents=True, exist_ok=True)
    (root / "sample/app/__init__.py").write_text("")
    (root / "sample/app/impl.py").write_text(implementation)


def _type_unknowns(result: ObservationResult) -> list[object]:
    assert result.observation is not None
    return [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_position"
    ]


_SHADOWED_DICT_ALLOWANCE = {
    "qualified_name": "sample.app.impl.run",
    "position": "return",
    "field_path": "",
    "annotation": "dict[str, str]",
}


@pytest.mark.parametrize(
    ("implementation", "needs_type"),
    (
        (
            "class dict:\n    pass\n\ndef run() -> dict[str, str]:\n    return dict()\n",
            False,
        ),
        (
            "from .types import LocalDict as dict\n"
            "\n"
            "def run() -> dict[str, str]:\n"
            "    return dict()\n",
            True,
        ),
        (
            "from .types import LocalDict\n"
            "\n"
            "dict = LocalDict\n"
            "\n"
            "def run() -> dict[str, str]:\n"
            "    return dict()\n",
            True,
        ),
        (
            "import types as dict\n"
            "\n"
            "def run() -> dict[str, str]:\n"
            "    return dict.MappingProxyType({})\n",
            False,
        ),
        (
            "class LocalDict:\n"
            "    pass\n"
            "\n"
            "dict, other = LocalDict, None\n"
            "\n"
            "def run() -> dict[str, str]:\n"
            "    return dict()\n",
            False,
        ),
        (
            "class LocalDict:\n"
            "    pass\n"
            "\n"
            "if condition:\n"
            "    dict = LocalDict\n"
            "\n"
            "def run() -> dict[str, str]:\n"
            "    return dict()\n",
            False,
        ),
        (
            "if condition:\n    dict = 42\n\ndef run() -> dict[str, str]:\n    return {}\n",
            False,
        ),
        (
            "if (dict := object()):\n    pass\n\ndef run() -> dict[str, str]:\n    return {}\n",
            False,
        ),
        (
            "for dict in ():\n    pass\n\ndef run() -> dict[str, str]:\n    return {}\n",
            False,
        ),
        (
            "if condition:\n"
            "    class dict:\n"
            "        pass\n"
            "\n"
            "def run() -> dict[str, str]:\n"
            "    return {}\n",
            False,
        ),
        (
            "if condition:\n"
            "    def dict() -> None:\n"
            "        return None\n"
            "\n"
            "def run() -> dict[str, str]:\n"
            "    return {}\n",
            False,
        ),
        (
            "match subject:\n"
            '    case {"value": dict}:\n'
            "        pass\n"
            "\n"
            "def run() -> dict[str, str]:\n"
            "    return {}\n",
            False,
        ),
    ),
    ids=(
        "local-class",
        "imported-alias",
        "lowercase-rebound",
        "module-import",
        "tuple-rebound",
        "conditional-rebound",
        "conditional-constant",
        "walrus-rebound",
        "for-rebound",
        "conditional-class",
        "conditional-function",
        "match-capture",
    ),
)
@pytest.mark.parametrize("allowance", (False, True), ids=("unallowed", "exact-allowance"))
def test_shadowed_dict_does_not_match_a_builtin_allowance(
    tmp_path: Path, implementation: str, needs_type: bool, allowance: bool
) -> None:
    _write_app(
        tmp_path,
        implementation=implementation,
        declared=("sample.app.impl:run",),
        allowed_positions=(_SHADOWED_DICT_ALLOWANCE,) if allowance else (),
    )
    if needs_type:
        (tmp_path / "sample/app/types.py").write_text("class LocalDict:\n    pass\n")

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) or _type_unknowns(result)


@pytest.mark.parametrize("allowance", (False, True), ids=("unallowed", "exact-allowance"))
def test_builtin_dict_matches_only_its_exact_allowance(tmp_path: Path, allowance: bool) -> None:
    _write_app(
        tmp_path,
        implementation="def run() -> dict[str, str]:\n    return {}\n",
        declared=("sample.app.impl:run",),
        allowed_positions=(_SHADOWED_DICT_ALLOWANCE,) if allowance else (),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    if allowance:
        assert violations == ()
        assert _type_unknowns(result) == []
    else:
        [violation] = violations
        assert violation.data.get("annotation") == "dict[str, str]"


def test_builtin_named_module_imports_are_unknown(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "import types as dict\n"
            "import types as object\n"
            "import types as int\n"
            "\n"
            "def run(mapping: dict, value: object, number: int) -> str:\n"
            "    return str(mapping) + str(value) + str(number)\n"
        ),
        declared=("sample.app.impl:run",),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    assert len(_type_unknowns(result)) == 3


@pytest.mark.parametrize(
    "implementation",
    (
        "from builtins import dict\n\ndef run() -> dict[str, str]:\n    return {}\n",
        "from typing import Mapping as dict\n\ndef run() -> dict[str, str]:\n    return {}\n",
    ),
    ids=("builtins-dict", "typing-mapping-alias"),
)
def test_explicit_proven_mapping_imports_remain_broad(tmp_path: Path, implementation: str) -> None:
    _write_app(
        tmp_path,
        implementation=implementation,
        declared=("sample.app.impl:run",),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.data.get("annotation") == "dict[str, str]"


@pytest.mark.parametrize("allowance", (False, True), ids=("unallowed", "exact-allowance"))
def test_annotation_only_builtin_declaration_does_not_shadow_dict(
    tmp_path: Path, allowance: bool
) -> None:
    _write_app(
        tmp_path,
        implementation="dict: type\n\ndef run() -> dict[str, str]:\n    return {}\n",
        declared=("sample.app.impl:run",),
        allowed_positions=(_SHADOWED_DICT_ALLOWANCE,) if allowance else (),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    if allowance:
        assert trace_valid_violations(result.observation) == ()
        assert _type_unknowns(result) == []
    else:
        [violation] = trace_valid_violations(result.observation)
        assert violation.data.get("annotation") == "dict[str, str]"


def test_star_import_makes_builtin_mapping_unknown(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation="from .types import *\n\ndef run() -> dict[str, str]:\n    return {}\n",
        declared=("sample.app.impl:run",),
        allowed_positions=(_SHADOWED_DICT_ALLOWANCE,),
    )
    (tmp_path / "sample/app/types.py").write_text("value = 1\n")

    result = _observe(tmp_path)

    assert result.observation is not None
    assert any(
        item.data.get("binding") == "*" for item in result.observation.records("imports") or ()
    )
    assert trace_valid_violations(result.observation) == ()
    assert _type_unknowns(result)


def test_two_level_owned_dtos_are_decided(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "class Leaf:\n    value: int\n\n\n"
            "class Inner:\n    leaf: Leaf\n\n\n"
            "class Request:\n    inner: Inner\n\n\n"
            "def run(value: Request) -> str:\n    return ''\n"
        ),
        declared=(
            "sample.app.impl:Leaf",
            "sample.app.impl:Inner",
            "sample.app.impl:Request",
            "sample.app.impl:run",
        ),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    assert _type_unknowns(result) == []


def test_recursive_dto_terminates_and_repeated_scans_are_deterministic(
    tmp_path: Path,
) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "class Node:\n    parent: Node | None\n    payload: dict\n\n\n"
            "def run(value: Node) -> str:\n    return ''\n"
        ),
        declared=("sample.app.impl:Node", "sample.app.impl:run"),
    )

    first = _observe(tmp_path)
    repeated = _observe(tmp_path)

    assert first.observation is not None
    assert repeated.observation is not None
    first_violations = trace_valid_violations(first.observation)
    repeated_violations = trace_valid_violations(repeated.observation)
    assert [item.data.get("path") for item in first_violations] == ["value.payload"]
    assert first_violations == repeated_violations
    assert _type_unknowns(first) == []
    assert first.observation.records("unknowns") == repeated.observation.records("unknowns")


def test_shared_nested_dto_violations_keep_both_sibling_paths(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "class Inner:\n    metadata: dict\n\n\n"
            "class Request:\n    left: Inner\n    right: Inner\n\n\n"
            "def run(value: Request) -> str:\n    return ''\n"
        ),
        declared=("sample.app.impl:Inner", "sample.app.impl:Request", "sample.app.impl:run"),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert sorted(item.data.get("path") for item in violations) == [
        "value.left.metadata",
        "value.right.metadata",
    ]
    assert all(item.kind == "boundary_types" for item in violations)
    assert all(item.data.get("annotation") == "Request" for item in violations)
    assert all(item.data.get("nested_annotation") == "dict" for item in violations)


def test_undeclared_nested_dto_is_a_violation_with_the_full_field_path(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "class Hidden:\n    value: int\n\n\n"
            "class Inner:\n    hidden: Hidden\n\n\n"
            "class Request:\n    inner: Inner\n\n\n"
            "def run(value: Request) -> str:\n    return ''\n"
        ),
        declared=("sample.app.impl:Inner", "sample.app.impl:Request", "sample.app.impl:run"),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.kind == "boundary_types"
    assert violation.data.get("path") == "value.inner.hidden"
    assert violation.data.get("annotation") == "Request"
    assert violation.data.get("nested_annotation") == "Hidden"


def test_unsupported_nested_expression_stays_unknown_at_its_full_path(
    tmp_path: Path,
) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "class Inner:\n    payload: Custom[dict]\n\n\n"
            "class Request:\n    inner: Inner\n\n\n"
            "def run(value: Request) -> str:\n    return ''\n"
        ),
        declared=("sample.app.impl:Inner", "sample.app.impl:Request", "sample.app.impl:run"),
    )

    result = _observe(tmp_path)

    [unknown] = _type_unknowns(result)
    assert unknown.data.get("path") == "value.inner.payload"
    assert unknown.data.get("annotation") == "Request"
    assert unknown.data.get("nested_annotation") == "Custom[dict]"
    assert unknown.data.get("reason") == "generic"


def test_collection_and_union_nesting_decides_owned_dtos(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "class Inner:\n    value: int\n\n\n"
            "class Request:\n    items: list[Inner | None]\n\n\n"
            "def run(value: Request) -> str:\n    return ''\n"
        ),
        declared=("sample.app.impl:Inner", "sample.app.impl:Request", "sample.app.impl:run"),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    assert _type_unknowns(result) == []


def test_exact_nested_boundary_allowance_is_a_fact_and_leaves_bare_dict_unallowed(
    tmp_path: Path,
) -> None:
    allowance = {
        "qualified_name": "sample.app.impl.run",
        "position": "return",
        "field_path": "payload",
        "annotation": "dict[str, JsonValue]",
    }
    _write_app(
        tmp_path,
        implementation=(
            "class Request:\n    payload: dict[str, JsonValue]\n\n\n"
            "def run() -> Request:\n    return Request()\n"
        ),
        declared=("sample.app.impl:Request", "sample.app.impl:run"),
        allowed_positions=(allowance,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    [fact] = [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]
    assert fact.evidence_class.value == "FACT"
    assert fact.rule_ids == ("APP-TYPES-NOT-DICT",)
    assert fact.data.get("field_path") == "payload"
    assert fact.data.get("annotation") == "dict[str, JsonValue]"
    [rule] = [
        item
        for item in result.observation.records("declarations") or ()
        if item.id == "APP-TYPES-NOT-DICT"
    ]
    reported_allowances = rule.data.get("allowed_positions")
    assert isinstance(reported_allowances, tuple)
    [reported_allowance] = reported_allowances
    assert isinstance(reported_allowance, RecordData)
    assert all(reported_allowance.get(key) == value for key, value in allowance.items())

    _write_app(
        tmp_path,
        implementation=(
            "class Request:\n    payload: dict\n\n\ndef run() -> Request:\n    return Request()\n"
        ),
        declared=("sample.app.impl:Request", "sample.app.impl:run"),
        allowed_positions=(allowance,),
    )
    bare = _observe(tmp_path)
    assert bare.observation is not None
    assert any(
        item.kind == "boundary_types" and item.data.get("nested_annotation") == "dict"
        for item in trace_valid_violations(bare.observation)
    )
    assert not any(
        item.kind == "boundary_type_allowance"
        for item in bare.observation.records("typing_signals") or ()
    )


def test_nested_boundary_allowance_is_exact_to_sibling_field_path(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "class Request:\n"
            "    left: dict[str, JsonValue]\n"
            "    right: dict[str, JsonValue]\n\n\n"
            "def run() -> Request:\n    return Request()\n"
        ),
        declared=("sample.app.impl:Request", "sample.app.impl:run"),
        allowed_positions=(
            {
                "qualified_name": "sample.app.impl.run",
                "position": "return",
                "field_path": "left",
                "annotation": "dict[str, JsonValue]",
            },
        ),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert [(item.kind, item.data.get("path")) for item in violations] == [
        ("boundary_types", "return.right"),
    ]


def test_unmatched_allowance_does_not_create_a_violation_without_source_evidence(
    tmp_path: Path,
) -> None:
    _write_app(
        tmp_path,
        implementation="def run() -> str:\n    return ''\n",
        declared=("sample.app.impl:run",),
        allowed_positions=(
            {
                "qualified_name": "sample.app.impl.typo",
                "position": "return",
                "field_path": "payload",
                "annotation": "dict[str, JsonValue]",
            },
        ),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert result.diagnostics == ()
    assert trace_valid_violations(result.observation) == ()
    assert not any(
        item.kind == "boundary_type_allowance"
        for item in result.observation.records("typing_signals") or ()
    )
