# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #133: resolve static Literal and typing aliases without evaluating Python."""

from __future__ import annotations

import json
from pathlib import Path

from test_analyzer import _component, _observe

from archkeel.ir.model import ObservationResult, Record
from archkeel.ir.trace import trace_valid_violations


def _write_app(root: Path, source: str, *, public: list[str] | None = None) -> None:
    contract = {
        "schema_version": "2.1.0",
        "components": [_component("app", public=public or ["sample.app.facade:run"])],
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
    (root / "contract.json").write_text(json.dumps(contract))
    (root / "sample/app").mkdir(parents=True)
    (root / "sample/app/__init__.py").write_text("")
    (root / "sample/app/facade.py").write_text(source)


def _positions(result: ObservationResult) -> list[Record]:
    assert result.observation is not None
    return [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_position"
    ]


def test_boundary_types_accepts_static_literal_values_on_signatures_and_dto_fields(
    tmp_path: Path,
) -> None:
    _write_app(
        tmp_path,
        "from pydantic import BaseModel\n"
        "from typing import Literal\n\n"
        'READY = "ready"\n\n'
        "class Request(BaseModel):\n"
        '    state: Literal["ready", READY]\n\n'
        'def run(state: Literal["ready", READY], request: Request) -> str:\n'
        "    return state + request.state\n",
        public=["sample.app.facade:run", "sample.app.facade:Request"],
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    assert _positions(result) == []


def test_boundary_types_keeps_dynamic_literal_arguments_unknown_with_source_annotation(
    tmp_path: Path,
) -> None:
    _write_app(
        tmp_path,
        "from typing import Literal\n\n"
        'DEFAULT = "ready"\n'
        "def compute() -> str:\n    return DEFAULT\n\n"
        "def run(state: Literal[compute()]) -> str:\n    return state\n",
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    [position] = _positions(result)
    assert position.data.get("annotation") == "Literal[compute()]"
    assert position.data.get("reason") == "generic"


def test_boundary_types_checks_union_inside_annotated_and_ignores_metadata_expression(
    tmp_path: Path,
) -> None:
    annotation = "Annotated[str | dict[str, str], Field(discriminator='kind')]"
    _write_app(
        tmp_path,
        "from typing import Annotated\n\n"
        f"def run(value: {annotation}) -> str:\n    return str(value)\n",
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.data.get("position") == "value"
    assert violation.data.get("annotation") == annotation
    assert _positions(result) == []


def test_boundary_types_resolves_unannotated_and_typealias_annotated_union_aliases(
    tmp_path: Path,
) -> None:
    _write_app(
        tmp_path,
        "from typing import Annotated, TypeAlias\n\n"
        "AuthoringReferenceQuery = Annotated[str | int, Field(description='query')]\n"
        "ExplicitQuery: TypeAlias = Annotated[str | int, Field(description='query')]\n\n"
        "def run(query: AuthoringReferenceQuery, explicit: ExplicitQuery) -> str:\n"
        "    return str((query, explicit))\n",
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    assert _positions(result) == []


def test_boundary_types_alias_cycle_stays_unknown_without_losing_annotation(
    tmp_path: Path,
) -> None:
    _write_app(
        tmp_path,
        "First = Second\nSecond = First\n\ndef run(value: First) -> str:\n    return str(value)\n",
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    [position] = _positions(result)
    assert position.data.get("annotation") == "First"


def test_boundary_types_reassigned_alias_fails_closed_as_ambiguous(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        "from typing import Literal\n\n"
        'Query = Literal["safe"]\n'
        "Query = dict[str, str]\n\n"
        "def run(value: Query) -> str:\n    return str(value)\n",
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    [position] = _positions(result)
    assert position.data.get("annotation") == "Query"
    assert position.data.get("reason") == "ambiguous_binding"


def test_boundary_types_class_shadowing_alias_never_silently_uses_old_alias(
    tmp_path: Path,
) -> None:
    _write_app(
        tmp_path,
        "from typing import Literal\n\n"
        'Query = Literal["safe"]\n'
        "class Query:\n    pass\n\n"
        "def run(value: Query) -> str:\n    return str(value)\n",
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) or _positions(result)


def test_boundary_types_known_broad_type_in_annotated_alias_still_violates(
    tmp_path: Path,
) -> None:
    _write_app(
        tmp_path,
        "from typing import Annotated, TypeAlias\n\n"
        "Payload: TypeAlias = Annotated[dict[str, str], Field(description='payload')]\n\n"
        "def run(value: Payload) -> str:\n    return str(value)\n",
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.data.get("annotation") == "Payload"
    assert "field" not in violation.data.get("position", "")
    assert _positions(result) == []
