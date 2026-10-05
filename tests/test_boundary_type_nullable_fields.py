# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #342: field permissions pin the declaration, not one union member."""

from pathlib import Path

import pytest
from test_analyzer import _observe
from test_boundary_types_nested_dtos import _write_app

from archkeel.ir.model import Observation, stable_id
from archkeel.ir.trace import trace_valid_violations

_NULLABLE = "dict[str, int] | None"
_ALLOWANCE = {
    "qualified_name": "sample.app.impl.run",
    "position": "return",
    "field_path": "result.observed_counts",
    "annotation": _NULLABLE,
}


def _fixture(
    root: Path,
    annotation: str = _NULLABLE,
    *,
    allowance: dict[str, str] = _ALLOWANCE,
    imports: str = "",
    route: str = "Result",
) -> Observation:
    _write_app(
        root,
        implementation=(
            "from dataclasses import dataclass\nfrom pydantic import BaseModel\n"
            + imports
            + "\nclass Result(BaseModel):\n"
            + f"    observed_counts: {annotation} = None\n"
            + f"    other_counts: {_NULLABLE} = None\n\n"
            + "Alias = Result\n\n@dataclass\nclass Envelope:\n"
            + f"    result: {route}\n\n"
            + "def run() -> Envelope:\n    return Envelope(result=Result())\n"
        ),
        declared=("sample.app.impl:Result", "sample.app.impl:Envelope", "sample.app.impl:run"),
        allowed_positions=(allowance,),
    )
    result = _observe(root)
    assert result.observation is not None
    assert result.diagnostics == ()
    return result.observation


@pytest.mark.parametrize(
    ("annotation", "imports"),
    [
        (_NULLABLE, ""),
        ("Optional[dict[str, int]]", "from typing import Optional\n"),
        ("typing.Optional[dict[str, int]]", "import typing\n"),
        ("Maybe[dict[str, int]]", "from typing import Optional as Maybe\n"),
        ("Union[dict[str, int], None]", "from typing import Union\n"),
    ],
)
def test_exact_nullable_field_allowance_keeps_sibling_and_member_identity(
    tmp_path: Path, annotation: str, imports: str
) -> None:
    observed = _fixture(
        tmp_path, annotation, imports=imports, allowance={**_ALLOWANCE, "annotation": annotation}
    )
    [sibling] = trace_valid_violations(observed)
    assert sibling.data.get("path") == "return.result.other_counts"
    assert sibling.data.get("nested_annotation") == "dict[str, int]"
    assert sibling.id == stable_id(
        "VIO",
        "APP-TYPES-NOT-DICT",
        sibling.fact_ids[0],
        "return",
        "result",
        "other_counts",
        "dict[str, int]",
        "instead of a typed model",
    )
    [fact] = [
        r for r in observed.records("typing_signals") or () if r.kind == "boundary_type_allowance"
    ]
    assert fact.data.get("annotation") == annotation
    assert fact.data.get("nested_annotation") == "dict[str, int]"
    assert fact.data.get("field_path") == "result.observed_counts"
    assert fact.evidence_ids == sibling.evidence_ids


@pytest.mark.parametrize(
    ("annotation", "change", "imports"),
    [
        (_NULLABLE, {"annotation": "dict[str, int]"}, ""),
        ("dict[str, int] | str | None", {}, ""),
        (_NULLABLE, {"qualified_name": "sample.app.impl.other"}, ""),
        (_NULLABLE, {"position": "value"}, ""),
        (_NULLABLE, {"field_path": "observed_counts"}, ""),
        (_NULLABLE, {"field_path": "result.missing"}, ""),
        ("Optional[dict[str, int]]", {}, "from typing import Optional\n"),
        ("dict[str, int]", {"annotation": "dict[str,int]"}, ""),
    ],
)
def test_field_allowance_rejects_inexact_declaration_or_selector(
    tmp_path: Path, annotation: str, change: dict[str, str], imports: str
) -> None:
    observed = _fixture(tmp_path, annotation, allowance={**_ALLOWANCE, **change}, imports=imports)
    assert {r.data.get("path") for r in trace_valid_violations(observed)} == {
        "return.result.observed_counts",
        "return.result.other_counts",
    }
    assert not any(
        r.kind == "boundary_type_allowance" for r in observed.records("typing_signals") or ()
    )


@pytest.mark.parametrize(
    ("route", "remaining"),
    [
        ("Alias", ["return.result.other_counts"]),
        ("list[Alias | None]", ["return.result.other_counts"]),
        ("dict[str, Alias]", ["return.result", "return.result.other_counts"]),
    ],
)
def test_nullable_field_declaration_survives_dto_alias_and_container(
    tmp_path: Path, route: str, remaining: list[str]
) -> None:
    observed = _fixture(tmp_path, route=route)
    assert sorted(r.data.get("path") for r in trace_valid_violations(observed)) == remaining


def test_nullable_allowance_keeps_unknown_union_member(tmp_path: Path) -> None:
    annotation = "dict[str, int] | Missing | None"
    observed = _fixture(tmp_path, annotation, allowance={**_ALLOWANCE, "annotation": annotation})
    assert [r.data.get("path") for r in trace_valid_violations(observed)] == [
        "return.result.other_counts",
    ]
    [unknown] = [
        r for r in observed.records("unknowns") or () if r.kind == "boundary_type_position"
    ]
    assert unknown.data.get("path") == "return.result.observed_counts"
    assert unknown.data.get("nested_annotation") == annotation
    assert unknown.data.get("reason") == "unresolved_name"


@pytest.mark.parametrize(
    ("annotation", "remaining"),
    [
        ("dict[str, int] | object | None", "object"),
        ("dict[str, dict[str, int]] | None", "dict[str, int]"),
    ],
)
def test_full_field_allowance_keeps_other_bad_members(
    tmp_path: Path, annotation: str, remaining: str
) -> None:
    observed = _fixture(tmp_path, annotation, allowance={**_ALLOWANCE, "annotation": annotation})
    selected = [
        r
        for r in trace_valid_violations(observed)
        if r.data.get("path") == "return.result.observed_counts"
    ]
    assert len(selected) == 1
    assert selected[0].data.get("nested_annotation") == remaining


def test_alias_field_allowance_cannot_pin_an_alias_expansion(tmp_path: Path) -> None:
    observed = _fixture(
        tmp_path,
        "Counts",
        imports=f"Counts = {_NULLABLE}\n",
        allowance={**_ALLOWANCE, "annotation": "Counts"},
    )
    assert len(trace_valid_violations(observed)) == 2
    assert not any(
        r.kind == "boundary_type_allowance" for r in observed.records("typing_signals") or ()
    )


def test_full_field_allowance_does_not_select_between_two_map_members(tmp_path: Path) -> None:
    annotation = "dict[str, int] | dict[str, str] | None"
    observed = _fixture(tmp_path, annotation, allowance={**_ALLOWANCE, "annotation": annotation})
    assert len(trace_valid_violations(observed)) == 3
    assert not any(
        r.kind == "boundary_type_allowance" for r in observed.records("typing_signals") or ()
    )


def test_same_field_path_in_distinct_dto_union_branches_stays_unallowed(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "class Left:\n    counts: dict[str, int] | None\n\n"
            "class Right:\n    counts: dict[str, int]\n\n"
            "class Envelope:\n    result: Left | Right\n\n"
            "def run() -> Envelope:\n    return Envelope()\n"
        ),
        declared=(
            "sample.app.impl:Left",
            "sample.app.impl:Right",
            "sample.app.impl:Envelope",
            "sample.app.impl:run",
        ),
        allowed_positions=({**_ALLOWANCE, "field_path": "result.counts"},),
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.data.get("path") == "return.result.counts"
    assert not any(
        r.kind == "boundary_type_allowance"
        for r in result.observation.records("typing_signals") or ()
    )


@pytest.mark.parametrize(
    ("left", "right", "route", "remaining"),
    [
        (_NULLABLE, _NULLABLE, "Left | list[Right]", 2),
        ("dict[str, int]", "dict[str, str]", "Left | Right", 2),
        (_NULLABLE, "object", "Left | Right", 2),
        (_NULLABLE, "str", "Left | Right", 1),
        (_NULLABLE, "Missing", "Left | Right", 1),
    ],
)
def test_field_allowance_requires_one_reached_declaration(
    tmp_path: Path, left: str, right: str, route: str, remaining: int
) -> None:
    implementation = (
        f"class Left:\n    counts: {left}\n\n"
        f"class Right:\n    counts: {right}\n\n"
        f"class Envelope:\n    result: {route}\n\n"
        "def run() -> Envelope:\n    return Envelope()\n"
    )
    declared = (
        "sample.app.impl:Left",
        "sample.app.impl:Right",
        "sample.app.impl:Envelope",
        "sample.app.impl:run",
    )
    _write_app(tmp_path, implementation=implementation, declared=declared)
    control = _observe(tmp_path)
    assert control.observation is not None
    original = trace_valid_violations(control.observation)
    assert len(original) == remaining
    _write_app(
        tmp_path,
        implementation=implementation,
        declared=declared,
        allowed_positions=({**_ALLOWANCE, "field_path": "result.counts", "annotation": left},),
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    assert result.diagnostics == ()
    assert trace_valid_violations(result.observation) == original
    assert result.observation.records("unknowns") == control.observation.records("unknowns")
    assert not any(
        r.kind == "boundary_type_allowance"
        for r in result.observation.records("typing_signals") or ()
    )
