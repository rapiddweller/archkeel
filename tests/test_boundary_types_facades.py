# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""boundary_types follows facade re-exports and owned DTO fields."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_analyzer import _component, _observe

from archkeel.ir.trace import trace_valid_violations


def _contract(*public: str) -> dict[str, object]:
    return {
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


def _write_app(root: Path, *, init: str, impl: str) -> None:
    (root / "contract.json").write_text(json.dumps(_contract("sample.app:run")))
    (root / "sample/app").mkdir(parents=True)
    (root / "sample/app/__init__.py").write_text(init)
    (root / "sample/app/impl.py").write_text(impl)


def test_boundary_types_checks_a_function_at_its_reexport_definition(
    tmp_path: Path,
) -> None:
    """A package facade owns the subject, while the definition supplies its signature."""
    _write_app(
        tmp_path,
        init="from .impl import run\n",
        impl="def run(value: dict) -> str:\n    return str(value)\n",
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.subjects == ("sample.app", "sample.app.run")
    assert violation.data.get("module") == "sample.app"
    assert violation.data.get("qualified_name") == "sample.app.run"


def test_boundary_types_uses_the_facade_in_the_rule_scope_when_reexported_twice(
    tmp_path: Path,
) -> None:
    """A second declared facade must not hide the occurrence in this rule's source."""
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    {
                        **_component("app", public=["sample.a:run", "sample.app:run"]),
                        "packages": ["sample"],
                    }
                ],
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
    (tmp_path / "sample/a").mkdir(parents=True)
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/a/__init__.py").write_text("from ..impl import run\n")
    (tmp_path / "sample/app/__init__.py").write_text("from ..impl import run\n")
    (tmp_path / "sample/impl.py").write_text(
        "def run(value: dict) -> str:\n    return str(value)\n"
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.subjects == ("sample.app", "sample.app.run")


@pytest.mark.parametrize(
    "init",
    [
        "from .impl_a import run\nfrom .impl_b import run\n",
        "from .impl_b import run\nfrom .impl_a import run\n",
    ],
)
def test_boundary_types_marks_two_reexport_origins_unknown_in_either_order(
    tmp_path: Path, init: str
) -> None:
    """Two typed origins for one facade binding are ambiguous, independent of import order."""
    (tmp_path / "contract.json").write_text(json.dumps(_contract("sample.app:run")))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text(init)
    for name in ("impl_a", "impl_b"):
        (tmp_path / f"sample/app/{name}.py").write_text(
            "def run(value: dict) -> str:\n    return str(value)\n"
        )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    [limit] = [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_limit"
    ]
    assert limit.data.get("ambiguous_facade") == 4


def test_boundary_types_accepts_two_aliases_of_one_reexport_origin(
    tmp_path: Path,
) -> None:
    """Two facade aliases of one definition are decidable, not ambiguous."""
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    _component(
                        "app",
                        public=["sample.app:run", "sample.app:run_alias"],
                    )
                ],
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
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text(
        "from .impl import run\n"
        "from .impl import run as run_alias\n"
        "\n"
        '__all__ = ["run", "run_alias"]\n'
    )
    (tmp_path / "sample/app/impl.py").write_text(
        "def run(value: dict) -> str:\n    return str(value)\n"
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.rule_ids == ("APP-TYPES-NOT-DICT",)
    assert violation.subjects == ("sample.app", "sample.app.run")
    assert not [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_limit" and item.data.get("ambiguous_facade")
    ]


def test_boundary_types_checks_direct_fields_of_a_reexported_model(
    tmp_path: Path,
) -> None:
    _write_app(
        tmp_path,
        init="from .impl import Request, run\n",
        impl=(
            "class Request:\n"
            "    metadata: dict\n\n\n"
            "def run(value: Request) -> str:\n"
            "    return str(value)\n"
        ),
    )
    (tmp_path / "contract.json").write_text(
        json.dumps(_contract("sample.app:run", "sample.app.impl:Request"))
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.subjects == ("sample.app", "sample.app.run")
    assert "field metadata" in violation.title


def test_boundary_types_checks_fields_of_a_nested_model(
    tmp_path: Path,
) -> None:
    _write_app(
        tmp_path,
        init="from .impl import Inner, Request, run\n",
        impl=(
            "class Inner:\n"
            "    metadata: dict\n\n\n"
            "class Request:\n"
            "    left: Inner\n"
            "    right: Inner\n\n\n"
            "def run(value: Request) -> str:\n"
            "    return str(value)\n"
        ),
    )
    (tmp_path / "contract.json").write_text(
        json.dumps(
            _contract(
                "sample.app:run",
                "sample.app.impl:Request",
                "sample.app.impl:Inner",
            )
        )
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert {item.data.get("path") for item in violations} == {
        "value.left.metadata",
        "value.right.metadata",
    }
    assert all("field metadata" in item.title for item in violations)
    assert all(item.data.get("nested_annotation") == "dict" for item in violations)


def test_boundary_types_keeps_violations_from_each_union_member(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        init="from .impl import Request, run\n",
        impl=(
            "class Left:\n"
            "    metadata: dict\n\n\n"
            "class Right:\n"
            "    details: object\n\n\n"
            "class Request:\n"
            "    payload: Left | Right | dict\n\n\n"
            "def run(value: Request) -> str:\n"
            "    return str(value)\n"
        ),
    )
    (tmp_path / "contract.json").write_text(
        json.dumps(
            _contract(
                "sample.app:run",
                "sample.app.impl:Request",
                "sample.app.impl:Left",
                "sample.app.impl:Right",
            )
        )
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert {item.data.get("path") for item in violations} == {
        "value.payload",
        "value.payload.metadata",
        "value.payload.details",
    }
    assert (
        next(item for item in violations if item.data.get("path") == "value.payload").data.get(
            "nested_annotation"
        )
        == "dict"
    )


def test_boundary_types_reports_unknown_for_an_unresolved_model_field(
    tmp_path: Path,
) -> None:
    _write_app(
        tmp_path,
        init="from .impl import Request, run\n",
        impl=(
            "class Request:\n"
            "    value: Missing\n\n\n"
            "def run(value: Request) -> str:\n"
            "    return str(value)\n"
        ),
    )
    (tmp_path / "contract.json").write_text(
        json.dumps(_contract("sample.app:run", "sample.app.impl:Request"))
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    [limit] = [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_limit"
    ]
    assert limit.data.get("unresolved_name") == 1
