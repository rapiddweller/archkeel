# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Boundary mapping annotations are broad, while their value types remain observable."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_analyzer import _observe
from test_boundary_types_nested_dtos import _type_unknowns, _write_app

from archkeel.ir.trace import trace_valid_violations


def test_stdlib_mapping_generics_are_broad_across_exact_import_forms(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "from collections.abc import Mapping as ReadMapping, MutableMapping\n"
            "from typing import Mapping as TypingMapping\n"
            "import collections.abc as cabc\n\n"
            "def run(\n"
            "    read: ReadMapping[str, str],\n"
            "    write: MutableMapping[str, str],\n"
            "    typing_alias: TypingMapping[str, str],\n"
            "    qualified: cabc.Mapping[str, str],\n"
            ") -> str:\n"
            "    return ''\n"
        ),
        declared=("sample.app.impl:run",),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert {item.data.get("position") for item in violations} == {
        "read",
        "write",
        "typing_alias",
        "qualified",
    }
    assert all("instead of a typed model" in item.title for item in violations), [
        (item.title, item.data) for item in violations
    ]
    assert _type_unknowns(result) == []


def test_non_stdlib_mapping_generic_stays_unknown(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "from .types import Mapping as LocalMapping\n\n"
            "def run(value: LocalMapping[str, str]) -> str:\n"
            "    return ''\n"
        ),
        declared=("sample.app.impl:run",),
    )
    (tmp_path / "sample/app/types.py").write_text(
        "from typing import Generic, TypeVar\n"
        "K = TypeVar('K')\nV = TypeVar('V')\n"
        "class Mapping(Generic[K, V]):\n    pass\n"
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    [unknown] = _type_unknowns(result)
    assert unknown.data.get("reason") == "generic"
    assert unknown.data.get("annotation") == "LocalMapping[str, str]"


def test_shadowed_stdlib_mapping_name_stays_unknown(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "from collections.abc import Mapping\n\n"
            "def choose():\n    return Mapping\n\n"
            "Mapping = choose()\n\n"
            "def run(value: Mapping[str, str]) -> str:\n"
            "    return ''\n"
        ),
        declared=("sample.app.impl:run",),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    [unknown] = _type_unknowns(result)
    assert unknown.data.get("reason") == "ambiguous_binding"
    assert unknown.data.get("annotation") == "Mapping[str, str]"


@pytest.mark.parametrize(
    "annotation",
    ("Mapping[str]", "Mapping[str, str, bool]", "Mapping[str, ...]"),
    ids=("one-argument", "three-arguments", "ellipsis"),
)
def test_malformed_stdlib_mapping_generic_stays_unknown(tmp_path: Path, annotation: str) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "from collections.abc import Mapping\n\n"
            f"def run(value: {annotation}) -> str:\n"
            "    return ''\n"
        ),
        declared=("sample.app.impl:run",),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    [unknown] = _type_unknowns(result)
    assert unknown.data.get("reason") == "generic"
    assert unknown.data.get("annotation") == annotation


@pytest.mark.parametrize(
    ("position", "field_path", "annotation", "allowance_applies"),
    (
        ("return", "payload", "Mapping[str, float]", True),
        ("return", "other", "Mapping[str, float]", False),
        ("request", "payload", "Mapping[str, float]", False),
        ("return", "payload", "Mapping[str, int]", False),
    ),
    ids=("exact", "wrong-field", "wrong-position", "wrong-annotation"),
)
def test_exact_nested_mapping_allowance(
    tmp_path: Path, position: str, field_path: str, annotation: str, allowance_applies: bool
) -> None:
    allowance = {
        "qualified_name": "sample.app.impl.run",
        "position": position,
        "field_path": field_path,
        "annotation": annotation,
    }
    rule = {
        "id": "APP-TYPES-NOT-DICT",
        "kind": "boundary_types",
        "source": "sample.app",
        "rationale": "Keep the declared application boundary typed.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
        "allowed_positions": [allowance],
    }
    _write_app(
        tmp_path,
        implementation=(
            "from collections.abc import Mapping\n\n"
            "class Request:\n"
            "    payload: Mapping[str, float]\n\n\n"
            "def run() -> Request:\n    return Request()\n"
        ),
        declared=("sample.app.impl:Request", "sample.app.impl:run"),
    )
    contract_path = tmp_path / "contract.json"
    contract = json.loads(contract_path.read_text())
    contract["rules"] = [rule]
    contract_path.write_text(json.dumps(contract))

    result = _observe(tmp_path)

    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    if allowance_applies:
        assert violations == ()
    else:
        [violation] = violations
        assert violation.data.get("path") == "return.payload"
        assert violation.data.get("nested_annotation") == "Mapping[str, float]"
        assert "instead of a typed model" in violation.title


def test_empty_field_path_allows_only_the_top_level_mapping(tmp_path: Path) -> None:
    allowance = {
        "qualified_name": "sample.app.impl.run",
        "position": "values",
        "field_path": "",
        "annotation": "Mapping[str, float]",
    }
    _write_app(
        tmp_path,
        implementation=(
            "from collections.abc import Mapping\n\n"
            "class Request:\n"
            "    payload: Mapping[str, float]\n\n\n"
            "def run(values: Mapping[str, float]) -> Request:\n"
            "    return Request()\n"
        ),
        declared=("sample.app.impl:Request", "sample.app.impl:run"),
        allowed_positions=(allowance,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert {item.data.get("path") for item in violations} == {"return.payload"}
    [fact] = [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]
    assert fact.data.get("position") == "values"
    assert fact.data.get("field_path") == ""


@pytest.mark.parametrize(
    "annotation",
    ("dict[str, MissingType]", "dict[str, str] | MissingType"),
    ids=("unknown-dict-value", "unknown-union-member"),
)
def test_root_dict_allowance_keeps_unknown_members(tmp_path: Path, annotation: str) -> None:
    allowance = {
        "qualified_name": "sample.app.impl.run",
        "position": "return",
        "field_path": "",
        "annotation": annotation,
    }
    _write_app(
        tmp_path,
        implementation=f"def run() -> {annotation}:\n    return {{}}\n",
        declared=("sample.app.impl:run",),
        allowed_positions=(allowance,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    assert any(item.data.get("reason") == "unresolved_name" for item in _type_unknowns(result))


def test_root_dict_allowance_does_not_exempt_nested_collection(tmp_path: Path) -> None:
    allowance = {
        "qualified_name": "sample.app.impl.run",
        "position": "return",
        "field_path": "",
        "annotation": "dict[str, str]",
    }
    _write_app(
        tmp_path,
        implementation="def run() -> list[dict[str, str]]:\n    return []\n",
        declared=("sample.app.impl:run",),
        allowed_positions=(allowance,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.data.get("annotation") == "list[dict[str, str]]"
    assert not [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]


@pytest.mark.parametrize(
    "annotation",
    (
        "Mapping[str, HiddenType]",
        "dict[str, HiddenType]",
        "Mapping[str, str] | HiddenType",
    ),
)
def test_root_mapping_allowance_keeps_private_member(tmp_path: Path, annotation: str) -> None:
    allowance = {
        "qualified_name": "sample.app.impl.run",
        "position": "return",
        "field_path": "",
        "annotation": annotation,
    }
    _write_app(
        tmp_path,
        implementation=(
            "from collections.abc import Mapping\n\n"
            "class HiddenType:\n    pass\n\n"
            f"def run() -> {annotation}:\n    return {{}}\n"
        ),
        declared=("sample.app.impl:run",),
        allowed_positions=(allowance,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert "HiddenType" in violation.title
    assert "does not declare" in violation.title
    allowance_facts = [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]
    assert len(allowance_facts) == 1


def test_root_allowance_cannot_exempt_undeclared_type(tmp_path: Path) -> None:
    allowance = {
        "qualified_name": "sample.app.impl.run",
        "position": "return",
        "field_path": "",
        "annotation": "HiddenType",
    }
    _write_app(
        tmp_path,
        implementation=(
            "class HiddenType:\n    pass\n\ndef run() -> HiddenType:\n    return HiddenType()\n"
        ),
        declared=("sample.app.impl:run",),
        allowed_positions=(allowance,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert "does not declare" in violation.title
    assert not [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]


@pytest.mark.parametrize(
    ("annotation", "inner"),
    (
        ("Mapping[str, dict[str, str]]", "dict[str, str]"),
        ("dict[str, Mapping[str, str]]", "Mapping[str, str]"),
        ("Mapping[str, dict[str, str]] | None", "dict[str, str]"),
        ("list[dict[str, str]] | dict[str, str]", "dict[str, str]"),
    ),
)
def test_root_mapping_allowance_keeps_nested_mapping(
    tmp_path: Path, annotation: str, inner: str
) -> None:
    allowance = {
        "qualified_name": "sample.app.impl.run",
        "position": "return",
        "field_path": "",
        "annotation": annotation,
    }
    _write_app(
        tmp_path,
        implementation=(
            f"from collections.abc import Mapping\n\ndef run() -> {annotation}:\n    return {{}}\n"
        ),
        declared=("sample.app.impl:run",),
        allowed_positions=(allowance,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.data.get("nested_annotation") == inner
    allowance_facts = [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]
    assert len(allowance_facts) == 1


def test_root_allowance_does_not_guess_between_multiple_broad_union_members(tmp_path: Path) -> None:
    annotation = "Mapping[str, dict[str, str]] | dict[str, str]"
    allowance = {
        "qualified_name": "sample.app.impl.run",
        "position": "return",
        "field_path": "",
        "annotation": annotation,
    }
    _write_app(
        tmp_path,
        implementation=(
            f"from collections.abc import Mapping\n\ndef run() -> {annotation}:\n    return {{}}\n"
        ),
        declared=("sample.app.impl:run",),
        allowed_positions=(allowance,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert len(violations) == 3
    assert {item.data.get("container_depth", 0) for item in violations} == {0, 1}
    assert not [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]


def test_exact_mapping_allowance_does_not_hide_private_value_type(tmp_path: Path) -> None:
    allowance = {
        "qualified_name": "sample.app.impl.run",
        "position": "return",
        "field_path": "payload",
        "annotation": "Mapping[str, HiddenType]",
    }
    rule = {
        "id": "APP-TYPES-NOT-DICT",
        "kind": "boundary_types",
        "source": "sample.app",
        "rationale": "Keep the declared application boundary typed.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
        "allowed_positions": [allowance],
    }
    _write_app(
        tmp_path,
        implementation=(
            "from collections.abc import Mapping\n\n"
            "class HiddenType:\n    pass\n\n\n"
            "class Request:\n"
            "    payload: Mapping[str, HiddenType]\n\n\n"
            "def run() -> Request:\n    return Request()\n"
        ),
        declared=("sample.app.impl:Request", "sample.app.impl:run"),
    )
    contract_path = tmp_path / "contract.json"
    contract = json.loads(contract_path.read_text())
    contract["rules"] = [rule]
    contract_path.write_text(json.dumps(contract))

    result = _observe(tmp_path)

    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert {item.data.get("path") for item in violations} == {"return.payload"}
    assert all(
        "HiddenType" in item.title and "does not declare" in item.title for item in violations
    ), [(item.title, item.data) for item in violations]


def test_exact_mapping_allowance_does_not_pass_an_unresolved_value_type(tmp_path: Path) -> None:
    allowance = {
        "qualified_name": "sample.app.impl.run",
        "position": "return",
        "field_path": "payload",
        "annotation": "Mapping[str, MissingType]",
    }
    _write_app(
        tmp_path,
        implementation=(
            "from collections.abc import Mapping\n\n"
            "class Request:\n"
            "    payload: Mapping[str, MissingType]\n\n\n"
            "def run() -> Request:\n    return Request()\n"
        ),
        declared=("sample.app.impl:Request", "sample.app.impl:run"),
        allowed_positions=(allowance,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    [unknown] = _type_unknowns(result)
    assert unknown.data.get("path") == "return.payload"
    assert unknown.data.get("reason") == "unresolved_name"
    [allowance_fact] = [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]
    assert allowance_fact.data.get("annotation") == "Mapping[str, MissingType]"


def test_mapping_alias_allowance_keeps_union_violation_and_unknown(tmp_path: Path) -> None:
    allowance = {
        "qualified_name": "sample.app.impl.run",
        "position": "return",
        "field_path": "payload",
        "annotation": "Mapping[str, float]",
    }
    _write_app(
        tmp_path,
        implementation=(
            "from collections.abc import Mapping\n"
            "from typing import TypeAlias\n\n"
            "class HiddenType:\n    pass\n\n"
            "Payload: TypeAlias = (\n"
            "    Mapping[str, MissingType] | Mapping[str, float] | HiddenType\n"
            ")\n\n"
            "class Request:\n"
            "    payload: Payload\n\n\n"
            "def run() -> Request:\n    return Request()\n"
        ),
        declared=("sample.app.impl:Request", "sample.app.impl:run"),
        allowed_positions=(allowance,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert any(
        "HiddenType" in item.title and "does not declare" in item.title for item in violations
    )
    unknowns = _type_unknowns(result)
    assert any(
        item.data.get("path") == "return.payload" and item.data.get("reason") == "unresolved_name"
        for item in unknowns
    )
    [allowance_fact] = [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]
    assert allowance_fact.data.get("annotation") == "Mapping[str, float]"


def test_top_level_mapping_union_keeps_hidden_violation_and_unknown(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "from collections.abc import Mapping\n"
            "from typing import TypeAlias\n\n"
            "class HiddenType:\n    pass\n\n"
            "Payload: TypeAlias = Mapping[str, HiddenType] | Mapping[str, MissingType]\n\n"
            "def run(value: Payload) -> str:\n    return ''\n"
        ),
        declared=("sample.app.impl:run",),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert any("instead of a typed model" in item.title for item in violations)
    assert any(
        "HiddenType" in item.title and "does not declare" in item.title for item in violations
    )
    assert any(item.data.get("reason") == "unresolved_name" for item in _type_unknowns(result))
