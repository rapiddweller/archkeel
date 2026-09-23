# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #134: exact, auditable allowances for nested boundary fields."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_boundary_types_nested_dtos import _write_app

from archkeel.check.ratchets import measure_python_ratchets
from archkeel.ir.codec import observation_payload, parse_contract
from archkeel.ir.trace import trace_valid_violations

_DECLARED = (
    "sample.app.impl:Inner",
    "sample.app.impl:Request",
    "sample.app.impl:Response",
    "sample.app.impl:run",
)
_IMPLEMENTATION = (
    "from typing import Any\n\n"
    "class Inner:\n"
    "    allowed: dict\n"
    "    sibling: dict\n"
    "    changed: dict[str, Any]\n\n\n"
    "class Request:\n"
    "    items: Inner\n\n\n"
    "class Response:\n"
    "    items: Inner\n"
    "    backup: Inner\n\n\n"
    "def run(request: Request) -> Response:\n"
    "    return Response()\n"
)
_ALLOWANCE = {
    "qualified_name": "sample.app.impl.run",
    "position": "return",
    "field_path": "items.allowed",
    "annotation": "dict",
}


def _contract(*, allowance: dict[str, str] | None = None) -> dict[str, object]:
    rule: dict[str, object] = {
        "id": "APP-TYPES-NOT-DICT",
        "kind": "boundary_types",
        "source": "sample.app",
        "rationale": "Keep the declared application boundary typed.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    if allowance is not None:
        rule["allowed_positions"] = [allowance]
    return {
        "schema_version": "2.1.0",
        "components": [
            {
                "id": "COMP-APP",
                "label": "app",
                "role": "component",
                "packages": ["sample.app"],
                "responsibilities": [],
                "forbidden_responsibilities": [],
                "provenance": ["docs/architecture/sample.md"],
                "public": list(_DECLARED),
            }
        ],
        "rules": [rule],
    }


def _observe_app(tmp_path: Path, allowance: dict[str, str] | None = None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    _write_app(tmp_path, implementation=_IMPLEMENTATION, declared=_DECLARED)
    (tmp_path / "contract.json").write_text(json.dumps(_contract(allowance=allowance)))
    from test_analyzer import _observe

    return _observe(tmp_path)


def test_exact_nested_allowance_leaves_sibling_position_and_changed_annotation(
    tmp_path: Path,
) -> None:
    result = _observe_app(tmp_path, _ALLOWANCE)

    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert {item.data.get("path") for item in violations} == {
        "request.items.allowed",
        "request.items.sibling",
        "request.items.changed",
        "return.items.sibling",
        "return.items.changed",
        "return.backup.allowed",
        "return.backup.sibling",
        "return.backup.changed",
    }


@pytest.mark.parametrize(
    "change",
    [
        {"qualified_name": "sample.app.impl.other"},
        {"position": "returns"},
        {"field_path": "item.allowed"},
        {"annotation": "dict[str, Any]"},
    ],
    ids=["callable-typo", "position-typo", "path-typo", "annotation-mismatch"],
)
def test_allowance_selector_typos_do_not_exempt(tmp_path: Path, change: dict[str, str]) -> None:
    allowance = {**_ALLOWANCE, **change}
    result = _observe_app(tmp_path, allowance)

    assert result.observation is not None
    assert "return.items.allowed" in {
        item.data.get("path") for item in trace_valid_violations(result.observation)
    }
    assert not [
        record
        for record in result.observation.records("typing_signals") or ()
        if record.kind == "boundary_type_allowance"
    ]


def test_applied_allowance_has_exact_positive_json_evidence(tmp_path: Path) -> None:
    result = _observe_app(tmp_path, _ALLOWANCE)
    without_allowance = _observe_app(tmp_path / "without-allowance")

    assert result.observation is not None
    assert without_allowance.observation is not None
    payload = json.loads(json.dumps(observation_payload(result.observation)))
    evidence = [
        record
        for record in payload["typing_signals"]
        if record["kind"] == "boundary_type_allowance"
    ]
    assert len(evidence) == 1
    assert evidence[0]["rule_ids"] == ["APP-TYPES-NOT-DICT"]
    assert evidence[0]["data"] == {
        "qualified_name": _ALLOWANCE["qualified_name"],
        "position": _ALLOWANCE["position"],
        "field_path": _ALLOWANCE["field_path"],
        "annotation": _ALLOWANCE["annotation"],
    }
    assert (
        measure_python_ratchets(result.observation).scalars.typing_positions
        == measure_python_ratchets(without_allowance.observation).scalars.typing_positions
    )


@pytest.mark.parametrize(
    "allowance",
    [
        None,
        {},
        {
            "qualified_name": "sample.app.impl.run",
            "position": "return",
            "field_path": "items.allowed",
        },
        {**_ALLOWANCE, "annotation": 1},
        {**_ALLOWANCE, "extra": "not part of the selector"},
    ],
    ids=["not-an-object", "empty", "missing-annotation", "wrong-value-type", "unknown-field"],
)
def test_malformed_nested_allowance_is_rejected(allowance: object) -> None:
    raw = _contract()
    rules = raw["rules"]
    assert isinstance(rules, list)
    rule = rules[0]
    assert isinstance(rule, dict)
    rule["allowed_positions"] = [allowance]

    with pytest.raises(ValueError):
        parse_contract(raw)
