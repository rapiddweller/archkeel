# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #132: decide nested DTO fields and preserve full paths for unresolved fields."""

from __future__ import annotations

import json
from pathlib import Path

from test_analyzer import _component, _observe

from archkeel.ir.model import ObservationResult
from archkeel.ir.trace import trace_valid_violations


def _write_app(root: Path, *, implementation: str, declared: tuple[str, ...]) -> None:
    (root / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [_component("app", public=list(declared))],
                "rules": [
                    {
                        "id": "APP-TYPES-NOT-DICT",
                        "kind": "boundary_types",
                        "source": "sample.app",
                        "rationale": "Keep the declared application boundary typed.",
                        "provenance": ["docs/architecture/sample.md"],
                        "decided_by": "architect",
                    }
                ],
            }
        )
    )
    (root / "sample/app").mkdir(parents=True)
    (root / "sample/app/__init__.py").write_text("")
    (root / "sample/app/impl.py").write_text(implementation)


def _type_unknowns(result: ObservationResult) -> list[object]:
    assert result.observation is not None
    return [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_position"
    ]


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
