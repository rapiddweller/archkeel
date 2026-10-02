# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #207: omitted paths reuse the exact direct-position allowance."""

from pathlib import Path

import pytest
from test_analyzer import _observe
from test_boundary_type_allowances import _contract
from test_boundary_types_nested_dtos import _write_app
from test_contract_model import VALIDATOR

from archkeel.ir.codec import contract_bytes, contract_digest, parse_contract
from archkeel.ir.trace import trace_valid_violations
from archkeel.ir.widening import contract_widenings

_ALLOWANCE = {
    "qualified_name": "sample.app.impl.run",
    "position": "return",
    "annotation": "dict[str, str]",
}


def test_omitted_path_has_the_same_canonical_contract_and_digest_as_empty_path() -> None:
    omitted = _contract(allowance=_ALLOWANCE)
    explicit = _contract(allowance={**_ALLOWANCE, "field_path": ""})

    assert not list(VALIDATOR.iter_errors(omitted))
    direct = parse_contract(omitted)
    root = parse_contract(explicit)
    assert direct == root
    assert contract_bytes(direct) == contract_bytes(root)
    assert contract_digest(direct) == contract_digest(root)
    assert contract_widenings(direct, root) == contract_widenings(root, direct) == ()
    [widening] = contract_widenings(parse_contract(_contract()), direct)
    assert "allowed_positions gained" in widening


def test_omitted_return_path_keeps_other_functions_inputs_nested_fields_and_unknowns(
    tmp_path: Path,
) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "from missing import Unknown\n\n"
            "class Request:\n"
            "    payload: dict[str, str]\n"
            "    unresolved: Unknown\n\n"
            "def run(context: dict[str, str], request: Request) -> dict[str, str]:\n"
            "    return {}\n\n"
            "def other() -> dict[str, str]:\n"
            "    return {}\n"
        ),
        declared=("sample.app.impl:Request", "sample.app.impl:run", "sample.app.impl:other"),
        allowed_positions=(_ALLOWANCE,),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert {
        (item.data.get("qualified_name"), item.data.get("position"), item.data.get("path"))
        for item in trace_valid_violations(result.observation)
    } == {
        ("sample.app.impl.run", "context", None),
        ("sample.app.impl.run", "request", "request.payload"),
        ("sample.app.impl.other", "return", None),
    }
    unknowns = result.observation.records("unknowns") or ()
    assert any(item.data.get("path") == "request.unresolved" for item in unknowns)
    [fact] = [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]
    assert dict(fact.data.entries) == {**_ALLOWANCE, "field_path": ""}
    assert fact.rule_ids == ("APP-TYPES-NOT-DICT",)
    assert fact.evidence_ids


@pytest.mark.parametrize(
    "change",
    [
        {"qualified_name": "sample.app.impl.other"},
        {"position": "context"},
        {"annotation": "dict[str, int]"},
    ],
    ids=["function", "position", "annotation"],
)
def test_omitted_path_selector_mismatch_keeps_the_return(
    tmp_path: Path, change: dict[str, str]
) -> None:
    _write_app(
        tmp_path,
        implementation="def run() -> dict[str, str]:\n    return {}\n",
        declared=("sample.app.impl:run",),
        allowed_positions=({**_ALLOWANCE, **change},),
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.data.get("position") == "return"
    assert not [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]


@pytest.mark.parametrize("annotation", ["dict", "Dict", "object", "Mapping", "MutableMapping"])
def test_omitted_path_retains_bare_broad_type_rejection(annotation: str) -> None:
    raw = _contract(allowance={**_ALLOWANCE, "annotation": annotation})

    assert list(VALIDATOR.iter_errors(raw))
    with pytest.raises(ValueError, match="annotation cannot allow bare"):
        parse_contract(raw)


@pytest.mark.parametrize(
    "allowance",
    [
        {"qualified_name": _ALLOWANCE["qualified_name"], "position": "return"},
        {"position": "return", "annotation": "dict[str, str]"},
        {"qualified_name": _ALLOWANCE["qualified_name"], "annotation": "dict[str, str]"},
        {**_ALLOWANCE, "field_path": None},
        {**_ALLOWANCE, "field_path": 1},
        {**_ALLOWANCE, "field_path": " "},
        {**_ALLOWANCE, "extra": "unknown"},
    ],
)
def test_optional_path_does_not_accept_malformed_entries(allowance: dict[str, object]) -> None:
    raw = _contract(allowance=allowance)

    assert list(VALIDATOR.iter_errors(raw))
    with pytest.raises(ValueError):
        parse_contract(raw)


def test_omitted_and_empty_paths_cannot_duplicate_the_same_permission() -> None:
    raw = _contract(allowance=_ALLOWANCE)
    raw["rules"][0]["allowed_positions"].append({**_ALLOWANCE, "field_path": ""})

    with pytest.raises(ValueError, match="unique entries"):
        parse_contract(raw)
