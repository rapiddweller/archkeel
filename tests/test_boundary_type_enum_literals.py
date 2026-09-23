# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #141: resolve only statically proven enum members in Literal annotations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_analyzer import _component, _observe

from archkeel.ir.model import ObservationResult
from archkeel.ir.trace import trace_valid_violations


def _write_app(
    root: Path, modules: dict[str, str], public: tuple[str, ...] = ("sample.app.facade:run",)
) -> None:
    (root / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [_component("app", public=list(public))],
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
    (root / "sample/app").mkdir(parents=True, exist_ok=True)
    (root / "sample/app/__init__.py").write_text("")
    for module, source in modules.items():
        path = root / "sample/app" / f"{module}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)


def _unknowns(result: ObservationResult) -> list[object]:
    assert result.observation is not None
    return [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_position"
    ]


@pytest.mark.parametrize(
    ("enum_source", "field_annotation", "expected_enum"),
    [
        (
            "from enum import Enum\n"
            "class AuthoringReferenceCategory(str, Enum):\n"
            "    PRODUCT = 'product'\n",
            "AuthoringReferenceCategory.PRODUCT",
            "sample.app.facade.AuthoringReferenceCategory",
        ),
        (
            "from sample.app.types import AuthoringReferenceCategory as RefCategory\n",
            "RefCategory.PRODUCT",
            "sample.app.types.AuthoringReferenceCategory",
        ),
        (
            "from sample.app.types import AuthoringReferenceCategory\n"
            "Category = AuthoringReferenceCategory\n",
            "Category.PRODUCT",
            "sample.app.types.AuthoringReferenceCategory",
        ),
    ],
)
def test_literal_resolves_exact_static_enum_member_through_signature(
    tmp_path: Path, enum_source: str, field_annotation: str, expected_enum: str
) -> None:
    modules = {
        "types": (
            "from enum import Enum\n"
            "class AuthoringReferenceCategory(str, Enum):\n"
            "    PRODUCT = 'product'\n"
        ),
        "facade": (
            "from pydantic import BaseModel, Field\n"
            "from typing import Annotated, Literal\n"
            + enum_source
            + "\ndef run(category: Annotated[Literal["
            + field_annotation
            + "] | str, Field()]) -> str:\n    return str(category)\n"
        ),
    }
    _write_app(tmp_path, modules)

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    assert _unknowns(result) == []
    [run] = [
        item
        for item in result.observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.facade.run"
    ]
    assert expected_enum in run.data.get("facade_types", ())


@pytest.mark.parametrize(
    "annotation",
    [
        "AuthoringReferenceCategory.MISSING",
        "choose_category().PRODUCT",
        "Category.PRODUCT",
        "Other.PRODUCT",
        "Ignored.PRODUCT",
    ],
)
def test_unproven_enum_member_remains_unknown_at_signature_position(
    tmp_path: Path, annotation: str
) -> None:
    facade = (
        "from enum import Enum\n"
        "from typing import Literal\n\n"
        "class AuthoringReferenceCategory(str, Enum):\n"
        "    PRODUCT = 'product'\n\n"
        "class Other:\n"
        "    PRODUCT = 'product'\n\n"
        "class Ignored(Enum):\n"
        "    _ignore_ = ['PRODUCT']\n"
        "    PRODUCT = 'product'\n\n"
        "def choose_category():\n    return AuthoringReferenceCategory\n\n"
        "Category = choose_category()\n\n"
        f"def run(category: Literal[{annotation}]) -> str:\n    return str(category)\n"
    )
    _write_app(tmp_path, {"facade": facade})

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    [unknown] = _unknowns(result)
    assert unknown.data.get("position") == "category"
    assert unknown.data.get("annotation") == f"Literal[{annotation}]"


def test_literal_enum_member_is_reached_through_nested_pydantic_dto(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        {
            "types": (
                "from enum import Enum\n"
                "class AuthoringReferenceCategory(str, Enum):\n"
                "    PRODUCT = 'product'\n"
            ),
            "facade": (
                "from pydantic import BaseModel, Field\n"
                "from typing import Annotated, Literal\n"
                "from sample.app.types import AuthoringReferenceCategory\n\n"
                "class Selection(BaseModel):\n"
                "    category: Annotated[Literal["
                "AuthoringReferenceCategory.PRODUCT] | str, Field()]\n\n"
                "class Request(BaseModel):\n"
                "    selection: Selection\n\n"
                "def run(request: Request) -> str:\n    return str(request)\n"
            ),
        },
        public=(
            "sample.app.facade:Request",
            "sample.app.facade:Selection",
            "sample.app.facade:run",
        ),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [run] = [
        item
        for item in result.observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.facade.run"
    ]
    assert "sample.app.types.AuthoringReferenceCategory" in run.data.get("facade_types", ())
